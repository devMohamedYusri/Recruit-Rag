import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

def list_models():
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("No API key found in .env")
        return

    print(f"Using API Key: {api_key[:5]}...{api_key[-5:]}")
    
    try:
        client = genai.Client(api_key=api_key)
        print("Listing available models...")
        for m in client.models.list():
            if "generateContent" in (m.supported_generation_methods or []):
                print(f"Model: {m.name}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_models()
