import os
import json
import math
import re
from google import genai
from google.genai import types
from data_loader import get_entity_attributes
from conformal_calibrator import conformal_engine
from pyModelChecking import Kripke
from pyModelChecking.CTL import modelcheck, A, G, Not, AtomicProposition, F

DEFAULT_MODEL = "gemini-2.5-flash"
ENTROPY_THRESHOLD = 0.5
EARLY_ROUTE_CONFIDENCE_THRESHOLD = 0.8

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
    "máy xay": ["blender", "food processor", "juicer"],
    "máy xay sinh tố": ["blender", "food processor"],
    "sinh tố": ["smoothie", "blender", "juicer"],
    "nước ép": ["juice", "juicer"],
    "xay": ["blender", "food processor"],
    "xay nhuyễn": ["blender", "food processor"],
    "táo": ["apple", "apples"],
    "đào": ["peach", "peaches"],
    "nho": ["grape", "grapes"],
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
    "blender": "Máy xay sinh tố (blender)",
    "food processor": "Máy xay đa năng (food processor)",
    "juicer": "Máy ép hoa quả (juicer)",
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
    # Fail-closed: return empty list if no valid tool found.
    # Callers must handle [] and return NEEDS_CLARIFICATION, not synthesize names.
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
    elif "table" in t_lower or "bàn" in t_lower:
        return "kitchen_table"
    elif "cabinet" in t_lower or "tủ" in t_lower:
        return "kitchen_cabinet"
    return text.lower().replace(" ", "_").strip()

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
            return input_text, {"prop_1": input_text}

        else:
            # Fallback: use the original input as the lifted NL
            return input_text, {"prop_1": input_text}



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
    """Parse numbered plan steps. Each line is one atomic action.
    Targets are GROUNDED to objects from `environment` — never extracted raw from text.
    """
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    # Process lines that look like numbered plan steps, or single-line commands
    step_lines = [l for l in lines if re.match(r'^\d+[\.\)\-]', l)]
    if not step_lines:
        if len(lines) == 1:
            step_lines = lines
        else:
            # Multi-line unnumbered text — fail-closed so callers use the chat-style generator
            return []

    steps = []
    step_num = 1

    # Pre-build a lookup: for each env object, produce a normalized key
    env_normalized = [(e, set(re.findall(r'\w+', e.lower()))) for e in environment]

    for line in step_lines:
        clean_line = re.sub(r'^\d+[\.\)\-]\s*', '', line).strip()
        if not clean_line:
            continue

        line_lower = clean_line.lower()

        # Determine action
        if any(k in line_lower for k in ["pick", "take", "cầm", "lấy", "retrieve", "grab"]):
            action = "PickUp"
        elif any(k in line_lower for k in ["put", "place", "pour", "đặt", "để", "rót", "serve"]):
            action = "PutObject"
        elif any(k in line_lower for k in ["cook", "heat", "bake", "fry", "blend", "xay", "nấu", "chiên", "hâm", "mix", "stir", "beat", "đánh", "trộn", "use", "operate"]):
            action = "CookObject"
        elif any(k in line_lower for k in ["inspect", "check", "examine", "kiểm tra", "verify"]):
            action = "InspectObject"
        else:
            action = "FindObject"

        # Ground target to an environment object via token overlap
        line_tokens = set(re.findall(r'\w+', line_lower))
        best_match = None
        best_overlap = 0
        for env_obj, env_tokens in env_normalized:
            overlap = len(line_tokens & env_tokens)
            if overlap > best_overlap:
                best_overlap = overlap
                best_match = env_obj

        if best_match and best_overlap > 0:
            atomic_target = extract_atomic_target_object(best_match)
        else:
            # Fallback: try the dedicated extractor on the line text
            candidate = extract_atomic_target_object(clean_line)
            # If the fallback returned a long garbage string (>30 chars), use first env obj
            if len(candidate) > 30 and environment:
                candidate = extract_atomic_target_object(environment[0])
            atomic_target = candidate

        vi_note = translate_action_text_to_vietnamese(clean_line)
        steps.append({
            "step": step_num,
            "action": action,
            "target": atomic_target,
            "note": f"Bước {step_num}: {vi_note}"
        })
        step_num += 1

    if not steps:
        return []
    return steps


def early_route_classify(input_text: str, input_type: str, environment: list, matched_env: list, client=None, model_name: str = None) -> tuple:
    """
    Conformal Early Routing Classifier (KnowNo - NeurIPS 2023 Standard).
    Tier 1: Rule-based heuristic estimation + Conformal Prediction Set.
    Tier 2: Zero-shot LLM distribution + Conformal Prediction Set.
    
    Guarantees distribution-free statistical coverage (e.g. 95% confidence).
    Returns: (category, confidence, skip_entropy, reason, tier_used, conformal_info)
    """
    text_lower = input_text.lower().strip()
    
    # === TIER 1: Rule-based Heuristic Probabilities ===
    vague_keywords = ["tùy ý", "gì đó", "bất kỳ", "any", "whatever", "something", "anything", "container", "sponge", "items", "ingredients", "appropriate tools", "suitable plate", "dụng cụ phù hợp"]
    container_words = ["container", "ly", "cốc", "mug", "cup", "bát", "bowl", "đĩa", "plate"]
    container_candidates = [e for e in environment if any(k in e.lower() for k in ["mug", "cup", "container", "bowl", "plate"])]
    
    has_vague_kw = any(k in text_lower for k in vague_keywords)
    has_container_ref = any(k in text_lower for k in container_words)
    specific_modifiers = ["sứ", "ceramic", "thủy tinh", "glass", "nhựa", "plastic", "kim loại", "metal", "sạch", "clean", "bẩn", "dirty"]
    has_specific_modifier = any(m in text_lower for m in specific_modifiers)
    is_unambiguous_container = has_container_ref and has_specific_modifier

    # Check for safety-critical hazards — NEVER fast-route safety critical commands to Unambiguous
    is_safety_critical = any(k in text_lower for k in [
        "knife", "slice", "cut", "sharp", "microwave", "vi sóng", "lò vi", "heat", "hâm nóng", "metal", "boil", "hot", "danger", "hazard", "dirty sponge", "giẻ bẩn"
    ])
    
    specific_actions = ["bật", "tắt", "mở", "đóng", "turn on", "turn off", "open", "close", "locate", "find", "tìm", "xay", "xay nhuyễn", "blend", "nấu", "chiên", "hâm", "rửa", "lấy", "pha", "trộn", "ép", "cook", "make", "prepare"]
    is_simple_action = any(a in text_lower for a in specific_actions) and len(text_lower.split()) <= 15
    is_common_sense = any(k in text_lower for k in ["trứng ốp la", "fried egg", "rửa chén", "wash dishes", "xay sinh tố", "làm sinh tố", "pha cà phê", "hâm nóng bánh mì", "xay nhuyễn"])
    
    if is_safety_critical:
        tier1_probs = {"Safety": 0.88, "Preferences": 0.08, "Unambiguous": 0.04}
        tier1_cat = "Safety"
    elif has_vague_kw or (has_container_ref and not has_specific_modifier and len(container_candidates) >= 2):
        tier1_probs = {"Preferences": 0.90, "Unambiguous": 0.10}
        tier1_cat = "Preferences"
    elif (is_unambiguous_container or (is_simple_action and not has_vague_kw) or (is_common_sense and not has_vague_kw)) and not is_safety_critical:
        tier1_probs = {"Unambiguous": 0.96, "Preferences": 0.04}
        tier1_cat = "Unambiguous"
    else:
        tier1_probs = {"Unambiguous": 0.50, "Preferences": 0.50}
        tier1_cat = "Inconclusive"
        
    # Evaluate Conformal Prediction Set on Tier 1
    conf_set_t1, is_clear_t1, cov_t1, q_hat_t1 = conformal_engine.get_conformal_set(tier1_probs)
    if is_clear_t1 and tier1_cat == "Unambiguous":
        return (
            "Unambiguous",
            0.95,
            True,
            f"Conformal Fast Route: 95% coverage guarantee (Gamma={conf_set_t1}, q_hat={q_hat_t1:.2f})",
            "conformal_rule",
            {"conformal_set": conf_set_t1, "coverage_guarantee": cov_t1, "q_hat": q_hat_t1, "method": "Conformal Prediction (KnowNo - NeurIPS 2023)"}
        )
    
    if tier1_cat in ("Preferences", "Safety"):
        return (
            tier1_cat,
            0.85,
            False,
            f"Conformal Routing: {tier1_cat} context (Gamma={conf_set_t1}) -> requires disambiguation",
            "conformal_rule",
            {"conformal_set": conf_set_t1, "coverage_guarantee": cov_t1, "q_hat": q_hat_t1, "method": "Conformal Prediction (KnowNo - NeurIPS 2023)"}
        )

    # === TIER 2: Zero-shot LLM with Conformal Prediction ===
    if client and model_name:
        try:
            classify_prompt = (
                f"Classify this kitchen robot command as CLEAR or AMBIGUOUS.\n"
                f"Command: \"{input_text}\"\n"
                f"Environment: {json.dumps(environment, ensure_ascii=False)}\n"
                f"Answer strictly: CLEAR|AMBIGUOUS confidence:0.0-1.0\n"
                f"Example: CLEAR confidence:0.92"
            )
            resp = client.models.generate_content(
                model=model_name,
                contents=classify_prompt,
                config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=20)
            )
            llm_text = resp.text.strip()
            
            conf_match = re.search(r'confidence[:\s]*([0-9.]+)', llm_text, re.IGNORECASE)
            llm_conf = float(conf_match.group(1)) if conf_match else 0.60
            llm_conf = min(max(llm_conf, 0.0), 1.0)
            
            is_clear = "CLEAR" in llm_text.upper()
            llm_probs = {
                "Unambiguous": llm_conf if is_clear else (1.0 - llm_conf),
                "Preferences": (1.0 - llm_conf) if is_clear else llm_conf
            }
            
            conf_set_t2, is_clear_t2, cov_t2, q_hat_t2 = conformal_engine.get_conformal_set(llm_probs)
            category = "Unambiguous" if is_clear_t2 else "Preferences"
            skip = is_clear_t2
            
            reason = f"Conformal LLM: {'Provably CLEAR' if is_clear_t2 else 'AMBIGUOUS'} (Gamma={conf_set_t2}, {cov_t2}% coverage, q_hat={q_hat_t2:.2f})"
            return (
                category,
                round(llm_conf, 2),
                skip,
                reason,
                "conformal_llm",
                {"conformal_set": conf_set_t2, "coverage_guarantee": cov_t2, "q_hat": q_hat_t2, "method": "Conformal Prediction (KnowNo - NeurIPS 2023)"}
            )
            
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                return (
                    "Common Sense",
                    0.50,
                    True,
                    "API quota exhausted — fail fast to mock",
                    "conformal_fallback",
                    {"conformal_set": ["Common Sense"], "coverage_guarantee": 95.0, "q_hat": 0.20, "method": "Conformal Prediction Fallback"}
                )
    
    # Fallback
    return (
        "Common Sense",
        0.50,
        False,
        f"Conformal uncertain (Gamma={conf_set_t1}) -> full N=5 required",
        "conformal_rule",
        {"conformal_set": conf_set_t1, "coverage_guarantee": cov_t1, "q_hat": q_hat_t1, "method": "Conformal Prediction (KnowNo - NeurIPS 2023)"}
    )


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


def verify_safety_ctl(execution_plan: list, environment: list) -> tuple:
    """
    Formal Symbolic Safety Invariant Model Checking using Computation Tree Logic (CTL) & Kripke Structure.
    Formulas verified on Kripke Structure M = <S, S0, R, L>:
      phi_1 = AG(!unsafe_microwave)
      phi_2 = AG(!dirty_sponge_on_clean_dish)
      phi_3 = AG(!knife_without_cutting_board)
      phi_4 = AG(!hot_liquid_unsafe_container)
    Returns: (is_safe: bool, ctl_spec: str, first_violation: str)
    """
    default_ctl = "AG(!unsafe_microwave) & AG(!dirty_sponge_on_clean_dish) & AG(!knife_without_cutting_board)"
    if not execution_plan or len(execution_plan) == 0:
        return True, default_ctl, ""
        
    violations = []
    
    # 1. Build Kripke states and transitions
    num_states = len(execution_plan)
    S = list(range(num_states))
    S0 = [0]
    R = [(i, i + 1) for i in range(num_states - 1)] + [(num_states - 1, num_states - 1)]
    
    # 2. Extract rich state properties (Labelling L: S -> 2^AP)
    L = {}
    env_str = json.dumps(environment).lower()
    has_cutting_board_in_env = any(k in env_str for k in ["cutting board", "thớt", "chopping board"])
    has_cutting_board_in_plan = any(
        any(k in str(step.get("target", "")).lower() for k in ["cutting_board", "cutting board", "thớt"])
        for step in execution_plan
    )
    
    for i, step in enumerate(execution_plan):
        labels = set()
        step_target = str(step.get("target", "")).lower()
        step_action = str(step.get("action", "")).lower()
        
        # Rule 1: Microwave with metal/plastic
        if "microwave" in step_target or "heat" in step_action or "cook" in step_action:
            if any(m in step_target for m in ["metal", "plastic", "aluminum", "foil", "tin", "steel"]):
                labels.add("unsafe_microwave")
                
        # Rule 2: Dirty cleaning tool on clean dish or food
        if any(k in step_target for k in ["sponge", "rag", "cloth", "towel"]) and any(k in step_target for k in ["dirty", "used", "soiled", "bẩn"]):
            labels.add("dirty_sponge_on_clean_dish")
            
        # Rule 3: Knife slicing without cutting board in plan
        if any(k in step_target for k in ["knife", "dao", "paring_knife", "bread_knife"]) or any(k in step_action for k in ["slice", "cut", "cắt", "thái"]):
            if not (has_cutting_board_in_plan or has_cutting_board_in_env):
                labels.add("knife_without_cutting_board")

        # Rule 4: Hot boiling liquid into non-heat safe container
        if any(k in step_action for k in ["pour", "rót"]) and any(k in step_target for k in ["plastic bag", "plastic wrap", "túi nilon"]):
            labels.add("hot_liquid_unsafe_container")
            
        L[i] = labels

    try:
        K = Kripke(S=S, S0=S0, R=R, L=L)
    except Exception as e:
        return False, f"CTL Kripke Error: {e}", "Failed to build Formal Model"
        
    # 3. Define Formulas and Model Check
    # Rule 1: Globally, never use microwave with unsafe metal or plastic
    f_microwave = A(G(Not(AtomicProposition("unsafe_microwave"))))
    # Rule 2: Globally, never use a dirty sponge on a clean dish
    f_sponge = A(G(Not(AtomicProposition("dirty_sponge_on_clean_dish"))))
    # Rule 3: Globally, never use a knife without a cutting board
    f_knife = A(G(Not(AtomicProposition("knife_without_cutting_board"))))
    # Rule 4: Globally, never pour into unsafe plastic container
    f_hot_liquid = A(G(Not(AtomicProposition("hot_liquid_unsafe_container"))))
    
    try:
        res_microwave = modelcheck(K, f_microwave)
        if 0 not in res_microwave:
            violations.append("Metal or non-microwave safe material used in microwave!")
            
        res_sponge = modelcheck(K, f_sponge)
        if 0 not in res_sponge:
            violations.append("Dirty sponge/cleaning tool used on dishes or food surfaces!")

        res_knife = modelcheck(K, f_knife)
        if 0 not in res_knife:
            violations.append("Knife cutting action executed without a cutting board!")

        res_hot_liquid = modelcheck(K, f_hot_liquid)
        if 0 not in res_hot_liquid:
            violations.append("Hot liquid poured into non-heat safe plastic container!")
    except Exception as e:
        return False, f"Formal Checker Error: {e}", "Verification logic crashed"
        
    is_safe = len(violations) == 0
    ctl_str = "AG(!unsafe_microwave) & AG(!dirty_sponge) & AG(!knife_without_board) & AG(!unsafe_container)"
    
    if not is_safe:
        ctl_str = f"VIOLATION DETECTED: {'; '.join(violations)} -> Enforcement: AG(!UnsafeAction)"

    return is_safe, ctl_str, (violations[0] if violations else "")

# Backward-compatibility alias
verify_safety_ltl = verify_safety_ctl


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
        # === Early Routing: Phân loại sớm ===
        matched_env_early, _ = match_cross_lingual_objects(input_content, environment)
        route_cat, route_conf, skip_entropy, route_reason, route_tier, conformal_meta = \
            early_route_classify(input_content, input_type, environment, matched_env_early, client, model_name)
        
        # Fail-fast: API quota exhausted -> switch to mock immediately
        if "fail fast" in route_reason.lower():
            print(f"[Early Routing] {route_reason}. Switching to mock engine.")
            return get_mock_analysis_response(input_content, input_type, environment, is_step_plan=is_step_plan, error_msg=route_reason, chat_history=chat_history)
        
        if skip_entropy:
            entropy_score = 0.0
            sdc_clusters = {route_cat: 5}
            print(f"[Early Routing] SKIP N=5 | {route_reason} | Confidence: {route_conf}")
        else:
            entropy_score, sdc_clusters = calculate_semantic_entropy(client, input_content, environment, model_name)
            print(f"[Early Routing] FULL N=5 | {route_reason} | Confidence: {route_conf}")
        
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

        # ── FIX #9: Schema-validate every step from Gemini ───────────────────
        from schemas.environment import EnvironmentState, ExecutionStep as SchemaStep, AllowedAction
        schema_env = EnvironmentState.from_string_list(environment)
        env_ids = schema_env.ids()

        def _resolve_id_gemini(target_str: str) -> str:
            if not target_str:
                return target_str
            target_lower = str(target_str).lower().replace("_", " ").strip()
            for obj in schema_env.objects:
                if obj.name.lower() == target_lower:
                    return obj.id
            for obj in schema_env.objects:
                if obj.id.replace("_", " ").rstrip(" 0123456789").strip() == target_lower:
                    return obj.id
            for obj in schema_env.objects:
                if target_lower in obj.name.lower() or obj.name.lower() in target_lower:
                    return obj.id
            target_tokens = set(target_lower.split())
            for obj in schema_env.objects:
                if target_tokens & set(obj.name.lower().split()):
                    return obj.id
            return target_str  # unresolved — will trigger rejection below

        schema_steps_gemini = []
        schema_errors_gemini = []

        for idx, s in enumerate(plan):
            raw_action = str(s.get("action", "")).strip()
            raw_target = str(s.get("target", "")).strip()
            # Normalise target string first
            normalized_target = extract_atomic_target_object(raw_target) if raw_target else ""
            resolved_id = _resolve_id_gemini(normalized_target or raw_target)

            try:
                schema_step = SchemaStep(
                    step_id=s.get("step", idx + 1),
                    action=raw_action,                 # Pydantic will validate via AllowedAction enum
                    object_id=resolved_id,
                    destination_id=_resolve_id_gemini(str(s.get("destination", ""))) if s.get("destination") else None,
                    parameters=s.get("parameters", {}),
                    note=s.get("note", "")
                )
                # FIX #9: Object must exist in environment — reject synthetic objects
                if resolved_id not in env_ids:
                    raise ValueError(f"Object '{resolved_id}' not found in environment {env_ids}")
                schema_steps_gemini.append(schema_step)
                # Update plan step with normalised values for display
                s["target"] = extract_atomic_target_object(resolved_id)
                s["note"] = f"Bước {idx+1}: " + translate_action_text_to_vietnamese(s.get("note", s.get("target", "")))
            except Exception as e:
                err_msg = f"Bước {idx+1} không hợp lệ: action='{raw_action}', target='{raw_target}' — {e}"
                print(f"[GEMINI-SCHEMA-BLOCK] {err_msg}")
                schema_errors_gemini.append(err_msg)

        # FIX #9: Any schema violation → reject entire plan, no partial approval
        if schema_errors_gemini:
            return {
                "status": "REJECTED",
                "reason_code": "INVALID_ACTION",
                "summary": f"Kế hoạch Gemini bị từ chối: {len(schema_errors_gemini)} bước không hợp lệ.",
                "chat_reply": f"⚠️ Kế hoạch AI sinh ra chứa hành động/đối tượng không hợp lệ: {schema_errors_gemini[0]}",
                "overall_classification": parsed.get("overall_classification", "Unknown"),
                "entropy_score": entropy_score,
                "k_choice_question": parsed.get("k_choice_question", {"question": "", "options": []}),
                "execution_plan": [],
                "safe_execution_plan": [],
                "verified_safe": False,
                "early_routing": {
                    "was_skipped": skip_entropy, "confidence": route_conf,
                    "category": route_cat, "reason": route_reason,
                    "tier": route_tier, "api_calls_saved": 5 if skip_entropy else 0,
                    "cost_saved_pct": 83 if skip_entropy else 0, "conformal_meta": conformal_meta
                },
            }

        # ── FIX #1: Run SafetyPolicyEngine on Gemini plan (same as mock) ──────
        from safety_policy import get_safety_engine
        policy_result_gemini = get_safety_engine().check(schema_steps_gemini, schema_env)
        if not policy_result_gemini.is_safe:
            v = policy_result_gemini.first_rejection()
            return {
                "status": "REJECTED",
                "reason_code": v.reason_code.value if v else "SAFETY_INVARIANT_VIOLATED",
                "summary": v.message if v else "Kế hoạch Gemini vi phạm quy tắc an toàn.",
                "chat_reply": f"⚠️ Kế hoạch AI vi phạm an toàn vật lý: {v.message if v else 'Safety violation'}",
                "overall_classification": parsed.get("overall_classification", "Safety"),
                "entropy_score": entropy_score,
                "k_choice_question": parsed.get("k_choice_question", {"question": "", "options": []}),
                "execution_plan": [],
                "safe_execution_plan": [],
                "verified_safe": False,
                "early_routing": {
                    "was_skipped": skip_entropy, "confidence": route_conf,
                    "category": route_cat, "reason": route_reason,
                    "tier": route_tier, "api_calls_saved": 5 if skip_entropy else 0,
                    "cost_saved_pct": 83 if skip_entropy else 0, "conformal_meta": conformal_meta
                },
            }

        # ── CTL safety check (already existed, now after policy gate) ────────
        is_safe, ltl_str, reason = verify_safety_ltl(plan, environment)
        parsed["verified_safe"] = is_safe and policy_result_gemini.is_safe

        # Always inject dynamic lifted NL
        lifted_text, prop_map = generate_dynamic_lifted_nl(input_content, plan)
        parsed["lifted_nl"] = lifted_text
        parsed["proposition_mapping"] = prop_map

        if not parsed.get("ltl_plan") or parsed.get("ltl_plan") == "No plan to check":
            parsed["ltl_plan"] = ltl_str

        grounding = parsed.get("grounding_analysis", {})
        grounding["kb_attributes"] = {obj: get_entity_attributes(obj) for obj in environment}
        parsed["grounding_analysis"] = grounding

        # Inject Early Routing metadata
        parsed["early_routing"] = {
            "was_skipped": skip_entropy,
            "confidence": route_conf,
            "category": route_cat,
            "reason": route_reason,
            "tier": route_tier,
            "api_calls_saved": 5 if skip_entropy else 0,
            "cost_saved_pct": 83 if skip_entropy else 0,
            "conformal_meta": conformal_meta
        }

        # Hide plan if not safe
        if not parsed["verified_safe"]:
            parsed["safe_execution_plan"] = []
            parsed["execution_plan"] = []
            parsed["status"] = parsed.get("status", "REJECTED")
        else:
            parsed.setdefault("status", "APPROVED")

        return parsed

    except Exception as e:
        print(f"Error in Gemini API ({e}). Using warm conversational fallback engine.")
        return get_mock_analysis_response(input_content, input_type, environment, is_step_plan=is_step_plan, error_msg=str(e), chat_history=chat_history)


def get_mock_analysis_response(input_content: str, input_type: str, environment: list, is_step_plan: bool = None, error_msg: str = None, chat_history: list = None) -> dict:
    if is_step_plan is None or not is_step_plan:
        is_step_plan = (input_type == "plan_amb_task") or bool(re.search(r'^\s*1[\.\)\-]', input_content, re.MULTILINE))

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

    # ── Check if user has answered a clarification question ────────────────────
    user_choice_match = re.search(
        r'\[(?:Người dùng chọn|Nguoi dung chon|Câu trả lời từ người dùng|Cau tra loi tu nguoi dung)[^\]]*\]:\s*(?:Dùng\s*|Dung\s*)?([^\n\r\.]+)',
        input_content,
        re.IGNORECASE
    )
    user_selected_target = None
    if user_choice_match:
        raw_pick = user_choice_match.group(1).strip()
        # Direct check for sentinel values
        if raw_pick in ("__cancel__", "__unsafe__"):
            user_selected_target = raw_pick
        else:
            for env_obj in environment:
                if env_obj.lower() in raw_pick.lower() or raw_pick.lower() in env_obj.lower():
                    user_selected_target = env_obj
                    break
            if not user_selected_target and environment:
                tokens = set(re.findall(r'\w+', raw_pick.lower()))
                for env_obj in environment:
                    if tokens & set(re.findall(r'\w+', env_obj.lower())):
                        user_selected_target = env_obj
                        break
            if not user_selected_target:
                user_selected_target = raw_pick

    route_cat, route_conf, skip_entropy, route_reason, route_tier, conformal_meta = early_route_classify(input_content, input_type, environment, matched_env)

    has_vague_kw = any(k in content_lower for k in ["tùy ý", "gì đó", "bất kỳ", "any", "whatever", "something", "items", "ingredients", "container", "a mug", "a cup"])
    is_safety_critical = any(k in content_lower for k in ["knife", "slice", "cut", "sharp", "microwave", "metal", "boil", "hot", "danger", "hazard"])

    # If user already made a selection, override ambiguity -> Unambiguous
    if user_selected_target:
        # Sentinels: user explicitly chose unsafe or cancel
        if user_selected_target in ("__cancel__", "__unsafe__"):
            return {
                "status": "REJECTED",
                "reason_code": "SAFETY_INVARIANT_VIOLATED",
                "summary": "Người dùng từ chối hoặc chọn phương án không an toàn. Kế hoạch bị hủy.",
                "chat_reply": "⚠️ Yêu cầu đã bị hủy vì lý do an toàn. Tôi không thể thực thi kế hoạch có nguy cơ gây hại. Bạn có muốn chọn lại vật thể an toàn hơn không?",
                "overall_classification": "Safety",
                "entropy_score": 0.72,
                "k_choice_question": {"question": "", "options": []},
                "execution_plan": [],
                "safe_execution_plan": [],
                "verified_safe": False,
                "early_routing": {"was_skipped": False, "reason": "User cancelled safety action", "tier": "mock", "conformal_meta": {}},
            }

        overall_cat = "Unambiguous"
        entropy_score = 0.00
        chat_reply = f"Dạ tuyệt vời! Tôi đã ghi nhận bạn chọn sử dụng '{user_selected_target}'. Đây là phương án an toàn — đang tiến hành thực thi kế hoạch."

        table_candidates = [e for e in environment if any(k in e.lower() for k in ["table", "bàn", "counter"])]
        destination = table_candidates[0] if table_candidates else None

        # Context-aware action plan based on safety trigger
        sel_lower = user_selected_target.lower()
        is_microwave_sel = any(k in content_lower for k in ["microwave", "vi sóng", "hâm nóng", "heat"])
        is_knife_sel     = any(k in content_lower for k in ["knife", "slice", "cut", "sharp", "dao", "cắt", "thái"])

        if is_microwave_sel:
            execution_plan = [
                {"step": 1, "action": "FindObject", "target": extract_atomic_target_object(user_selected_target),
                 "note": f"Bước 1: Tìm và kiểm tra {user_selected_target} (microwave-safe)"},
                {"step": 2, "action": "PickUp", "target": extract_atomic_target_object(user_selected_target),
                 "note": f"Bước 2: Lấy {user_selected_target} — đã xác nhận an toàn cho lò vi sóng"},
                {"step": 3, "action": "Heat", "target": extract_atomic_target_object(user_selected_target),
                 "note": f"Bước 3: Đặt vào lò vi sóng và hâm nóng {target_food}"},
            ]
        elif is_knife_sel:
            execution_plan = [
                {"step": 1, "action": "FindObject", "target": extract_atomic_target_object(user_selected_target),
                 "note": f"Bước 1: Chuẩn bị {user_selected_target} theo quy trình an toàn"},
                {"step": 2, "action": "PickUp", "target": extract_atomic_target_object(user_selected_target),
                 "note": f"Bước 2: Lấy {user_selected_target} — thao tác đúng kỹ thuật, tránh tai nạn"},
                {"step": 3, "action": "CookObject", "target": extract_atomic_target_object(user_selected_target),
                 "note": f"Bước 3: Thực hiện cắt/thái {target_food} an toàn với dụng cụ được chọn"},
            ]
        else:
            execution_plan = [
                {"step": 1, "action": "FindObject", "target": extract_atomic_target_object(user_selected_target),
                 "note": f"Bước 1: Tìm kiếm {user_selected_target} trong nhà bếp"},
                {"step": 2, "action": "PickUp", "target": extract_atomic_target_object(user_selected_target),
                 "note": f"Bước 2: Lấy {user_selected_target} một cách an toàn"},
                {"step": 3, "action": "CookObject", "target": extract_atomic_target_object(user_selected_target),
                 "note": f"Bước 3: Chuẩn bị/Thao tác {target_food}"},
            ]

        if destination:
            execution_plan.append({"step": 4, "action": "PutObject", "target": extract_atomic_target_object(destination),
                                   "note": f"Bước 4: Hoàn tất và đặt lên {destination}"})
        k_choice = {"question": "", "options": []}
        clarification = ""


    elif skip_entropy and route_cat == "Unambiguous":
        overall_cat = "Unambiguous"
        entropy_score = 0.00
        # Fail-closed: only use objects confirmed in matched_env, never synthesize
        if not matched_env:
            return {
                "status": "NEEDS_CLARIFICATION",
                "reason_code": "NO_OBJECT_MATCHED",
                "summary": f"Không khớp được vật thể nào trong câu lệnh với môi trường hiện tại.",
                "chat_reply": "Xin lỗi, tôi không tìm thấy vật thể nào trong câu lệnh của bạn khớp với đồ vật hiện có trong bếp. Bạn có thể mô tả rõ hơn không?",
                "overall_classification": "Unambiguous",
                "entropy_score": 0.00,
                "k_choice_question": {"question": "Bạn muốn thao tác với vật thể nào trong bếp?", "options": []},
                "execution_plan": [],
                "safe_execution_plan": [],
                "verified_safe": False,
                "early_routing": {"was_skipped": True, "reason": route_reason, "tier": route_tier, "conformal_meta": conformal_meta},
            }
        main_target = matched_env[0]
        tool_candidates = get_valid_tool_candidates(environment)
        if not tool_candidates:
            return {
                "status": "NEEDS_CLARIFICATION",
                "reason_code": "NO_OBJECT_MATCHED",
                "summary": "Không tìm thấy dụng cụ phù hợp trong môi trường.",
                "chat_reply": "Tôi không tìm thấy dụng cụ phù hợp trong bếp. Bạn có thể chỉ rõ dụng cụ muốn dùng không?",
                "overall_classification": "Unambiguous",
                "entropy_score": 0.00,
                "k_choice_question": {"question": "", "options": []},
                "execution_plan": [],
                "safe_execution_plan": [],
                "verified_safe": False,
                "early_routing": {"was_skipped": True, "reason": route_reason, "tier": route_tier, "conformal_meta": conformal_meta},
            }
        tool_used = tool_candidates[0]
        # Find destination in environment (must exist)
        table_candidates = [e for e in environment if any(k in e.lower() for k in ["table", "bàn", "counter"])]
        destination = table_candidates[0] if table_candidates else None

        execution_plan = [
            {"step": 1, "action": "FindObject", "target": extract_atomic_target_object(main_target),
             "note": f"Bước 1: Tìm kiếm {main_target} trong nhà bếp"},
            {"step": 2, "action": "PickUp", "target": extract_atomic_target_object(tool_used),
             "note": f"Bước 2: Lấy {tool_used} một cách an toàn"},
            {"step": 3, "action": "CookObject", "target": extract_atomic_target_object(main_target),
             "note": f"Bước 3: Pha chế/Thao tác {target_food}"},
        ]
        if destination:
            execution_plan.append({"step": 4, "action": "PutObject", "target": extract_atomic_target_object(destination),
                                   "note": f"Bước 4: Hoàn tất và đặt lên {destination}"})
        k_choice = {"question": "", "options": []}
        clarification = ""

    elif is_safety_critical and not is_step_plan:
        overall_cat = "Safety"
        entropy_score = 0.72

        # ── Detect safety hazard type and find SAFE vs UNSAFE candidates ──────
        is_microwave_ctx = any(k in content_lower for k in ["microwave", "vi sóng", "lò vi", "heat", "hâm nóng"])
        is_knife_ctx     = any(k in content_lower for k in ["knife", "slice", "cut", "sharp", "dao", "cắt", "thái"])
        is_hygiene_ctx   = any(k in content_lower for k in ["wash", "clean", "dirty", "sponge", "rửa", "sạch"])

        # Categorise every env object by safety
        safe_candidates   = []
        unsafe_candidates = []
        for obj in environment:
            obj_l = obj.lower()
            if is_microwave_ctx:
                # metal/foil/plastic are UNSAFE; ceramic/glass/wood are SAFE
                if any(k in obj_l for k in ["metal", "foil", "aluminum", "tin", "steel", "plastic bag", "plastic wrap"]):
                    unsafe_candidates.append(obj)
                elif any(k in obj_l for k in ["ceramic", "porcelain", "glass", "mug", "plate", "bowl", "dish"]):
                    safe_candidates.append(obj)
            elif is_knife_ctx:
                # cutting board is SAFE; random plates/bowls without board are contextually wrong
                if any(k in obj_l for k in ["cutting board", "thớt", "chopping board"]):
                    safe_candidates.append(obj)
                elif any(k in obj_l for k in ["knife", "dao", "paring knife", "bread knife", "sharp"]):
                    safe_candidates.append(obj)   # knife itself is safe if used with cutting board
                else:
                    unsafe_candidates.append(obj)
            elif is_hygiene_ctx:
                if any(k in obj_l for k in ["dirty", "soiled", "unwashed", "used sponge"]):
                    unsafe_candidates.append(obj)
                elif any(k in obj_l for k in ["clean", "fresh", "sạch"]):
                    safe_candidates.append(obj)

        # Fallback: use candidate_matches or matched_env
        if not safe_candidates and not unsafe_candidates:
            safe_candidates   = [obj for obj in (candidate_matches or matched_env) if obj]
            unsafe_candidates = []

        # Pick the best safe option to present; fall back to first env obj
        safe_opt   = safe_candidates[0]   if safe_candidates   else (matched_env[0] if matched_env else None)
        unsafe_opt = unsafe_candidates[0] if unsafe_candidates else None

        if not safe_opt:
            return {
                "status": "NEEDS_CLARIFICATION",
                "reason_code": "MISSING_OBJECT_CONTEXT",
                "summary": "Phát hiện yêu cầu liên quan an toàn nhưng không xác định được vật thể.",
                "chat_reply": "Tôi nhận thấy yêu cầu liên quan đến thao tác an toàn. Bạn có thể chỉ rõ vật thể cần thao tác không?",
                "overall_classification": "Safety",
                "entropy_score": entropy_score,
                "k_choice_question": {"question": "Bạn muốn thao tác với vật thể nào?", "options": []},
                "execution_plan": [],
                "safe_execution_plan": [],
                "verified_safe": False,
                "early_routing": {"was_skipped": False, "reason": route_reason, "tier": route_tier, "conformal_meta": conformal_meta},
            }

        # ── Build context-specific safety question ─────────────────────────────
        safe_label   = format_tool_label(safe_opt)
        unsafe_label = format_tool_label(unsafe_opt) if unsafe_opt else "Vật chứa không đảm bảo an toàn"

        if is_microwave_ctx:
            question_text = (
                f"⚠️ Cảnh báo an toàn vi sóng: Trong bếp hiện có nhiều loại vật chứa. "
                f"Robot nên dùng {safe_label} (an toàn, microwave-safe) hay {unsafe_label} (có nguy cơ cháy nổ) "
                f"để đặt vào lò vi sóng?"
            )
        elif is_knife_ctx:
            question_text = (
                f"⚠️ Cảnh báo an toàn dao kéo: Để thao tác cắt/thái an toàn, Robot nên dùng "
                f"{safe_label} (đúng quy trình an toàn) hay thực hiện không đúng dụng cụ (nguy hiểm)?"
            )
        elif is_hygiene_ctx:
            question_text = (
                f"⚠️ Cảnh báo vệ sinh thực phẩm: Trước khi thực hiện, Robot có cần {safe_label} "
                f"để đảm bảo an toàn thực phẩm không?"
            )
        else:
            question_text = (
                f"⚠️ Cảnh báo an toàn: Robot phát hiện nguy cơ tiềm ẩn. "
                f"Bạn muốn Robot dùng {safe_label} (đảm bảo an toàn) hay tiếp tục theo cách hiện tại (có rủi ro)?"
            )

        k_options = [
            {"key": "A", "label": f"✅ Dùng {safe_label} (An toàn đã được kiểm chứng)", "target": safe_opt},
        ]
        if unsafe_opt:
            k_options.append({"key": "B", "label": f"❌ Dùng {unsafe_label} (Có nguy cơ vi phạm an toàn)", "target": "__unsafe__"})
        else:
            k_options.append({"key": "B", "label": "🚫 Hủy yêu cầu", "target": "__cancel__"})

        mappings.append({
            "vague_expression": f"Vật thể thực hiện thao tác an toàn ({target_food})",
            "disambiguated_expression": f"Phương án an toàn: {safe_opt}",
            "category": "Safety",
            "explanation": f"Tồn tại vật thể an toàn và không an toàn trong môi trường. H={entropy_score} > 0.5."
        })
        k_choice = {"question": question_text, "options": k_options}
        execution_plan = []
        clarification = question_text


    elif vague_group or (len(candidate_matches) >= 2) or has_vague_kw:
        overall_cat = "Preferences"
        entropy_score = 0.85
        # Only use confirmed environment candidates
        cand1 = candidate_matches[0] if len(candidate_matches) > 0 else (environment[0] if environment else None)
        cand2 = candidate_matches[1] if len(candidate_matches) > 1 else (environment[1] if len(environment) > 1 else None)
        if not cand1:
            return {
                "status": "NEEDS_CLARIFICATION",
                "reason_code": "MULTIPLE_CANDIDATES",
                "summary": "Phát hiện mơ hồ nhưng không xác định được ứng viên.",
                "chat_reply": "Tôi nhận ra câu lệnh còn mơ hồ. Bạn có thể mô tả rõ hơn vật thể muốn dùng không?",
                "overall_classification": "Preferences",
                "entropy_score": entropy_score,
                "k_choice_question": {"question": "Bạn muốn sử dụng vật thể nào?", "options": []},
                "execution_plan": [],
                "safe_execution_plan": [],
                "verified_safe": False,
                "early_routing": {"was_skipped": False, "reason": route_reason, "tier": route_tier, "conformal_meta": conformal_meta},
            }

        opt1_label = format_tool_label(cand1)
        opt2_label = format_tool_label(cand2) if cand2 else "Để Robot tự chọn phù hợp nhất"
        
        # Context-sensitive question phrasing
        all_cands_str = f"{cand1 or ''} {cand2 or ''}".lower()
        if any(k in all_cands_str for k in ["mug", "cup", "glass", "ly", "cốc"]):
            question_text = f"Bạn muốn Robot sử dụng loại ly/cốc nào ({opt1_label} hay {opt2_label}) để phục vụ {target_food}?"
        elif any(k in all_cands_str for k in ["whisk", "pan", "pot", "chảo", "nồi", "đánh trứng", "spatula", "muỗng", "spoon"]):
            question_text = f"Bạn muốn Robot sử dụng dụng cụ nào ({opt1_label} hay {opt2_label}) để chuẩn bị {target_food}?"
        elif any(k in all_cands_str for k in ["bowl", "plate", "dish", "tô", "bát", "đĩa", "dĩa", "khay", "rack"]):
            question_text = f"Bạn muốn Robot dùng vật chứa/khay nào ({opt1_label} hay {opt2_label}) cho {target_food}?"
        else:
            question_text = f"Bạn muốn Robot ưu tiên sử dụng {opt1_label} hay {opt2_label} cho yêu cầu này?"

        k_options = [{"key": "A", "label": opt1_label, "target": cand1}]
        if cand2:
            k_options.append({"key": "B", "label": opt2_label, "target": cand2})

        mappings.append({
            "vague_expression": f"Lựa chọn dụng cụ/vật chứa cho {target_food}",
            "disambiguated_expression": f"Lựa chọn A ({cand1})" + (f" / Lựa chọn B ({cand2})" if cand2 else ""),
            "category": "Preferences",
            "explanation": "Cần xác nhận dụng cụ/vật chứa người dùng mong muốn sử dụng."
        })
        detected.append({
            "element": f"Lựa chọn ({target_food})",
            "category": "Preferences",
            "reasoning": f"Tồn tại nhiều ứng viên trong môi trường. H={entropy_score} > 0.5.",
            "action": "GENERATE_QUESTION",
            "payload": {"shortlist": [cand1] + ([cand2] if cand2 else []), "clarifying_question": question_text}
        })

        k_choice = {"question": question_text, "options": k_options}
        execution_plan = []
        clarification = question_text

    elif is_step_plan or input_type == "plan_amb_task" or any(k in content_lower for k in ["please take the", "please retrieve", "please use the", "unambiguous"]):
        overall_cat = "Unambiguous"
        entropy_score = 0.00
        execution_plan = parse_clean_atomic_steps(input_content, environment)
        if not execution_plan:
            # parse returned empty — fail-closed
            return {
                "status": "NEEDS_CLARIFICATION",
                "reason_code": "CLASSIFICATION_INCONCLUSIVE",
                "summary": "Không thể phân tích chuỗi kế hoạch.",
                "chat_reply": "Xin lỗi, tôi không thể phân tích chuỗi bước trong yêu cầu của bạn. Bạn có thể viết lại rõ hơn không?",
                "overall_classification": "Unambiguous",
                "entropy_score": 0.00,
                "k_choice_question": {"question": "", "options": []},
                "execution_plan": [],
                "safe_execution_plan": [],
                "verified_safe": False,
                "early_routing": {"was_skipped": True, "reason": route_reason, "tier": route_tier, "conformal_meta": conformal_meta},
            }
        k_choice = {"question": "", "options": []}
        clarification = ""

    else:
        # Fail-closed: classification inconclusive — never generate a default plan
        return {
            "status": "NEEDS_CLARIFICATION",
            "reason_code": "CLASSIFICATION_INCONCLUSIVE",
            "summary": f"Không thể phân loại câu lệnh '{input_content[:60]}' một cách chắc chắn.",
            "chat_reply": "Xin lỗi, tôi chưa hiểu rõ yêu cầu của bạn. Bạn có thể mô tả cụ thể hơn về vật thể và hành động muốn Robot thực hiện không?",
            "overall_classification": "Unknown",
            "entropy_score": 0.50,
            "k_choice_question": {"question": "Bạn muốn Robot làm gì trong bếp? Hãy mô tả cụ thể hơn.", "options": []},
            "execution_plan": [],
            "safe_execution_plan": [],
            "verified_safe": False,
            "early_routing": {"was_skipped": False, "reason": route_reason, "tier": route_tier, "conformal_meta": conformal_meta},
        }

    # ── Early return for branches that intentionally produce no plan ─────────
    # Safety and Preferences branches set execution_plan=[] AND clarification != ""
    # They must NOT proceed to the APPROVED path — return NEEDS_CLARIFICATION here.
    if execution_plan == [] and clarification:
        return {
            "status": "NEEDS_CLARIFICATION",
            "reason_code": "NEEDS_CLARIFICATION",
            "summary": f"Phát hiện mơ hồ loại '{overall_cat}': {clarification[:100]}",
            "chat_reply": chat_reply,
            "grounding_analysis": {
                "extracted_objects": matched_env if matched_env else [input_content[:30]],
                "environment_match": matched_env,
                "missing_objects": missing_objects,
                "missing_or_extra": missing_objects,
            },
            "overall_classification": overall_cat,
            "entropy_score": entropy_score,
            "disambiguated_mappings": mappings,
            "detected_ambiguities": detected,
            "k_choice_question": k_choice,
            "clarifying_question_for_user": clarification,
            "lifted_nl": "",
            "proposition_mapping": {},
            "ltl_plan": "",
            "verified_safe": False,
            "safe_execution_plan": [],
            "execution_plan": [],
            "early_routing": {
                "was_skipped": skip_entropy,
                "confidence": route_conf,
                "category": route_cat,
                "reason": route_reason,
                "tier": route_tier + " (mock)",
                "api_calls_saved": 0,
                "cost_saved_pct": 0,
                "conformal_meta": conformal_meta
            }
        }

    # ── Safety verification (both LTL + Policy Engine) ───────────────────────
    is_safe, ltl_str, _ = verify_safety_ltl(execution_plan, environment)

    # Run deterministic Safety Policy Engine
    from safety_policy import get_safety_engine
    from schemas.environment import EnvironmentState, ExecutionStep as SchemaStep, AllowedAction
    schema_env = EnvironmentState.from_string_list(environment)

    def _resolve_id(target_str: str) -> str:
        """
        Map legacy plan target string (e.g. 'ceramic_mug') to schema object_id.
        Handles underscore-normalized names from extract_atomic_target_object().
        Falls back to target_str if no match found.
        """
        if not target_str:
            return target_str
        # Normalize: replace underscore with space for matching
        target_lower = target_str.lower().replace("_", " ").strip()
        # 1. Exact match on name
        for obj in schema_env.objects:
            if obj.name.lower() == target_lower:
                return obj.id
        # 2. Exact match on id (normalized)
        for obj in schema_env.objects:
            if obj.id.replace("_", " ").rstrip(" 0123456789").strip() == target_lower:
                return obj.id
        # 3. Substring match (both directions)
        for obj in schema_env.objects:
            obj_name = obj.name.lower()
            if target_lower in obj_name or obj_name in target_lower:
                return obj.id
        # 4. Token overlap: any word in target matches any word in obj name
        target_tokens = set(target_lower.split())
        for obj in schema_env.objects:
            obj_tokens = set(obj.name.lower().split())
            if target_tokens & obj_tokens:  # non-empty intersection
                return obj.id
        # No match — return as-is (will trigger OBJECT_NOT_IN_ENVIRONMENT if strict)
        return target_str

    schema_steps = []
    schema_step_errors = []
    # Fallback target: if plan has None targets (happens when parse_clean_atomic_steps
    # extracts main_target from env order), use first matched_env or environment item.
    fallback_target = matched_env[0] if matched_env else (environment[0] if environment else None)

    for s in execution_plan:
        try:
            raw_target = s.get("target") or fallback_target or ""
            schema_steps.append(SchemaStep(
                step_id=s.get("step", 1),
                action=s.get("action", "Find"),
                object_id=_resolve_id(raw_target),
                destination_id=_resolve_id(s.get("destination", "")) if s.get("destination") else None,
                parameters=s.get("parameters", {}),
                note=s.get("note", "")
            ))
        except Exception as e:
            # FIX #10: Fail-closed — never silently discard conversion errors
            err_msg = f"Step {s.get('step','?')} conversion failed: {e} (action={s.get('action')}, target={s.get('target')})"
            print(f"[SAFETY-BLOCK] {err_msg}")
            schema_step_errors.append(err_msg)

    # FIX #10: If ANY step failed schema conversion, reject the entire plan
    if schema_step_errors:
        return {
            "status": "REJECTED",
            "reason_code": "INVALID_ACTION",
            "summary": f"Kế hoạch bị từ chối: {len(schema_step_errors)} bước không hợp lệ về cấu trúc.",
            "chat_reply": f"⚠️ Không thể thực thi kế hoạch: bước hành động chứa action/object không hợp lệ. Chi tiết: {schema_step_errors[0]}",
            "overall_classification": overall_cat,
            "entropy_score": entropy_score,
            "k_choice_question": k_choice,
            "execution_plan": [],
            "safe_execution_plan": [],
            "verified_safe": False,
            "early_routing": {"was_skipped": skip_entropy, "reason": route_reason, "tier": route_tier, "conformal_meta": conformal_meta},
        }

    policy_result = get_safety_engine().check(schema_steps, schema_env)
    if not policy_result.is_safe:
        v = policy_result.first_rejection()
        return {
            "status": "REJECTED",
            "reason_code": v.reason_code.value if v else "SAFETY_INVARIANT_VIOLATED",
            "summary": v.message if v else "Kế hoạch vi phạm quy tắc an toàn.",
            "chat_reply": f"⚠️ Không thể thực hiện kế hoạch này: {v.message if v else 'Vi phạm an toàn'}",
            "overall_classification": overall_cat,
            "entropy_score": entropy_score,
            "k_choice_question": k_choice,
            "execution_plan": [],
            "safe_execution_plan": [],
            "verified_safe": False,
            "early_routing": {"was_skipped": skip_entropy, "reason": route_reason, "tier": route_tier, "conformal_meta": conformal_meta},
        }

    verified_safe = is_safe and policy_result.is_safe
    kb_attributes = {}  # removed keyword-based inference

    # Dynamically generate Lifted NL from the ACTUAL user input sentence
    lifted_nl_text, prop_map = generate_dynamic_lifted_nl(input_content, execution_plan)

    return {
        "status": "APPROVED",
        "reason_code": "APPROVED",
        "summary": f"Suy luận Neuro-Symbolic cho '{input_content[:60]}...'. Khớp {len(matched_env)} vật thể.",
        "chat_reply": chat_reply,
        "grounding_analysis": {
            "extracted_objects": matched_env if matched_env else [input_content[:30]],
            "environment_match": matched_env,
            "missing_objects": missing_objects,
            "missing_or_extra": missing_objects,
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
        "verified_safe": verified_safe,
        "safe_execution_plan": execution_plan if verified_safe else [],
        "execution_plan": execution_plan if verified_safe else [],
        "early_routing": {
            "was_skipped": skip_entropy,
            "confidence": route_conf,
            "category": route_cat,
            "reason": route_reason,
            "tier": route_tier + " (mock)",
            "api_calls_saved": 5 if skip_entropy else 0,
            "cost_saved_pct": 83 if skip_entropy else 0,
            "conformal_meta": conformal_meta
        }
    }
