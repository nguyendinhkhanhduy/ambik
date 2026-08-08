import os
import json
import pandas as pd

AMBIK_CSV_PATH = r"C:\Users\ADMIN\Downloads\LAB\Code\01.08.2026\AmbiK_data.csv"
KITCHEN_KB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kitchen_kb.json")

def load_kitchen_kb():
    """Load structured Kitchen Knowledge Base JSON."""
    if os.path.exists(KITCHEN_KB_PATH):
        try:
            with open(KITCHEN_KB_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading kitchen_kb.json: {e}")
    return {"kitchen_entities": []}

def get_entity_attributes(entity_name: str) -> dict:
    """Find entity attributes by name from kitchen_kb.json."""
    kb = load_kitchen_kb()
    name_clean = entity_name.lower().strip()
    
    for entity in kb.get("kitchen_entities", []):
        ent_name = entity.get("name", "").lower().strip()
        if ent_name in name_clean or name_clean in ent_name:
            return entity.get("attributes", {})
            
    # Default fallback properties
    return {
        "is_clean": True,
        "location": "kitchen_table",
        "microwave_safe": not ("metal" in name_clean or "plastic" in name_clean)
    }

def load_ambik_samples(limit: int = 50):
    """Load sample records from AmbiK dataset CSV."""
    if not os.path.exists(AMBIK_CSV_PATH):
        return []
    
    try:
        df = pd.read_csv(AMBIK_CSV_PATH, encoding='utf-8')
        df = df.fillna('')
        
        samples = []
        for idx, row in df.head(limit).iterrows():
            env_short = [item.strip() for item in str(row.get('environment_short', '')).split(',') if item.strip()]
            env_full = [item.strip() for item in str(row.get('environment_full', '')).split(',') if item.strip()]
            
            env_list = env_full if env_full else env_short
            if not env_list:
                env_list = ["a ceramic mug", "a glass mug", "coffee machine", "milk", "kitchen table"]
            
            samples.append({
                "id": str(row.get('id', idx + 1)),
                "unambiguous_direct": str(row.get('unambiguous_direct', '')),
                "ambiguity_type": str(row.get('ambiguity_type', 'preferences')).lower(),
                "amb_shortlist": str(row.get('amb_shortlist', '')),
                "ambiguous_task": str(row.get('ambiguous_task', '')),
                "question": str(row.get('question', '')),
                "answer": str(row.get('answer', '')),
                "plan_for_amb_task": str(row.get('plan_for_amb_task', '')),
                "plan_for_clear_task": str(row.get('plan_for_clear_task', '')),
                "environment": env_list,
                "user_intent": str(row.get('user_intent', ''))
            })
        return samples
    except Exception as e:
        print(f"Error loading AmbiK CSV: {e}")
        return []

if __name__ == "__main__":
    data = load_ambik_samples(5)
    print(f"Loaded {len(data)} samples successfully.")
    kb = load_kitchen_kb()
    print(f"Loaded {len(kb.get('kitchen_entities', []))} KB entities.")
