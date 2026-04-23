from __future__ import annotations

import json
import re
from typing import Any

import requests

from app.core.config import settings


def _resolve_chat_url() -> str:
    base = (settings.openai_base_url or "").strip()
    if not base:
        return ""
    if base.endswith("/chat/completions"):
        return base
    return f"{base.rstrip('/')}/chat/completions"


def _extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts).strip()
    return ""


def _post_chat(payload: dict) -> dict:
    api_url = _resolve_chat_url()
    if not api_url:
        raise RuntimeError("OPENAI_BASE_URL is empty")
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is empty")

    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
        # Avoid rare broken gzip payloads from relay/upstream chain.
        "Accept-Encoding": "identity",
    }
    session = requests.Session()
    # Keep behavior aligned with host relay workaround and avoid broken local proxy env.
    session.trust_env = False
    response = session.post(
        api_url,
        headers=headers,
        json=payload,
        timeout=settings.llm_timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


def _extract_assistant_text(data: dict) -> str:
    content = data["choices"][0]["message"]["content"]
    text = _extract_text_content(content)
    if text:
        return text
    raise RuntimeError(f"LLM response parse failed: {json.dumps(data, ensure_ascii=False)[:500]}")


def _cn_numeral_to_int(token: str) -> int | None:
    if token.isdigit():
        return int(token)

    digits = {
        "零": 0,
        "〇": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    units = {"十": 10, "百": 100, "千": 1000}
    total = 0
    current = 0
    has_unit = False
    for ch in token:
        if ch in digits:
            current = digits[ch]
        elif ch in units:
            unit = units[ch]
            if current == 0:
                current = 1
            total += current * unit
            current = 0
            has_unit = True
        else:
            return None
    total += current
    if total == 0 and not has_unit:
        return None
    return total


def _contains_future_chapter_hint(answer: str, chapter_index: int) -> bool:
    for m in re.finditer(r"第([零〇一二两三四五六七八九十百千0-9]+)(?:回|章)", answer):
        token = m.group(1)
        value = _cn_numeral_to_int(token)
        if value is not None and value > chapter_index:
            return True
    return False


def request_roleplay_completion(
    *,
    role_name: str,
    role_style: str,
    persona_state: str,
    session_memory: str,
    user_message: str,
    chapter_index: int,
    evidence_snippets: list[str],
) -> str:
    evidence_block = "\n".join(f"- {snippet}" for snippet in evidence_snippets[:6]) or "- 无"
    persona_state = (persona_state or "暂无状态快照。").strip()
    session_memory = (session_memory or "暂无会话记忆。").strip()

    system_prompt = (
        "你是小说角色扮演助手，必须严格遵守：\n"
        "1) 只能依据证据回答，不得编造进度外剧情。\n"
        "2) 语气必须匹配角色设定，先共情再表达观点。\n"
        "3) 若证据不足，明确说明不确定，并继续陪伴交流。\n"
        "4) 回答自然有人味，不要模板化。"
    )
    user_prompt = (
        f"角色名：{role_name}\n"
        f"角色固定设定：{role_style}\n"
        f"角色状态快照：{persona_state}\n"
        f"本会话短期记忆：{session_memory}\n"
        f"读者进度：第{chapter_index}章\n"
        f"可用证据：\n{evidence_block}\n\n"
        f"读者消息：{user_message}\n\n"
        "请输出 120~260 字中文回复。"
    )
    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
    }
    data = _post_chat(payload)
    return _extract_assistant_text(data)


def guard_and_rewrite_answer(
    *,
    role_name: str,
    answer: str,
    chapter_index: int,
    evidence_snippets: list[str],
) -> tuple[str, bool, str]:
    if not settings.chat_guard_enabled:
        return answer, False, "guard_disabled"

    evidence_block = "\n".join(f"- {s}" for s in evidence_snippets[:6]) or "- 无"
    suspicious = _contains_future_chapter_hint(answer, chapter_index)
    if not suspicious and len(answer.strip()) >= 20:
        return answer, False, "safe_by_heuristic"

    system_prompt = (
        "你是防剧透校验器。"
        "判断回答是否超出用户当前阅读进度。"
        "只输出 JSON："
        '{"safe":true/false,"reason":"","rewrite":""}'
    )
    user_prompt = (
        f"角色：{role_name}\n"
        f"用户进度：第{chapter_index}章\n"
        f"证据：\n{evidence_block}\n\n"
        f"待校验回答：{answer}\n\n"
        "若不安全，请给出不剧透重写版本 rewrite。"
    )
    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
    }

    try:
        data = _post_chat(payload)
        text = _extract_assistant_text(data).strip()
        match = re.search(r"\{[\s\S]*\}", text)
        parsed = json.loads(match.group(0) if match else text)
        safe = bool(parsed.get("safe"))
        reason = str(parsed.get("reason") or "")
        rewrite = str(parsed.get("rewrite") or "").strip()
        if safe:
            return answer, False, reason or "safe"
        if rewrite:
            return rewrite, True, reason or "rewritten"
        return "基于你目前读到的章节，我先不剧透后续情节。我们可以继续聊你当下的感受。", True, reason or "blocked"
    except Exception:
        if suspicious:
            return "基于你目前读到的章节，我先不剧透后续情节。我们可以继续聊你当下的感受。", True, "guard_fallback_blocked"
        return answer, False, "guard_error_but_passed"


def check_llm_connectivity() -> dict[str, str | bool]:
    api_url = _resolve_chat_url()
    if not api_url:
        return {"ok": False, "reason": "OPENAI_BASE_URL is empty"}
    if not settings.openai_api_key:
        return {"ok": False, "reason": "OPENAI_API_KEY is empty"}

    payload = {
        "model": settings.openai_model,
        "messages": [{"role": "user", "content": "ping"}],
        "temperature": 0,
    }

    try:
        data = _post_chat(payload)
        ok = bool(data.get("choices"))
        return {"ok": ok, "api_url": api_url}
    except Exception as exc:  # noqa: PERF203
        return {"ok": False, "reason": str(exc), "api_url": api_url}
