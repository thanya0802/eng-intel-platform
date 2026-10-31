"""Optional Gemini client. Every caller has a deterministic fallback, so the system runs
(and CI passes) without a key. Confirm the model name against current docs."""
import json
import re
import time
from . import config
from .telemetry import log

RETRYABLE = ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "DEADLINE_EXCEEDED")

def available():
    return config.USE_LLM

def with_retry(fn, attempts=4, base_delay=2.0, sleep=time.sleep):
    """Retry rate limits and transient errors with exponential backoff; raise anything else."""
    for i in range(attempts + 1):
        try:
            return fn()
        except Exception as e:
            if i == attempts or not any(code in str(e) for code in RETRYABLE):
                raise
            sleep(base_delay * (2 ** i))

def parse_json(text):
    """First JSON object in the reply; tolerates code fences and trailing text."""
    text = re.sub(r"^```(?:json)?", "", text.strip()).strip()
    start = text.find("{")
    if start < 0:
        raise ValueError(f"no JSON object in model reply: {text[:120]}")
    return json.JSONDecoder().raw_decode(text[start:])[0]

def generate_json(prompt, run_id=None, node="llm"):
    from google import genai
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    resp = with_retry(lambda: client.models.generate_content(
        model=config.GEMINI_MODEL, contents=prompt, config={"response_mime_type": "application/json", "temperature": 0}))
    usage = getattr(resp, "usage_metadata", None)
    log(run_id=run_id, node=node, model=config.GEMINI_MODEL,
        tokens_in=getattr(usage, "prompt_token_count", None),
        tokens_out=getattr(usage, "candidates_token_count", None))
    return parse_json(resp.text)
