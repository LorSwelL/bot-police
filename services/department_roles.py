from __future__ import annotations

import discord
from config import Config


def get_chief_deputy_role_ids(dept: str) -> list[int]:
    mapping = {
        "grom": (Config.ROLE_CHIEF_GROM, Config.ROLE_DEPUTY_GROM),
        "pps": (Config.ROLE_CHIEF_PPS, Config.ROLE_DEPUTY_PPS),
        "osb": (Config.ROLE_CHIEF_OSB, Config.ROLE_DEPUTY_OSB),
        "orls": (Config.ROLE_CHIEF_ORLS, Config.ROLE_DEPUTY_ORLS),
    }
    pair = mapping.get((dept or "").strip().lower(), (0, 0))
    return [r for r in pair if r]


def get_dept_role_id(dept: str) -> int:
    mapping = {
        "grom": Config.ROLE_DEPT_GROM,
        "pps": Config.ROLE_DEPT_PPS,
        "osb": Config.ROLE_DEPT_OSB,
        "orls": Config.ROLE_DEPT_ORLS,
        "academy": getattr(Config, "ROLE_DEPT_ACADEMY", 0) or 0,
    }
    return mapping.get((dept or "").strip().lower(), 0) or 0


def get_rank_role_ids(dept: str) -> list[int]:
    mapping = {
        "grom": getattr(Config, "ROLE_RANK_GROM", None) or [],
        "pps": getattr(Config, "ROLE_RANK_PPS", None) or [],
        "osb": getattr(Config, "ROLE_RANK_OSB", None) or [],
        "orls": getattr(Config, "ROLE_RANK_ORLS", None) or [],
        "academy": getattr(Config, "ROLE_RANK_ACADEMY", None) or [],
    }
    ids = mapping.get((dept or "").strip().lower(), []) or []
    return [r for r in ids if r]


def get_dept_and_rank_roles(guild: discord.Guild, dept: str) -> tuple[list[discord.Role], list[discord.Role]]:
    dept_rid = get_dept_role_id(dept)
    rank_rids = get_rank_role_ids(dept)
    dept_roles = [guild.get_role(dept_rid)] if dept_rid and guild.get_role(dept_rid) else []
    rank_roles = [r for rid in rank_rids if (r := guild.get_role(rid))]
    return dept_roles, rank_roles


def get_all_dept_and_rank_roles(guild: discord.Guild) -> tuple[list[discord.Role], list[discord.Role]]:
    all_dept_roles: list[discord.Role] = []
    all_rank_roles: list[discord.Role] = []

    for dept in ("grom", "pps", "osb", "orls", "academy"):
        dept_roles, rank_roles = get_dept_and_rank_roles(guild, dept)
        all_dept_roles.extend(dept_roles)
        all_rank_roles.extend(rank_roles)

    def _unique(roles: list[discord.Role]) -> list[discord.Role]:
        seen = set()
        result: list[discord.Role] = []
        for r in roles:
            if not r:
                continue
            if r.id in seen:
                continue
            seen.add(r.id)
            result.append(r)
        return result

    return _unique(all_dept_roles), _unique(all_rank_roles)


def get_base_rank_role(guild: discord.Guild, dept: str) -> discord.Role | None:
    rank_rids = get_rank_role_ids(dept)
    for rid in rank_rids:
        role = guild.get_role(rid)
        if role:
            return role
    return None


def get_approval_label_source(source_dept: str) -> str:
    labels = {
        "pps": "ППС",
        "grom": "ОСН \"ГРОМ\"",
        "osb": "ОСБ",
        "orls": "ОРЛС",
    }
    return labels.get((source_dept or "").strip().lower(), source_dept or "?")


def get_approval_label_target(target_dept: str) -> str:
    labels = {
        "grom": "ОСН \"ГРОМ\"",
        "pps": "ППС",
        "osb": "ОСБ",
        "orls": "ОРЛС",
    }
    return labels.get((target_dept or "").strip().lower(), target_dept or "?")
