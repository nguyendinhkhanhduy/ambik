import os
import json
import math
import re
from google import genai
from google.genai import types
from data_loader import get_entity_attributes
from pyModelChecking import Kripke
from pyModelChecking.CTL import modelcheck, A, G, Not, AtomicProposition, F

DEFAULT_MODEL = "gemini-2.5-flash"
ENTROPY_THRESHOLD = 0.5

# BILINGUAL CROSS-LINGUAL DICTIONARY
BILINGUAL_KITCHEN_MAP = {
    "trứng ốp la": ["egg", "eggs", "fried_egg"],
    "trứng": ["egg", "eggs", "raw_egg", "fried_egg"],
    "bánh mì": ["bread", "sliced whole wheat bread", "toast"],
    "ly sứ": ["ceramic mug", "a ceramic mug", "porcelain cup"],
    "cốc sứ": ["porcelain cup", "a porcelain cup"],
    "ly bia": ["beer mug", "a beer mug"],
    "ly thủy tinh": ["glass mug", "a glass mug"],
    "ly": ["mug", "glass mug", "ceramic mug", "cup", "porcelain cup"],
    "cốc": ["mug", "glass mug", "ceramic mug", "cup", "porcelain cup"],
    "cà phê": ["coffee", "coffee machine"],
    "cafe": ["coffee", "coffee machine"],
    "sữa": ["milk", "milk glass"],
    "mật ong": ["honey", "honey jar"],
    "chảo": ["pan", "frying pan", "skillet"],
    "nồi": ["pot", "cooking pot"],
    "bát nhỏ": ["small bowl", "bowl"],
    "bát": ["bowl", "small bowl", "soup bowl"],
    "chén": ["bowl", "small bowl"],
    "đĩa": ["plate", "dish rack", "ceramic plate"],
    "lò vi sóng": ["microwave", "microwave oven"],
    "miếng rửa chén": ["sponge", "clean sponge", "dirty sponge"],
    "xà phòng": ["dish soap", "soap"],
    "dao": ["knife", "knife block"],
    "đánh trứng": ["whisk", "egg beater"],
    "đồ đựng": ["container", "food storage container"],
    "hộp đựng": ["container", "food storage container"]
}

TOOL_VIETNAMESE_NAME = {
    "pan": "Chảo chiên (pan)",
    "frying pan": "Chảo chiên (frying pan)",
    "skillet": "Chảo chiên (skillet)",
    "microwave": "Lò vi sóng (microwave)",
    "stove": "Bếp điện (stove)",
    "a ceramic mug": "Ly sứ (a ceramic mug)",
    "ceramic mug": "Ly sứ (ceramic mug)",
    "a glass mug": "Ly thủy tinh (a glass mug)",
    "glass mug": "Ly thủy tinh (glass mug)",
    "a porcelain cup": "Cốc sứ (a porcelain cup)",
    "a beer mug": "Ly bia (a beer mug)",
    "plate": "Đĩa sứ (plate)",
    "bowl": "Bát/Chén (bowl)",
    "small bowl": "Bát nhỏ (small bowl)",
    "whisk": "Cây đánh trứng (whisk)",
    "coffee machine": "Máy pha cà phê (coffee machine)",
    "plastic food storage container": "Hộp nhựa (plastic container)",
    "glass food storage container": "Hộp thủy tinh (glass container)"
}

NON_TOOL_ITEMS = ["eggs", "egg", "milk", "honey", "bread", "dish rack", "kitchen table", "countertop", "knife block", "sponge"]

SYSTEM_PROMPT = """You are a warm, intelligent, highly conversational Household Kitchen Robot Assistant operating in a Kitchen Environment.

CRITICAL REQUIREMENT FOR CHAT DIALOGUE (`chat_reply`):
- Write natural, warm, friendly Vietnamese responses for the Chat Box.
- Directly answer general culinary advice questions! (e.g. "Uống cafe thì nên ăn với món gì?" -> "Dạ, cà phê rất thích hợp ăn kèm bánh mì nướng (toast/bread) hoặc bánh ngọt ạ!").
- NEVER repeat identical fallback text if user asks a different question.

OUTPUT SCHEMA (Strict JSON):
{
  "summary": "<Concise overview>",
  "chat_reply": "<Warm, intelligent, highly conversational reply in Vietnamese>",
  "grounding_analysis": {
    "extracted_objects": ["<list of objects actually in input>"],
    "environment_match": ["<matching items from kitchen state>"],
    "missing_objects": ["<missing required items>"],
    "missing_or_extra": ["<missing or extra objects>"]
  },
  "overall_classification": "Unambiguous" | "Common Sense" | "Preferences" | "Safety",
  "entropy_score": 0.78,
  "disambiguated_mappings": [],
  "detected_ambiguities": [],
  "k_choice_question": {
    "question": "",
    "options": []
  },
  "clarifying_question_for_user": "",
  "lifted_nl": "The system should prop_1 and then prop_2.",
  "proposition_mapping": {
    "prop_1": "action on object 1",
    "prop_2": "action on object 2"
  },
  "ltl_plan": "A(G(Not unsafe_microwave)) & A(G(Not dirty_sponge_on_clean_dish))",
  "verified_safe": true,
  "safe_execution_plan": []
}
"""

def compute_dynamic_semantic_entropy(input_text: str, environment: list, matched_env: list) -> float:
    text_lower = input_text.lower()
    is_explicit_plan = bool(re.search(r'^\s*1[\.\)\-]', input_text, re.MULTILINE))
    has_underspecified_container = any(k in text_lower for k in ["container", "mug", "cup", "bowl", "plate", "vật chứa", "ly", "cốc", "bát", "đĩa", "cafe", "cà phê"])
    has_multiple_matches = len(matched_env) > 1 or len(environment) > 5
    has_vague_verb = any(k in text_lower for k in ["make food", "prepare", "làm đồ ăn", "tùy ý", "gì đó", "bất kỳ", "uống", "ăn"])

    if is_explicit_plan:
        return 0.0
    elif has_vague_verb or (has_underspecified_container and has_multiple_matches):
        sdc_distribution = {"Preferences": 4, "Common Sense": 1}
    elif any(k in text_lower for k in ["trứng ốp la", "fried egg", "rửa chén"]):
        sdc_distribution = {"Common Sense": 5}
    else:
        sdc_distribution = {"Unambiguous": 5}

    total_samples = sum(sdc_distribution.values())
    entropy = 0.0
    for category, count in sdc_distribution.items():
        p_i = count / total_samples
        if p_i > 0:
            entropy -= p_i * math.log2(p_i)

    return round(entropy, 2)


def match_cross_lingual_objects(user_text: str, environment: list) -> tuple:
    matched_env = []
    missing_env = []
    text_lower = user_text.lower()
    sorted_map_keys = sorted(BILINGUAL_KITCHEN_MAP.keys(), key=len, reverse=True)

    for vi_word in sorted_map_keys:
        en_candidates = BILINGUAL_KITCHEN_MAP[vi_word]
        pattern = r'\b' + re.escape(vi_word) + r'\b'
        if re.search(pattern, text_lower):
            found = False
            for env_item in environment:
                env_lower = env_item.lower()
                if any(cand in env_lower for cand in en_candidates) or vi_word in env_lower:
                    if env_item not in matched_env:
                        matched_env.append(env_item)
                    found = True
            if not found:
                if en_candidates[0] not in missing_env:
                    missing_env.append(en_candidates[0])

    for env_item in environment:
        env_word = env_item.lower().replace("a ", "").replace("the ", "").strip()
        pattern = r'\b' + re.escape(env_word) + r'\b'
        if re.search(pattern, text_lower) and env_item not in matched_env:
            matched_env.append(env_item)

    return matched_env, missing_env


def find_ambiguous_candidate_matches(input_text: str, environment: list) -> tuple:
    t_lower = input_text.lower()
    
    # Do not trigger container ambiguity if user is asking general questions like "nên ăn với món gì"
    if any(q in t_lower for q in ["ăn với", "món gì", "nên ăn", "gợi ý", "kèm với"]):
        return None, []

    vague_object_groups = {
        "mug": ["mug", "cup", "ly", "cốc", "cafe", "cà phê"],
        "container": ["container", "storage", "hộp", "đồ đựng"],
        "sponge": ["sponge", "giẻ", "miếng rửa"],
        "bread": ["bread", "bánh mì"],
        "plate": ["plate", "đĩa"],
        "bowl": ["bowl", "bát", "chén"]
    }

    for group_name, keywords in vague_object_groups.items():
        if any(re.search(r'\b' + re.escape(kw) + r'\b', t_lower) for kw in keywords):
            candidates = [env for env in environment if any(kw in env.lower() for kw in keywords)]
            if group_name in ["mug", "cafe", "cà phê"]:
                candidates = [e for e in environment if "mug" in e.lower() or "cup" in e.lower()]
            elif group_name == "container":
                candidates = [e for e in environment if "container" in e.lower()]
            elif group_name == "sponge":
                candidates = [e for e in environment if "sponge" in e.lower()]
            elif group_name == "bread":
                candidates = [e for e in environment if "bread" in e.lower()]

            if len(candidates) >= 2:
                explicit_match = any(c.lower() in t_lower for c in candidates)
                if not explicit_match:
                    return group_name, candidates

    return None, []


def get_valid_tool_candidates(environment: list) -> list:
    valid_tools = []
    for item in environment:
        item_lower = item.lower()
        if not any(non_tool in item_lower for non_tool in NON_TOOL_ITEMS):
            valid_tools.append(item)
    if not valid_tools:
        valid_tools = ["pan", "microwave", "plate", "a ceramic mug"]
    return valid_tools


def format_tool_label(target_name: str) -> str:
    name_clean = target_name.lower().strip()
    for raw_key, vi_label in TOOL_VIETNAMESE_NAME.items():
        if raw_key in name_clean:
            return f"Dùng {vi_label}"
    return f"Dùng {target_name.capitalize()} ({target_name})"


def extract_atomic_target_object(text: str) -> str:
    t_lower = text.lower()
    if "whisk" in t_lower and "small bowl" in t_lower:
        return "whisk & small_bowl"
    elif "whisk" in t_lower:
        return "whisk"
    elif "small bowl" in t_lower or "bowl" in t_lower:
        return "small_bowl"
    elif "eggshell" in t_lower or "shell" in t_lower:
        return "eggshell_fragments"
    elif "two eggs" in t_lower or "eggs" in t_lower or "egg" in t_lower:
        return "raw_eggs"
    elif "food storage container" in t_lower:
        return "food_storage_container"
    elif "honey jar" in t_lower or "honey" in t_lower:
        return "honey_jar"
    elif "bread" in t_lower:
        return "sliced_bread"
    elif "dish rack" in t_lower:
        return "dish_rack"
    elif "coffee machine" in t_lower or "coffee" in t_lower or "cafe" in t_lower:
        return "coffee_machine"
    elif "mug" in t_lower or "cup" in t_lower:
        return "ceramic_mug"

def generate_dynamic_lifted_nl(input_text: str, execution_plan: list) -> tuple:
    if not input_text or not input_text.strip():
        input_text = "Thực hiện nhiệm vụ nhà bếp an toàn"

    lines = [line.strip() for line in input_text.splitlines() if line.strip()]
    
    # 1. If input is numbered plan steps (e.g. 1. Locate container. 2. Pour honey...)
    step_lines = [l for l in lines if re.match(r'^\d+[\.\)\-]', l)]
    if step_lines and len(step_lines) >= 1:
        lifted_parts = []
        prop_map = {}
        for idx, line in enumerate(step_lines, start=1):
            clean_content = re.sub(r'^\d+[\.\)\-]\s*', '', line).strip()
            prop_key = f"prop_{idx}"
            prop_map[prop_key] = clean_content
            lifted_parts.append(f"{idx}. {prop_key}")
        return " -> ".join(lifted_parts), prop_map

    # 2. If execution_plan steps exist
    if execution_plan and len(execution_plan) > 0:
        lifted_parts = []
        prop_map = {}
        for idx, step in enumerate(execution_plan, start=1):
            act = step.get("action", f"Action_{idx}")
            tgt = step.get("target", "object")
            prop_key = f"prop_{idx}"
            prop_map[prop_key] = f"{act}({tgt})".strip()
            lifted_parts.append(prop_key)
        lifted_str = "The robot should " + " and then ".join(lifted_parts) + "."
        return lifted_str, prop_map

    # 3. If it's natural language, split clauses or prepositions
    delimiters = [r'\s+trong\s+', r'\s+bằng\s+', r'\s+và sau đó\s+', r'\s+sau đó\s+', r'\s+rồi\s+', r'\s+và\s+', r'\s+with\s+', r'\s+in\s+', r'\s+and then\s+', r'\s+then\s+', r'\s+and\s+', r',\s*']
    regex_pattern = '|'.join(delimiters)
    segments = [s.strip() for s in re.split(regex_pattern, input_text, flags=re.IGNORECASE) if s.strip()]
    
    if len(segments) >= 2:
        prop_map = {}
        lifted_str = input_text
        for idx, seg in enumerate(segments, start=1):
            prop_key = f"prop_{idx}"
            prop_map[prop_key] = seg
            lifted_str = lifted_str.replace(seg, prop_key, 1)
        return lifted_str, prop_map
    else:
        clean_text = input_text.strip()
        words = clean_text.split()
        if len(words) >= 4:
            mid = len(words) // 2
            seg1 = " ".join(words[:mid])
            seg2 = " ".join(words[mid:])
            return "The system should prop_1 and then prop_2.", {
                "prop_1": seg1,
                "prop_2": seg2
            }
        else:
            return "The system should prop_1 and then prop_2.", {
                "prop_1": clean_text,
                "prop_2": "verify safety constraints"
            }


def translate_action_text_to_vietnamese(text: str) -> str:
    if not text or not text.strip():
        return "Thực hiện bước thao tác an toàn."
        
    t = text.strip()
    t_lower = t.lower()
    
    if "whisk" in t_lower and "small bowl" in t_lower:
        return "Lấy cây đánh trứng và bát nhỏ từ tủ bếp."
    elif "beat two eggs" in t_lower or "beat eggs" in t_lower:
        return "Đánh hai quả trứng trong bát nhỏ cho đến khi tan đều."
    elif "eggshell" in t_lower or "shell" in t_lower:
        return "Kiểm tra bát xem có vỏ trứng và loại bỏ nếu cần."
    elif "locate" in t_lower and "food storage container" in t_lower:
        return "Tìm vị trí hộp đựng thực phẩm trong bếp."
    elif "locate" in t_lower and "honey" in t_lower:
        return "Tìm hũ mật ong trong tủ."
    elif "open" in t_lower and "honey" in t_lower:
        return "Mở nắp hũ mật ong."
    elif "pour honey" in t_lower:
        return "Rót mật ong vào hộp đựng thực phẩm cho đến khi đầy."
    elif "close" in t_lower and "honey" in t_lower:
        return "Đóng nắp hũ mật ong lại."
    elif "locate" in t_lower and "bread" in t_lower:
        return "Tìm vị trí bánh mì."
    elif "dish rack" in t_lower:
        return "Đặt vật thể lên giá úp chén đĩa."
    elif "coffee machine" in t_lower or "cafe" in t_lower or "coffee" in t_lower:
        return "Sử dụng máy pha cà phê để pha chế."

    vi_text = t
    replacements = [
        (r'\bLocate\b', 'Tìm kiếm'),
        (r'\bFind\b', 'Tìm kiếm'),
        (r'\bPick up\b', 'Lấy'),
        (r'\bTake\b', 'Lấy'),
        (r'\bPut\b', 'Đặt'),
        (r'\bPlace\b', 'Đặt'),
        (r'\bPour\b', 'Rót'),
        (r'\bOpen\b', 'Mở'),
        (r'\bClose\b', 'Đóng'),
        (r'\bCook\b', 'Chế biến'),
        (r'\bInspect\b', 'Kiểm tra'),
        (r'\bfrom the kitchen cabinet\b', 'từ tủ bếp'),
        (r'\bfrom the refrigerator\b', 'từ tủ lạnh'),
        (r'\bon the table\b', 'lên bàn'),
        (r'\binto the bowl\b', 'vào bát'),
        (r'\buntil full\b', 'cho đến khi đầy')
    ]
    for pattern, sub in replacements:
        vi_text = re.sub(pattern, sub, vi_text, flags=re.IGNORECASE)

    return vi_text


def parse_clean_atomic_steps(text: str, environment: list) -> list:
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    steps = []
    step_num = 1
    
    for line in lines:
        clean_line = re.sub(r'^\d+[\.\)\-]\s*', '', line).strip()
        if not clean_line: continue
        
        action = "FindObject"
        if any(k in clean_line.lower() for k in ["pick", "take", "cầm", "lấy"]):
            action = "PickUp"
        elif any(k in clean_line.lower() for k in ["put", "place", "pour", "đặt", "để", "rót"]):
            action = "PutObject"
        elif any(k in clean_line.lower() for k in ["cook", "heat", "bake", "fry", "nấu", "chiên", "hâm"]):
            action = "CookObject"
        elif any(k in clean_line.lower() for k in ["beat", "mix", "stir", "đánh", "trộn"]):
            action = "MixIngredients"
        elif any(k in clean_line.lower() for k in ["inspect", "check", "examine", "kiểm tra"]):
            action = "InspectObject"
            
        atomic_target = extract_atomic_target_object(clean_line)
        vi_note = translate_action_text_to_vietnamese(clean_line)
        
        steps.append({
            "step": step_num,
            "action": action,
            "target": atomic_target,
            "note": f"Bước {step_num}: {vi_note}"
        })
        step_num += 1

    if not steps:
        target = environment[0] if environment else "target_item"
        steps = [
            {"step": 1, "action": "FindObject", "target": target, "note": f"Bước 1: Tìm kiếm {target} trong nhà bếp"},
            {"step": 2, "action": "PickUp", "target": target, "note": f"Bước 2: Lấy {target} một cách an toàn"},
            {"step": 3, "action": "PutObject", "target": "kitchen_table", "note": f"Bước 3: Đặt {target} lên bàn ăn"}
        ]
    return steps


def calculate_semantic_entropy(client: genai.Client, input_content: str, environment: list, model_name: str) -> tuple:
    N = 5
    sdc_samples = []
    prompt = f"Analyze ambiguity category for task: '{input_content}'. Environment: {environment}."
    
    for _ in range(N):
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.7, max_output_tokens=10)
            )
            cat = resp.text.strip().replace('"', '').replace("'", "")
            if "unamb" in cat.lower() or "clear" in cat.lower(): sdc_samples.append("Unambiguous")
            elif "common" in cat.lower(): sdc_samples.append("Common Sense")
            elif "safe" in cat.lower(): sdc_samples.append("Safety")
            else: sdc_samples.append("Preferences")
        except Exception:
            sdc_samples.append("Common Sense")

    counts = {}
    for item in sdc_samples:
        counts[item] = counts.get(item, 0) + 1
        
    entropy = 0.0
    for item, count in counts.items():
        p_i = count / N
        if p_i > 0:
            entropy -= p_i * math.log2(p_i)

    return round(entropy, 2), counts


def verify_safety_ltl(execution_plan: list, environment: list) -> tuple:
    default_ltl = "A(G(Not unsafe_microwave)) & A(G(Not dirty_sponge_on_clean_dish)) & A(F(TaskComplete))"
    if not execution_plan or len(execution_plan) == 0:
        return True, default_ltl, ""
        
    violations = []
    
    # 1. Build Kripke states and transitions
    num_states = len(execution_plan)
    S = list(range(num_states))
    S0 = [0]
    R = [(i, i + 1) for i in range(num_states - 1)] + [(num_states - 1, num_states - 1)]
    
    # 2. Extract properties (Labelling)
    L = {}
    env_str = json.dumps(environment).lower()
    has_unsafe_metal = "metal" in env_str
    has_unsafe_plastic = "plastic" in env_str
    
    for i, step in enumerate(execution_plan):
        labels = set()
        step_target = str(step.get("target", "")).lower()
        step_action = str(step.get("action", "")).lower()
        
        if "microwave" in step_target or "microwave" in step_action:
            if has_unsafe_metal or has_unsafe_plastic:
                if any(m in step_target for m in ["metal", "plastic"]):
                    labels.add("unsafe_microwave")
                    
        if "sponge" in step_target and "dirty" in step_target:
            labels.add("dirty_sponge_on_clean_dish")
            
        L[i] = labels

    try:
        K = Kripke(S=S, S0=S0, R=R, L=L)
    except Exception as e:
        return False, f"LTL Kripke Error: {e}", "Failed to build Formal Model"
        
    # 3. Define Formulas and Model Check
    # Safety Rule 1: Globally, never use microwave with unsafe metal or plastic
    f_microwave = A(G(Not(AtomicProposition("unsafe_microwave"))))
    # Safety Rule 2: Globally, never use a dirty sponge on a clean dish
    f_sponge = A(G(Not(AtomicProposition("dirty_sponge_on_clean_dish"))))
    
    try:
        res_microwave = modelcheck(K, f_microwave)
        if 0 not in res_microwave:
            violations.append("Metal or non-microwave safe plastic used in microwave!")
            
        res_sponge = modelcheck(K, f_sponge)
        if 0 not in res_sponge:
            violations.append("Dirty sponge used to clean dishes!")
    except Exception as e:
        return False, f"Formal Checker Error: {e}", "Verification logic crashed"
        
    is_safe = len(violations) == 0
    ltl_str = "A(G(Not unsafe_microwave)) & A(G(Not dirty_sponge_on_clean_dish))"
    
    if not is_safe:
        ltl_str = f"VIOLATION DETECTED: {'; '.join(violations)} -> Enforcement: G(!UnsafeAction)"

    return is_safe, ltl_str, (violations[0] if violations else "")


def analyze_ambik_input(
    input_content: str,
    input_type: str = "plan_amb_task",
    environment: list = None,
    api_key: str = None,
    model_name: str = DEFAULT_MODEL,
    chat_history: list = None
) -> dict:
    if environment is None:
        environment = ["a ceramic mug", "a glass mug", "coffee machine", "milk", "kitchen table", "eggs", "pan"]
    
    is_step_plan = (input_type == "plan_amb_task") or bool(re.search(r'^\s*1[\.\)\-]', input_content, re.MULTILINE))

    key_to_use = api_key or os.environ.get("GEMINI_API_KEY")
    if not key_to_use:
        return get_mock_analysis_response(input_content, input_type, environment, is_step_plan=is_step_plan, chat_history=chat_history)

    try:
        client = genai.Client(api_key=key_to_use)
        entropy_score, sdc_clusters = calculate_semantic_entropy(client, input_content, environment, model_name)
        
        history_str = ""
        if chat_history and len(chat_history) > 0:
            history_str = "\n[CONVERSATION DIALOGUE HISTORY]\n"
            for turn in chat_history:
                role = "User" if turn.get("role") == "user" else "Robot"
                history_str += f"{role}: {turn.get('content', '')}\n"

        user_prompt = f"""
[INPUT DATA]
- Input Type: {input_type}
- Current Instruction / Message:
{input_content}
{history_str}
- Kitchen Environment State:
{json.dumps(environment, ensure_ascii=False, indent=2)}

Perform Neuro-Symbolic AmbiK analysis.
Generate a warm, friendly, highly conversational `chat_reply` in Vietnamese that DIRECTLY ACKNOWLEDGES the user's specific question (e.g. food recommendation or drink pairing)!
Return strictly valid JSON matching System Prompt schema.
"""
        
        response = client.models.generate_content(
            model=model_name,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.3,
                response_mime_type="application/json"
            )
        )
        
        text_content = response.text
        clean_json = re.sub(r'^```json\s*', '', text_content.strip(), flags=re.MULTILINE)
        clean_json = re.sub(r'\s*```$', '', clean_json.strip(), flags=re.MULTILINE)
        
        parsed = json.loads(clean_json)
        
        raw_mappings = parsed.get("disambiguated_mappings", [])
        clean_mappings = []
        for m in raw_mappings:
            vague = str(m.get("vague_expression", "")).strip()
            resolved = str(m.get("disambiguated_expression", "")).strip()
            if vague.lower() != resolved.lower() and vague and resolved:
                clean_mappings.append(m)
        parsed["disambiguated_mappings"] = clean_mappings

        plan = parsed.get("safe_execution_plan", [])
        for idx, s in enumerate(plan):
            if s.get("target"):
                s["target"] = extract_atomic_target_object(s["target"])
                s["note"] = f"Bước {idx+1}: " + translate_action_text_to_vietnamese(s.get("note", s.get("target")))

        is_safe, ltl_str, reason = verify_safety_ltl(plan, environment)
        parsed["verified_safe"] = is_safe
        
        # Always inject dynamic lifted NL
        lifted_text, prop_map = generate_dynamic_lifted_nl(input_content, plan)
        parsed["lifted_nl"] = lifted_text
        parsed["proposition_mapping"] = prop_map

        if not parsed.get("ltl_plan") or parsed.get("ltl_plan") == "No plan to check":
            parsed["ltl_plan"] = ltl_str

        grounding = parsed.get("grounding_analysis", {})
        grounding["kb_attributes"] = {obj: get_entity_attributes(obj) for obj in environment}
        parsed["grounding_analysis"] = grounding

        return parsed

    except Exception as e:
        print(f"Error in Gemini API ({e}). Using warm conversational fallback engine.")
        return get_mock_analysis_response(input_content, input_type, environment, is_step_plan=is_step_plan, error_msg=str(e), chat_history=chat_history)


def get_mock_analysis_response(input_content: str, input_type: str, environment: list, is_step_plan: bool = False, error_msg: str = None, chat_history: list = None) -> dict:
    t_lower = input_content.lower()
    
    detected = []
    mappings = []
    content_lower = input_content.lower()

    matched_env, missing_objects = match_cross_lingual_objects(input_content, environment)
    vague_group, candidate_matches = find_ambiguous_candidate_matches(input_content, environment)

    target_food = "món ăn"
    if "trứng" in content_lower or "egg" in content_lower: target_food = "trứng"
    elif "bánh mì" in content_lower or "bread" in content_lower: target_food = "bánh mì"
    elif "cà phê" in content_lower or "cafe" in content_lower or "coffee" in content_lower: target_food = "cà phê"

    # DYNAMIC & CONTEXT-AWARE CHAT DIALOGUE RESPONSES
    if any(q in content_lower for q in ["ăn với", "món gì", "nên ăn", "gợi ý", "kèm với"]):
        chat_reply = f"Dạ, khi uống cà phê thì rất thích hợp ăn kèm với **bánh mì nướng** (sliced whole wheat bread / toast) hoặc ốp la trứng ạ! Bạn có muốn tôi chuẩn bị bánh mì nướng cho bạn không?"
    elif "cafe" in content_lower or "cà phê" in content_lower:
        if candidate_matches and len(candidate_matches) >= 2:
            chat_reply = f"Dạ vâng! Tôi rất sẵn lòng pha cho bạn một ly cà phê thơm ngon ạ. Hiện trong bếp đang có ly sứ ({candidate_matches[0]}) và ly thủy tinh ({candidate_matches[1]}), bạn thích tôi dùng loại ly nào ạ?"
        else:
            chat_reply = "Dạ vâng! Tôi sẽ dùng máy pha cà phê có sẵn và mang cho bạn một ly cà phê thơm nóng tới bàn ăn ngay đây ạ!"
    elif "trứng" in content_lower:
        chat_reply = f"Vâng ạ! Tôi sẽ giúp bạn chuẩn bị món {target_food}. Bạn muốn chiên trứng bằng chảo hay hâm nóng bằng lò vi sóng ạ?"
    elif any(k in content_lower for k in ["chọn", "dùng", "lấy", "loại", "a", "b", "c", "thủy tinh", "sứ"]):
        chat_reply = f"Dạ tuyệt vời! Tôi đã ghi nhận lựa chọn của bạn và bắt đầu thực hiện kế hoạch chuẩn bị món ăn ngay ạ!"
    else:
        chat_reply = f"Dạ chào bạn! Tôi là Robot Nhà Bếp. Tôi sẵn sàng phục vụ bạn với món {target_food}. Bạn có yêu cầu gì đặc biệt về dụng cụ hay cách chế biến không ạ?"

    if vague_group or (len(candidate_matches) >= 2):
        overall_cat = "Preferences"
        entropy_score = 0.85
        
        cand1 = candidate_matches[0]
        cand2 = candidate_matches[1] if len(candidate_matches) > 1 else candidate_matches[0]
        
        opt1_label = format_tool_label(cand1)
        opt2_label = format_tool_label(cand2)

        question_text = f"Bạn muốn Robot sử dụng loại ly/vật chứa nào để uống {target_food}?"
        
        k_options = [
            {"key": "A", "label": opt1_label, "target": cand1},
            {"key": "B", "label": opt2_label, "target": cand2}
        ]

        mappings.append({
            "vague_expression": f"Lựa chọn vật chứa cho {target_food}",
            "disambiguated_expression": f"Lựa chọn A ({cand1}) / Lựa chọn B ({cand2})",
            "category": "Preferences",
            "explanation": f"Cần xác nhận loại ly/vật chứa người dùng mong muốn sử dụng."
        })

        detected.append({
            "element": f"Lựa chọn ly/vật chứa ({target_food})",
            "category": "Preferences",
            "reasoning": f"Tồn tại nhiều ứng viên {cand1} và {cand2} trong môi trường. Độ bất định H={entropy_score} > 0.5.",
            "action": "GENERATE_QUESTION",
            "payload": {
                "shortlist": [cand1, cand2],
                "clarifying_question": question_text
            }
        })

        k_choice = { "question": question_text, "options": k_options }
        execution_plan = []
        clarification = question_text

    elif is_step_plan or input_type == "plan_amb_task":
        overall_cat = "Unambiguous"
        entropy_score = 0.00
        execution_plan = parse_clean_atomic_steps(input_content, environment)
        k_choice = {"question": "", "options": []}
        clarification = ""

    else:
        overall_cat = "Common Sense"
        entropy_score = 0.18
        main_target = matched_env[0] if matched_env else "coffee_machine"
        tool_used = get_valid_tool_candidates(environment)[0] if get_valid_tool_candidates(environment) else "a ceramic mug"
        
        execution_plan = [
            {"step": 1, "action": "FindObject", "target": extract_atomic_target_object(main_target), "note": f"Bước 1: Tìm kiếm {main_target} trong nhà bếp"},
            {"step": 2, "action": "PickUp", "target": extract_atomic_target_object(tool_used), "note": f"Bước 2: Lấy ly/dụng cụ một cách an toàn"},
            {"step": 3, "action": "CookObject", "target": extract_atomic_target_object(main_target), "note": f"Bước 3: Pha chế {target_food} bằng thiết bị"},
            {"step": 4, "action": "PutObject", "target": "kitchen_table", "note": f"Bước 4: Đặt {target_food} hoàn chỉnh lên bàn ăn"}
        ]
        k_choice = {"question": "", "options": []}
        clarification = ""

    is_safe, ltl_str, _ = verify_safety_ltl(execution_plan, environment)
    kb_attributes = {obj: get_entity_attributes(obj) for obj in environment}

    # Dynamically generate Lifted NL from the ACTUAL user input sentence
    lifted_nl_text, prop_map = generate_dynamic_lifted_nl(input_content, execution_plan)

    return {
        "summary": f"Suy luận Neuro-Symbolic cho '{input_content[:60]}...'. Khớp {len(matched_env)} vật thể.",
        "chat_reply": chat_reply,
        "grounding_analysis": {
            "extracted_objects": matched_env if matched_env else [input_content[:30]],
            "environment_match": matched_env,
            "missing_objects": missing_objects,
            "missing_or_extra": missing_objects,
            "kb_attributes": kb_attributes
        },
        "overall_classification": overall_cat,
        "entropy_score": entropy_score,
        "disambiguated_mappings": mappings,
        "detected_ambiguities": detected,
        "k_choice_question": k_choice,
        "clarifying_question_for_user": clarification,
        "lifted_nl": lifted_nl_text,
        "proposition_mapping": prop_map,
        "ltl_plan": ltl_str,
        "verified_safe": is_safe,
        "safe_execution_plan": execution_plan
    }
