from __future__ import annotations

import json
import re
from typing import Any

import requests

from app.core.config import settings

CHARACTER_SYSTEM_PROMPT = (
    "你是小说信息抽取器。任务：从给定文本提取真实人物角色。\n"
    "规则：\n"
    "1) 只保留人物，排除动作词、代词、泛指词、旁白词。\n"
    "2) 合并别名（如 宝玉=贾宝玉）。\n"
    "3) 输出必须是 JSON 数组，不要 markdown，不要解释。\n"
    '4) 元素结构固定：{"name":"","aliases":[],"evidence":""}'
)

RELATION_SYSTEM_PROMPT = (
    "你是小说关系抽取器。任务：从给定文本提取人物关系。\n"
    "规则：\n"
    "1) source/target 必须是文本中可识别的人物名。\n"
    "2) relation_type 仅允许：亲属,朋友,对立,主仆,情感,同盟,其他。\n"
    "3) strength 为 1~5 的整数。\n"
    "4) 输出必须是 JSON 数组，不要 markdown，不要解释。\n"
    '5) 元素结构固定：{"source":"","target":"","relation_type":"","strength":3,"evidence":""}'
)

CARD_SYSTEM_PROMPT = (
    "你是小说人物角色卡生成器。"
    "请严格根据给定证据生成结构化角色卡，不得编造证据外剧情。"
    "输出必须是 JSON 对象，不要 markdown，不要解释。"
    '字段固定为：{"identity_summary":"","personality_summary":"","speaking_style":"","values_and_taboo":"","emotional_state":"","stance":"","current_goal":"","relation_snapshot":""}'
)


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
    session.trust_env = False
    response = session.post(
        api_url,
        headers=headers,
        json=payload,
        timeout=settings.llm_timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


def _try_parse_json_array(raw: str) -> list[dict[str, Any]]:
    text = raw.strip()
    if not text:
        return []

    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        array_match = re.search(r"\[[\s\S]*\]", text)
        if not array_match:
            return []
        data = json.loads(array_match.group(0))

    if isinstance(data, dict):
        for key in ("characters", "relations", "items", "data"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            return []
    if not isinstance(data, list):
        return []

    return [item for item in data if isinstance(item, dict)]


def _try_parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if not text:
        return {}

    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        obj_match = re.search(r"\{[\s\S]*\}", text)
        if not obj_match:
            return {}
        data = json.loads(obj_match.group(0))
    if not isinstance(data, dict):
        return {}
    return data


def extract_characters_from_text(text: str) -> list[dict[str, Any]]:
    user_prompt = (
        "请从下面文本提取人物角色。\n"
        '返回 JSON 数组，元素结构必须是 {"name":"","aliases":[],"evidence":""}。\n'
        "文本：\n"
        f"{text}"
    )

    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": CHARACTER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
    }
    data = _post_chat(payload)
    try:
        content = data["choices"][0]["message"]["content"]
        text_content = _extract_text_content(content)
    except Exception as exc:  # noqa: PERF203
        raise RuntimeError("LLM response parse failed") from exc

    raw_items = _try_parse_json_array(text_content)
    cleaned: list[dict[str, Any]] = []
    for item in raw_items:
        name = item.get("name")
        aliases = item.get("aliases") or []
        evidence = item.get("evidence") or ""
        if not isinstance(name, str):
            continue
        if not isinstance(aliases, list):
            aliases = []
        aliases = [a for a in aliases if isinstance(a, str)]
        if not isinstance(evidence, str):
            evidence = ""
        cleaned.append({"name": name, "aliases": aliases, "evidence": evidence})
    if not cleaned:
        raise RuntimeError("LLM returned empty/invalid character JSON")
    return cleaned


def extract_relationships_from_text(text: str) -> list[dict[str, Any]]:
    user_prompt = (
        "请从下面文本提取人物关系。\n"
        '返回 JSON 数组，元素结构必须是 {"source":"","target":"","relation_type":"","strength":3,"evidence":""}。\n'
        "文本：\n"
        f"{text}"
    )
    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": RELATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
    }
    data = _post_chat(payload)
    try:
        content = data["choices"][0]["message"]["content"]
        text_content = _extract_text_content(content)
    except Exception as exc:  # noqa: PERF203
        raise RuntimeError("LLM response parse failed") from exc

    raw_items = _try_parse_json_array(text_content)
    cleaned: list[dict[str, Any]] = []
    for item in raw_items:
        source = item.get("source")
        target = item.get("target")
        relation_type = item.get("relation_type") or item.get("relation")
        strength = item.get("strength")
        evidence = item.get("evidence") or ""
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        if not isinstance(relation_type, str):
            relation_type = "其他"
        try:
            strength_int = int(strength)
        except Exception:
            strength_int = 3
        strength_int = max(1, min(5, strength_int))
        if not isinstance(evidence, str):
            evidence = ""
        cleaned.append(
            {
                "source": source,
                "target": target,
                "relation_type": relation_type,
                "strength": strength_int,
                "evidence": evidence,
            }
        )
    return cleaned


def extract_character_card_from_evidences(
    *,
    name: str,
    evidence_list: list[str],
    mention_count: int,
    first_chapter_index: int | None,
) -> dict[str, str]:
    joined_evidence = "\n".join(f"- {s}" for s in evidence_list if s).strip()
    if not joined_evidence:
        raise RuntimeError("empty evidence list")

    user_prompt = (
        f"角色名：{name}\n"
        f"首次出现章节：{first_chapter_index or '未知'}\n"
        f"提及次数：{mention_count}\n"
        f"证据片段：\n{joined_evidence}\n\n"
        "请返回结构化角色卡 JSON。"
    )
    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": CARD_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
    }
    data = _post_chat(payload)
    try:
        content = data["choices"][0]["message"]["content"]
        text_content = _extract_text_content(content)
    except Exception as exc:  # noqa: PERF203
        raise RuntimeError("LLM response parse failed") from exc

    parsed = _try_parse_json_object(text_content)
    if not parsed:
        raise RuntimeError("LLM returned empty/invalid card JSON")

    fields = [
        "identity_summary",
        "personality_summary",
        "speaking_style",
        "values_and_taboo",
        "emotional_state",
        "stance",
        "current_goal",
        "relation_snapshot",
    ]
    result: dict[str, str] = {}
    for key in fields:
        value = parsed.get(key, "")
        if not isinstance(value, str):
            value = str(value) if value is not None else ""
        result[key] = value.strip()
    return result


def verify_character_candidates(name_list: list[str]) -> dict[str, bool]:
    """
    LLM-assisted post filtering for character candidates.
    Returns mapping: {candidate_name: is_real_character_name}
    """
    names = [n.strip() for n in name_list if isinstance(n, str) and n.strip()]
    names = list(dict.fromkeys(names))
    if not names:
        return {}

    system_prompt = (
        "You are a strict Chinese novel NER validator.\n"
        "Task: decide whether each candidate is a real character name.\n"
        "Reject verbs, narrative fragments, generic groups/pronouns, and malformed tokens.\n"
        "Return JSON object only. Keys are candidate strings, values are true/false."
    )
    user_prompt = "Candidates:\n" + "\n".join(f"- {n}" for n in names)

    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
    }
    data = _post_chat(payload)
    try:
        content = data["choices"][0]["message"]["content"]
        text_content = _extract_text_content(content)
    except Exception as exc:  # noqa: PERF203
        raise RuntimeError("LLM response parse failed") from exc

    parsed = _try_parse_json_object(text_content)
    if not parsed:
        raise RuntimeError("LLM returned empty/invalid verification JSON")

    result: dict[str, bool] = {}
    for name in names:
        value = parsed.get(name, False)
        if isinstance(value, bool):
            result[name] = value
        elif isinstance(value, (int, float)):
            result[name] = bool(value)
        elif isinstance(value, str):
            result[name] = value.strip().lower() in {"true", "yes", "1"}
        else:
            result[name] = False
    return result
