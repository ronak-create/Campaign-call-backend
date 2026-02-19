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

def extract_transcript_from_session(data: dict) -> str:
    events = data.get("events") or []
    transcript_lines = []

    for event in events:
        if event.get("event_type") != "transcript":
            continue

        event_data = event.get("event_data") or []

        for segment in event_data:
            role = (segment.get("role") or "").strip().lower()
            content = (segment.get("content") or "").strip()

            if not content:
                continue

            if role == "user":
                prefix = "User"
            elif role == "assistant":
                prefix = "Assistant"
            else:
                continue  # skip unknown roles safely

            transcript_lines.append(f"{prefix}: {content}")

    return "\n".join(transcript_lines).strip()

import re

def clean_transcript(transcript: str) -> str:
    if not transcript:
        return ""

    cleaned_lines = []

    for line in transcript.split("\n"):
        line = line.strip()
        if not line:
            continue

        # Normalize whitespace
        line = re.sub(r"\s+", " ", line)

        # Ensure proper role formatting
        if line.lower().startswith("user:"):
            content = line[5:].strip()
            if content:
                cleaned_lines.append(f"User: {content}")

        elif line.lower().startswith("assistant:"):
            content = line[10:].strip()
            if content:
                cleaned_lines.append(f"Assistant: {content}")

    return "\n".join(cleaned_lines).strip()

