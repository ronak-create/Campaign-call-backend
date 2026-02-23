import json
import google.generativeai as genai
import os

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Initialize model with JSON response configuration
MODEL = genai.GenerativeModel(
    "gemini-2.0-flash",
    generation_config={"response_mime_type": "application/json"}
)

async def send_to_analysis_service(batch_payload: list) -> list:
    try:
        prompt = f"""
        Analyze these call transcripts. For each, extract:
        - call_sid
        - city (string or null)
        - interest (yes or no)
        - outcome (result of the call/if not eligible,why?)

        Transcripts: {json.dumps(batch_payload)}
        """

        # Use the async version of the generate method
        response = await MODEL.generate_content_async(prompt)

        # In JSON mode, response.text is guaranteed to be a valid JSON string
        return json.loads(response.text)

    except Exception as e:
        print(f"Gemini error: {e}")
        return []
