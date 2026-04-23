from __future__ import annotations

import re
from urllib.parse import quote_plus
from typing import Any

import requests

from app.core.config import settings


def _fallback_short_prompt(raw_prompt: str) -> str:
    name_match = re.search(r"角色名：([^\n]+)", raw_prompt)
    name = name_match.group(1).strip() if name_match else "古典人物"
    return (
        f"{name}, ancient chinese portrait, hanfu, upper body, cinematic lighting, "
        "high detail, clean background"
    )


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

    for key in ["image_url", "url", "image", "output_url"]:
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
    if not settings.portrait_api_url:
        safe_prompt = quote_plus(_fallback_short_prompt(prompt))
        image_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?seed={seed}&width=768&height=1024&nologo=true"
        return {
            "image_url": image_url,
            "generator": "pollinations_fallback",
        }

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
