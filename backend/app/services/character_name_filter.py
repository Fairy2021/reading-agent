from __future__ import annotations

import re


_ZH_NAME_PATTERN = re.compile(r"^[\u4e00-\u9fff]{2,8}$")
_PUNCTUATION_PATTERN = re.compile(r"[\s,，。！？；：、\"'“”‘’（）()《》【】\[\]·]")
_PRONOUN_START = {"我", "你", "他", "她", "它", "咱", "俺", "吾", "余", "予"}

# Frequently mis-detected narrative fragments / generic nouns.
_NOISE_EXACT = {
    "众人",
    "众人都",
    "大家",
    "有人",
    "那人",
    "此人",
    "我们",
    "你们",
    "他们",
    "自己",
    "便说",
    "因说",
    "因笑",
    "都笑",
    "便问",
    "不知",
    "哪里知",
    "忙笑",
    "笑说",
    "又说",
    "便笑",
    "婆子",
    "丫头",
    "太监",
    "和尚",
    "老爷",
    "夫人",
    "太太",
    "老太太",
    "姑娘",
    "公子",
    "娘娘",
    "家的",
}

# Action/speech suffixes often attached to real names (e.g., 宝玉忙 / 凤姐说).
_ACTION_SUFFIX = {
    "说",
    "道",
    "问",
    "答",
    "笑",
    "叹",
    "喊",
    "叫",
    "想",
    "看",
    "听",
    "知",
    "忙",
    "又",
    "便",
    "哭",
    "骂",
    "喜",
    "惊",
}

_NOISE_SUBSTRINGS = (
    "便说",
    "因说",
    "都笑",
    "哪里知",
    "忙笑",
    "笑说",
    "只见",
    "只听",
    "忽见",
    "忽听",
)


def normalize_candidate_name(name: str) -> str:
    return _PUNCTUATION_PATTERN.sub("", (name or "")).strip()


def sanitize_character_name(name: str) -> str:
    """
    Normalize candidate name and strip 1-2 trailing action/speech chars.
    Example: 宝玉忙 -> 宝玉, 凤姐说 -> 凤姐
    """
    n = normalize_candidate_name(name)
    if not n:
        return ""

    trimmed = n
    for _ in range(2):
        if len(trimmed) >= 3 and trimmed[-1] in _ACTION_SUFFIX:
            trimmed = trimmed[:-1]
        else:
            break
    return trimmed


def is_noise_like_character_name(name: str) -> bool:
    raw = normalize_candidate_name(name)
    if not raw:
        return True

    n = sanitize_character_name(raw)
    if not n:
        return True

    if raw in _NOISE_EXACT or n in _NOISE_EXACT:
        return True

    if raw[0] in _PRONOUN_START and len(raw) <= 3:
        return True
    if n[0] in _PRONOUN_START and len(n) <= 3:
        return True

    if not _ZH_NAME_PATTERN.match(n):
        return True

    if any(token in n for token in _NOISE_SUBSTRINGS):
        return True

    if len(raw) <= 3 and raw[-1] in _ACTION_SUFFIX:
        return True

    if n.startswith("第") and ("回" in n or "章" in n):
        return True

    if n.endswith("家的") and len(n) <= 4:
        return True

    return False
