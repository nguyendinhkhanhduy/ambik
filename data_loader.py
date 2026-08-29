import os
import json
import csv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AMBIK_LOCAL_CSV = os.path.join(BASE_DIR, "AmbiK-dataset", "AmbiK_data.csv")
AMBIK_TEST_400_CSV = os.path.join(BASE_DIR, "AmbiK-dataset", "ambik_dataset", "ambik_test_400.csv")
AMBIK_CALIB_100_CSV = os.path.join(BASE_DIR, "AmbiK-dataset", "ambik_dataset", "ambik_calib_100.csv")

def get_ambik_csv_path():
    """Returns the available path to the AmbiK dataset CSV."""
    for p in [AMBIK_LOCAL_CSV, AMBIK_TEST_400_CSV, AMBIK_CALIB_100_CSV]:
        if os.path.exists(p):
            return p
    return None


def get_entity_attributes(entity_name: str) -> dict:
    """
    Pure NLP Dynamic Physical Attribute Extraction from AmbiK environment text.
    Infers physical properties, affordances, and safety attributes directly from textual tokens.
    """
    name_clean = entity_name.lower().strip()
    
    is_metal = any(k in name_clean for k in ["metal", "steel", "iron", "aluminum", "foil", "knife", "fork", "pan", "pot", "skillet", "can", "tin", "spoon"])
    is_plastic = any(k in name_clean for k in ["plastic", "bag", "wrap", "container", "bottle"])
    is_glass = any(k in name_clean for k in ["glass", "jar", "bottle", "cup"])
    is_ceramic = any(k in name_clean for k in ["ceramic", "porcelain", "mug", "plate", "bowl", "dish"])
    is_dirty = any(k in name_clean for k in ["dirty", "used", "unwashed", "soiled", "sponge"])
    
    material = "metal" if is_metal else ("plastic" if is_plastic else ("glass" if is_glass else ("ceramic" if is_ceramic else "unknown")))
    
    return {
        "material": material,
        "is_clean": not is_dirty,
        "location": "kitchen_table",
        "microwave_safe": not (is_metal or (is_plastic and "microwave" not in name_clean))
    }


def load_ambik_samples(category: str = "all", limit: int = 60) -> list:
    """
    Load structured benchmark samples from official AmbiK dataset CSV.
    Categories: 'all', 'preferences', 'common_sense_knowledge', 'safety', 'unambiguous'.
    """
    csv_path = get_ambik_csv_path()
    if not csv_path or not os.path.exists(csv_path):
        return []

    try:
        samples = []
        with open(csv_path, mode='r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader):
                amb_type = str(row.get('ambiguity_type', 'preferences')).strip().lower()
                
                # Filter by category if specified
                if category != "all":
                    if category == "unambiguous":
                        pass  # handled below
                    elif category not in amb_type:
                        continue

                env_short = [item.strip() for item in str(row.get('environment_short', '')).split(',') if item.strip()]
                env_full = [item.strip() for item in str(row.get('environment_full', '')).split(',') if item.strip()]
                env_list = env_full if env_full else env_short
                if not env_list:
                    env_list = ["a ceramic mug", "a glass mug", "coffee machine", "milk", "kitchen table"]

                task_id = str(row.get('id', idx + 1))
                amb_task = str(row.get('ambiguous_task', '')).strip()
                unamb_task = str(row.get('unambiguous_direct', '')).strip()
                question = str(row.get('question', '')).strip()
                answer = str(row.get('answer', '')).strip()

                plan_amb = str(row.get('plan_for_amb_task', '')).strip()
                plan_clear = str(row.get('plan_for_clear_task', '')).strip()

                # Add ambiguous task sample
                if category != "unambiguous" and amb_task:
                    samples.append({
                        "id": f"{task_id}_amb",
                        "task_type": "ambiguous",
                        "instruction": amb_task,
                        "unambiguous_direct": unamb_task,
                        "ambiguity_type": amb_type,
                        "question": question,
                        "answer": answer,
                        "environment": env_list,
                        "user_intent": str(row.get('user_intent', '')),
                        "plan_for_amb_task": plan_amb
                    })

                # Add unambiguous counterpart sample for testing Fast Route
                if (category == "all" or category == "unambiguous") and unamb_task:
                    samples.append({
                        "id": f"{task_id}_clear",
                        "task_type": "unambiguous",
                        "instruction": unamb_task,
                        "unambiguous_direct": unamb_task,
                        "ambiguity_type": "unambiguous",
                        "question": "",
                        "answer": "",
                        "environment": env_list,
                        "user_intent": "Direct unambiguous instruction",
                        "plan_for_amb_task": plan_clear
                    })

                if len(samples) >= limit:
                    break

        return samples
    except Exception as e:
        print(f"Error loading AmbiK samples from {csv_path}: {e}")
        return []


if __name__ == "__main__":
    p = get_ambik_csv_path()
    print(f"AmbiK CSV Path: {p}")
    samples = load_ambik_samples(limit=10)
    print(f"Loaded {len(samples)} benchmark samples from AmbiK dataset.")
