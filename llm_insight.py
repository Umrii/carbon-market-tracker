"""
LLM market insight via Groq API.

Reads grok_key from the environment (set in .env for local dev,
or as a Render environment variable in production).
"""

import os
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


# ── Groq API ────────────────────────────────────────────────────────────────

def get_market_insight(
    latest_price: float,
    change_pct: float,
    ma_7: float,
    ma_30: float,
    volatility: float,
) -> str:
    """
    Call the Groq API and return a 3-sentence plain-English carbon
    market analyst summary based on the supplied price metrics.

    Returns an error string (never raises) so the dashboard always gets
    something displayable.
    """
    api_key = os.environ.get("grok_key", "").strip()
    if not api_key:
        return "⚠️ grok_key is not set. Add it to your .env file or Render environment variables."

    vs_ma7 = "above" if latest_price > ma_7 else "below"
    vs_ma30 = "above" if latest_price > ma_30 else "below"

    prompt = (
        f"EU ETS data:\n"
        f"- EUA price: €{latest_price:.2f}/t ({change_pct:+.2f}% today)\n"
        f"- 7-day MA: €{ma_7:.2f}/t (price is {vs_ma7})\n"
        f"- 30-day MA: €{ma_30:.2f}/t (price is {vs_ma30})\n"
        f"- 20-day annualised volatility: {volatility:.1f}%\n\n"
        "Write 3 sentences of professional market commentary covering today's price move "
        "and position vs moving averages, what the MA spread implies about momentum, "
        "and what the volatility level suggests about near-term risk."
    )

    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior EU ETS carbon market analyst. "
                        "Respond with plain prose only — no bullet points, no headers, no labels."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=1,
            max_completion_tokens=512,
            top_p=1,
            reasoning_effort="medium",
            stream=False,
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ Could not generate insight: {e}"
