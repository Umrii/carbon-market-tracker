"""
LLM market insight via Google Gemini API.

Reads GEMINI_API_KEY from the environment (set in .env for local dev,
or as a Render environment variable in production).
"""

import os
import requests
from pathlib import Path


# ── Load .env for local development ────────────────────────────────────────

def _load_dotenv() -> None:
    """Parse .env in the project root and populate os.environ (local only)."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            val = val.strip().strip("'\"")
            os.environ.setdefault(key.strip(), val)


_load_dotenv()

# ── Gemini API ──────────────────────────────────────────────────────────────

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-3.5-flash:generateContent"
)


def get_market_insight(
    latest_price: float,
    change_pct: float,
    ma_7: float,
    ma_30: float,
    volatility: float,
) -> str:
    """
    Call the Gemini API and return a 2-3 sentence plain-English carbon
    market analyst summary based on the supplied price metrics.

    Returns an error string (never raises) so the dashboard always gets
    something displayable.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return "⚠️ GEMINI_API_KEY is not set. Add it to your .env file or Render environment variables."

    vs_ma7 = "above" if latest_price > ma_7 else "below"
    vs_ma30 = "above" if latest_price > ma_30 else "below"

    prompt = (
        "You are a senior EU ETS carbon market analyst. "
        "Write 3 sentences of professional market commentary in plain prose — no bullet points, no headers.\n\n"
        f"EU ETS data:\n"
        f"- EUA price: €{latest_price:.2f}/t ({change_pct:+.2f}% today)\n"
        f"- 7-day MA: €{ma_7:.2f}/t (price is {vs_ma7})\n"
        f"- 30-day MA: €{ma_30:.2f}/t (price is {vs_ma30})\n"
        f"- 20-day annualised volatility: {volatility:.1f}%\n\n"
        "Cover: (1) today's move and position vs moving averages, "
        "(2) what the MA spread implies about momentum, "
        "(3) what the volatility level suggests about near-term risk."
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 300, "temperature": 0.4},
    }

    try:
        resp = requests.post(
            _GEMINI_URL,
            params={"key": api_key},
            json=payload,
            timeout=(10, 30),  # (connect, read) in seconds
        )
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except requests.exceptions.HTTPError as e:
        return f"⚠️ Gemini API error ({e.response.status_code}): {e.response.text[:200]}"
    except Exception as e:
        return f"⚠️ Could not generate insight: {e}"
