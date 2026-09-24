"""
agent/llm_client.py
-------------------
Groq LLM wrapper (Llama 3.3 70B).

Architecture note: This module is intentionally thin. It is the ONLY place in
the codebase that talks to an external LLM. Two nodes use it:
  1. extract_intent  — parse user message → structured JSON
  2. respond         — generate final user-facing natural-language response

The policy_decision node NEVER imports or calls this module. That separation is
enforced by design — see policy_decision.py for the rationale.

Swapping to a different LLM provider means changing only this file.
Set GROQ_API_KEY in your .env file (or environment) before running.
"""

import os
import json
from typing import Any

from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Client instantiation
# ---------------------------------------------------------------------------
_GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not _GROQ_API_KEY:
    raise EnvironmentError(
        "GROQ_API_KEY is not set. "
        "Copy .env.example to .env and add your key from https://console.groq.com"
    )

_client = Groq(api_key=_GROQ_API_KEY)

# Model used for all calls.
# Verified available on this Groq account as of 2026-09.
# To check available models: from groq import Groq; Groq(api_key=KEY).models.list()
# Other options tried: llama-3.3-70b-versatile (404), openai/gpt-oss-120b (returns empty)
MODEL = "qwen/qwen3.8-27b"


def invoke(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.1,       # Low temperature for consistent structured outputs
    max_tokens: int = 512,
) -> str:
    """
    Send a chat completion request to Groq and return the raw text response.

    Parameters
    ----------
    system_prompt : str
        The system role message (task framing, output format instructions).
    user_prompt : str
        The user role message (the actual content to process).
    temperature : float
        Sampling temperature. Keep low (0.0–0.2) for structured extraction tasks.
    max_tokens : int
        Maximum tokens to generate. 512 is sufficient for both use cases.

    Returns
    -------
    str
        Raw text content of the LLM's response.

    Raises
    ------
    RuntimeError
        If the Groq API call fails after the retry. Callers should handle this
        gracefully (e.g., route to clarification node).
    """
    try:
        response = _client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        raise RuntimeError(f"Groq API call failed: {exc}") from exc


def invoke_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
) -> dict[str, Any]:
    """
    Like invoke(), but instructs the model to return JSON and parses the result.

    Used exclusively by extract_intent. The caller (extract_intent.py) then runs
    a second layer of Pydantic schema validation on the returned dict.

    Returns
    -------
    dict
        Parsed JSON dict. Returns {"error": "parse_failed"} if JSON parsing fails,
        so the caller can route to the clarification node rather than raising.
    """
    # Instruct the model to return only valid JSON, no markdown fences.
    augmented_system = (
        system_prompt
        + "\n\nCRITICAL: Respond with ONLY valid JSON. No markdown, no explanation, "
        "no code fences. The response must be parseable by json.loads()."
    )
    raw = invoke(augmented_system, user_prompt, temperature=temperature, max_tokens=256)

    # Strip accidental markdown fences if the model adds them despite instructions.
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "parse_failed", "raw_output": raw}
