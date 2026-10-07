"""Quick test of cv_0001 without the HTTP server."""
import json, pathlib, sys, os
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(pathlib.Path(__file__).parent / ".env", override=True)

from agent import run_conversation

clinic_path = pathlib.Path.home() / "Downloads" / "swasthiq-front-desk-agent-starter-pack" / "clinic.json"
with open(clinic_path, encoding="utf-8") as f:
    clinic = json.load(f)

model = os.environ.get("AGENT_MODEL", "gemini-3.8-flash")
print(f"Model: {model}")
print(f"Key prefix: {os.environ.get('OPENAI_API_KEY','NOT SET')[:10]}")

result = run_conversation(
    conversation_id="cv_0001",
    today="2026-10-01",
    turns=[
        "Namaste, Dr. Rao ke saath appointment chahiye tha.",
        "Shanivaar subah, 3 tareekh.",
        "Main Harpreet Singh, number 9812200311.",
    ],
    clinic_data=clinic,
    model=model,
)

print(f"\nterminal_state : {result['terminal_state']}")
print(f"appointment_id : {result['appointment_id']}")
print(f"patient_id     : {result['patient_id']}")
print(f"tool_calls     : {[t['name'] for t in result['tool_calls']]}")
print(f"tokens         : {result['metrics']['tokens']}")
print(f"reply          : {result['reply'][:200]}")
