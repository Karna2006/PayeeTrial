"""Small, dependency-free OpenRouter client shared by document review and email polish."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_ID_RE = re.compile(r"^(?:[A-Za-z0-9._-]+/)?[A-Za-z0-9._-]+(?::[A-Za-z0-9._-]+)?$")


class OpenRouterError(RuntimeError):
    """Safe provider error suitable for display in the app."""


def chat_completion(*, api_key: str, model: str, messages: list[dict[str, Any]],
                    timeout: float = 60.0, response_format: dict | None = None,
                    max_tokens: int = 1200, temperature: float = 0.2) -> dict[str, Any]:
    """Call one configured model and sanitize provider/network failures."""
    if not isinstance(api_key, str) or not api_key.strip():
        raise OpenRouterError("OpenRouter is not configured. Add OPENROUTER_API_KEY to app secrets.")
    if (not isinstance(model, str) or len(model) > 160 or ".." in model
            or not MODEL_ID_RE.fullmatch(model)):
        raise OpenRouterError("OpenRouter model name is invalid.")
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        payload["response_format"] = response_format
    request = urllib.request.Request(
        API_URL, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        message = {
            400: "OpenRouter rejected the request. Check the configured model and request format.",
            401: "OpenRouter rejected the API key. Check OPENROUTER_API_KEY.",
            402: "OpenRouter reports that this model or account requires credits.",
            403: "OpenRouter denied access to this model or endpoint.",
            429: "OpenRouter free-tier rate limit reached. Wait and retry; the local result is unchanged.",
            502: "The selected OpenRouter model is temporarily unavailable. Retry shortly.",
            503: "The selected OpenRouter model is temporarily unavailable. Retry shortly.",
        }.get(exc.code, f"OpenRouter request failed (HTTP {exc.code}).")
        raise OpenRouterError(message) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise OpenRouterError("OpenRouter could not be reached from this app process.") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise OpenRouterError("OpenRouter returned an unreadable response.") from None
    if not isinstance(decoded, dict):
        raise OpenRouterError("OpenRouter returned an unreadable response.")
    return decoded


def response_text(response: dict[str, Any]) -> str:
    """Extract assistant text from common OpenAI-compatible response shapes."""
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise OpenRouterError("OpenRouter returned an incomplete response.") from None
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(item.get("text", "") for item in content
                       if isinstance(item, dict) and isinstance(item.get("text"), str)).strip()
    raise OpenRouterError("OpenRouter returned an incomplete response.")
