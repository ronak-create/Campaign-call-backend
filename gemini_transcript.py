from google import genai
from google.genai import types
import json

# Initialize the modern client
client = genai.Client(api_key="AIzaSyDSFFJnU9pLxr8gLX89CNkrHSfmIPK6FMo")

transcript = """
Assistant: नमस्ते, मैं V R Catalyst से बात कर रही हूँ। क्या मैं आपसे बात कर सकती हूँ?
User: बताइए।
Assistant: ठीक है। क्या आप डिलीवरी जॉब की तलाश में हैं?
User: हाँ, मैं हूँ।
Assistant: ठीक है। आपकी उम्र क्या है?
User: मेरी उम्र 21 साल है, मेरे पास ड्राइविंग लाइसेंस भी है, मेरे पास पैन कार्ड भी है, मेरे पास बाइक की ओनरशिप भी है, मेरे पास बाइक भी है।
Assistant: ठीक है, आपकी उम्र इक्कीस साल है। आपके पास ड्राइविंग लाइसेंस, पैन कार्ड और बाइक भी है। बहुत अच्छे। आप किस शहर से हैं?
User: मैं वडोदरा से हूँ।
Assistant: ठीक है, आप वडोदरा से हैं। क्या आपके पास बैंक खाता है?
User: हाँ, बैंक खाता भी है।
Assistant: ठीक है, आपके पास बैंक खाता भी है। क्या आपके पास अपनी खुद की बाइक है या आप किसी और की बाइक इस्तेमाल करते हैं?
Assistant: ठीक है, आपके पास अपनी खुद की बाइक है। आपने जो जानकारी दी है, के अनुसार आप डिलीवरी पार्टनर बनने के लिए सभी शर्तों को पूरा करते हैं।
"""


def extract_data(text: str):
    try:
        # 2. Call generate_content (Latest GA method)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=text,
            config=types.GenerateContentConfig(
                # Use snake_case for the parameter name in Python SDK
                system_instruction="Return ONLY valid JSON with keys: city, is_interested (bool), outcome.",
                temperature=0.1,
                # Explicitly set JSON response mime type to prevent parsing errors
                response_mime_type="application/json"
            ),
        )

        # 3. Access response.text directly
        return json.loads(response.text)

    except Exception as e:
        print(f"Error: {e}")
        return None

result = extract_data(transcript)
print(json.dumps(result, indent=2), ensure_ascii=False)