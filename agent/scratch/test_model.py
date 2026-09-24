"""Quick test of available Groq models."""
import os, sys
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()
from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

for model_id in ["openai/gpt-oss-120b", "groq/compound", "qwen/qwen3.8-27b"]:
    try:
        r = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": 'Respond with ONLY valid JSON. No markdown.'},
                {"role": "user", "content": "My payment failed, transaction ID TXN_AUTO_001"},
            ],
            temperature=0.0,
            max_tokens=64,
        )
        print(f"  [{model_id}] OK: {r.choices[0].message.content[:100]!r}")
    except Exception as e:
        print(f"  [{model_id}] FAIL: {e}")
