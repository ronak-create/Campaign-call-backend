import re

def extract_city_from_session(session: dict):
    intents = session.get("intents", [])
    
    # iterate from last → first (latest intent wins)
    for intent_obj in reversed(intents):
        if intent_obj.get("intent") == "CITY":
            reasoning = intent_obj.get("reasoning", "")
            
            # extract text inside single quotes
            match = re.search(r"'([^']+)'", reasoning)
            if match:
                return match.group(1).strip()
    
    return None
