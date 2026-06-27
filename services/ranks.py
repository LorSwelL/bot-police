import logging
import re
from typing import Dict, Tuple, Optional, Set

import discord
from config import Config

logger = logging.getLogger(__name__)

_ARROW_RE = re.compile(r"\s*(?:->|→|➡|⇒|=+>)\s*")


def _canon_rank(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _canon_transition_key(key: str) -> Optional[Tuple[str, str]]:
    key = (key or "").strip()
    if not key:
        return None

    parts = _ARROW_RE.split(key)
    if len(parts) != 2:
        return None

    a = _canon_rank(parts[0])
    b = _canon_rank(parts[1])
    if not a or not b:
        return None
    return a, b


def _parse_role_id(role_id) -> Optional[int]:
    try:
        return int(role_id)
    except Exception:
        logger.debug("ranks _parse_role_id: не удалось преобразовать role_id %r", role_id, exc_info=True)
        return None


def build_normalized_rank_mapping() -> Dict[Tuple[str, str], int]:
    raw = getattr(Config, "RANK_ROLE_MAPPING", {}) or {}
    normalized: Dict[Tuple[str, str], int] = {}

    for raw_key, role_id in raw.items():
        canon = _canon_transition_key(str(raw_key))
        if canon is None:
            continue

        rid = _parse_role_id(role_id)
        if rid is None:
            continue

        if canon in normalized and normalized[canon] != rid:
            logger.warning(
                "⚠️ Конфликт RANK_ROLE_MAPPING: '%s' уже %s, новый %s. Оставляю первый.",
                raw_key, normalized[canon], rid
            )
            continue

        normalized[canon] = rid

    return normalized


def _build_new_rank_to_role_id() -> Dict[str, int]:
    raw = getattr(Config, "RANK_ROLE_MAPPING", {}) or {}
    result: Dict[str, int] = {}

    for raw_key, role_id in raw.items():
        rid = _parse_role_id(role_id)
        if rid is None:
            continue
        key = str(raw_key).strip()
        canon = _canon_transition_key(key)
        if canon:
            new_canon = canon[1]
            if new_canon in result and result[new_canon] != rid:
                logger.warning(
                    "⚠️ RANK_ROLE_MAPPING: дубликат нового звания '%s' (роль %s и %s). Оставляем первый.",
                    new_canon, result[new_canon], rid
                )
            else:
                result[new_canon] = rid
        else:
            key_canon = _canon_rank(key)
            if key_canon:
                if key_canon in result and result[key_canon] != rid:
                    logger.warning(
                        "⚠️ RANK_ROLE_MAPPING: дубликат звания '%s' (роль %s и %s). Оставляем первый.",
                        key_canon, result[key_canon], rid
                    )
                else:
                    result[key_canon] = rid

    return result


def find_role_id_for_transition(transition: str) -> Optional[int]:
    if not (transition or "").strip():
        return None

    canon = _canon_transition_key(transition)
    if canon:
        mapping = build_normalized_rank_mapping()
        rid = mapping.get(canon)
        if rid is not None:
            return rid

    new_rank_map = _build_new_rank_to_role_id()
    return new_rank_map.get(_canon_rank(transition))

def parse_transition_to_new_rank(transition: str):
    canon = _canon_transition_key(transition)
    if canon:
        return canon[1]
    return _canon_rank(transition) or None


def get_all_rank_role_ids_from_mapping():
    ids_from_transitions = set(build_normalized_rank_mapping().values())
    ids_from_new_rank = set(_build_new_rank_to_role_id().values())
    return ids_from_transitions | ids_from_new_rank


def get_all_rank_names_from_mapping() -> Set[str]:
    names: Set[str] = set()
    raw = getattr(Config, "RANK_ROLE_MAPPING", {}) or {}
    for key in raw:
        text = str(key or "").strip()
        canon = _canon_transition_key(text)
        if canon:
            names.add(canon[0])
            names.add(canon[1])
        else:
            c = _canon_rank(text)
            if c:
                names.add(c)
    return names


def _build_role_id_to_display_name() -> Dict[int, str]:
    raw = getattr(Config, "RANK_ROLE_MAPPING", {}) or {}
    result: Dict[int, str] = {}
    for raw_key, role_id in raw.items():
        rid = _parse_role_id(role_id)
        if rid is None:
            continue
        key = str(raw_key).strip()
        for sep in ("->", "→", "➡", "⇒"):
            if sep in key:
                part = key.split(sep, 1)[-1].strip()
                if part:
                    result[rid] = part[0].upper() + part[1:] if len(part) > 1 else part.upper()
                break
        else:
            if key:
                result[rid] = key[0].upper() + key[1:] if len(key) > 1 else key.upper()
    return result


def get_member_rank_display(member: Optional[discord.Member]) -> str:
    if not member or not getattr(member, "roles", None):
        return ""
    all_rank_ids = set(getattr(Config, "ALL_RANK_ROLE_IDS", []) or [])
    all_rank_ids |= get_all_rank_role_ids_from_mapping()
    if not all_rank_ids:
        return ""
    role_to_name = _build_role_id_to_display_name()
    member_rank_roles = [r for r in member.roles if r.id in all_rank_ids]
    if not member_rank_roles:
        return ""
    top = max(member_rank_roles, key=lambda r: r.position)
    return role_to_name.get(top.id, top.name) or ""


def is_promotion_key_allowed_for_member(member: Optional[discord.Member], promotion_key: str) -> bool:
    if not member or not (promotion_key or "").strip():
        return False
    canon = _canon_transition_key(promotion_key)
    if not canon:
        return False
    from_rank_canon = canon[0]
    member_rank = get_member_rank_display(member)
    if not member_rank:
        return False
    return _canon_rank(member_rank) == from_rank_canon