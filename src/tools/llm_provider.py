from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

import httpx


def get_provider() -> str:
    # MODEL_PROVIDER is the canonical name; LLM_PROVIDER kept for backward compat
    return os.getenv("MODEL_PROVIDER", os.getenv("LLM_PROVIDER", "mock")).strip().lower()


def is_enabled() -> bool:
    provider = get_provider()
    if provider in ("openai", "apim"):
        key = os.getenv("MODEL_API_KEY", os.getenv("OPENAI_API_KEY", "")).strip()
        auth_header = os.getenv("APIM_AUTH_HEADER", "").strip().lower()
        return bool(key) or auth_header == "none"
    return False


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name, "1" if default else "0").strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


def _extract_json_object(text: str) -> Optional[dict[str, Any]]:
    text = text.strip()
    if not text:
        return None

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None

    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def call_json(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.0,
    max_tokens: int = 1200,
) -> Optional[dict[str, Any]]:
    if not is_enabled():
        return None

    provider = get_provider()
    if provider not in ("openai", "apim"):
        return None

    # Core connection settings — canonical names with old-name fallbacks
    key = os.getenv("MODEL_API_KEY", os.getenv("OPENAI_API_KEY", "")).strip()
    base_url = os.getenv("MODEL_API_BASE", os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
    model = os.getenv("MODEL_NAME", os.getenv("LLM_MODEL", "gpt-4o-mini"))
    timeout_s = float(os.getenv("LLM_TIMEOUT_SECONDS", "20"))

    # Chat path — supports {model} template (e.g. /openai/custom/{model}/chat/completions)
    raw_path = os.getenv("APIM_PATH", os.getenv("OPENAI_CHAT_PATH", "/chat/completions")).strip()
    if not raw_path.startswith("/"):
        raw_path = f"/{raw_path}"
    chat_path = raw_path.replace("{model}", model)

    # Payload
    include_model = _env_flag("APIM_INCLUDE_MODEL_IN_BODY", default=True)
    payload: dict[str, Any] = {
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if include_model and model:
        payload["model"] = model

    # Headers
    headers: dict[str, str] = {"Content-Type": "application/json"}

    # Auth — APIM_AUTH_HEADER names the header (e.g. "api-key" or "Authorization")
    # APIM_AUTH_SCHEME optionally prefixes the key (e.g. "Bearer")
    auth_header = os.getenv("APIM_AUTH_HEADER", "").strip()
    auth_scheme = os.getenv("APIM_AUTH_SCHEME", "").strip()
    if auth_header and auth_header.lower() != "none" and key:
        headers[auth_header] = f"{auth_scheme} {key}".strip() if auth_scheme else key

    # Optional separate APIM subscription key header
    apim_sub_key = os.getenv("APIM_SUBSCRIPTION_KEY", "").strip()
    apim_sub_header = os.getenv("APIM_SUBSCRIPTION_HEADER", "Ocp-Apim-Subscription-Key").strip()
    if apim_sub_key and apim_sub_header:
        headers[apim_sub_header] = apim_sub_key

    # Extra custom headers (JSON object string)
    extra_raw = os.getenv("APIM_EXTRA_HEADERS", os.getenv("APIM_EXTRA_HEADERS_JSON", "")).strip()
    if extra_raw:
        try:
            extra = json.loads(extra_raw)
            if isinstance(extra, dict):
                for k, v in extra.items():
                    if str(k).strip() and v is not None:
                        headers[str(k)] = str(v)
        except Exception:
            pass

    # Query params
    params: dict[str, str] = {}
    api_version = os.getenv("APIM_API_VERSION", os.getenv("OPENAI_API_VERSION", "")).strip()
    if api_version:
        params["api-version"] = api_version

    try:
        with httpx.Client(timeout=timeout_s) as client:
            response = client.post(f"{base_url}{chat_path}", json=payload, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
    except Exception:
        return None

    content = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    if isinstance(content, list):
        text = "\n".join(str(chunk.get("text", "")) for chunk in content if isinstance(chunk, dict))
    else:
        text = str(content)
    return _extract_json_object(text)
