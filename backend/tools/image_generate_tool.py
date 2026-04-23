from __future__ import annotations

from typing import Any

import requests

from app.core.config import settings


def _extract_by_path(payload: dict[str, Any], key_path: str) -> str:
    current: Any = payload
    for part in key_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return ""
        current = current[part]
    return current if isinstance(current, str) else ""


def _extract_image_url(payload: dict[str, Any]) -> str:
    configured = _extract_by_path(payload, settings.portrait_api_response_url_field)
    if configured:
        return configured

    direct_keys = ["image_url", "url", "image", "output_url"]
    for key in direct_keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    images = payload.get("images")
    if isinstance(images, list):
        for item in images:
            if isinstance(item, dict):
                value = item.get("url") or item.get("image_url") or item.get("path")
                if isinstance(value, str) and value.strip():
                    return value.strip()
            elif isinstance(item, str) and item.strip():
                return item.strip()

    return ""


def image_generate_tool(prompt: str, seed: int) -> dict[str, str]:
    """
    Input: prompt + seed
    Output: generated image URL and provider marker
    """
    if not settings.portrait_api_url:
        raise RuntimeError("PORTRAIT_API_URL is empty")

    headers = {"Content-Type": "application/json"}
    if settings.portrait_api_token:
        headers["Authorization"] = f"Bearer {settings.portrait_api_token}"

    payload = {
        settings.portrait_api_prompt_field: prompt,
        settings.portrait_api_seed_field: seed,
    }

    try:
        resp = requests.post(
            settings.portrait_api_url,
            json=payload,
            headers=headers,
            timeout=settings.portrait_api_timeout_seconds,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Portrait API request failed: {exc}") from exc

    if resp.status_code >= 400:
        text = resp.text.strip()[:500]
        raise RuntimeError(f"Portrait API returned {resp.status_code}: {text}")

    try:
        result = resp.json()
    except ValueError as exc:
        raise RuntimeError("Portrait API returned non-JSON payload") from exc

    if not isinstance(result, dict):
        raise RuntimeError("Portrait API returned unexpected payload")

    image_url = _extract_image_url(result)
    if not image_url:
        raise RuntimeError("Portrait API response does not contain image URL")

    return {
        "image_url": image_url,
        "generator": settings.portrait_generator_name,
    }
