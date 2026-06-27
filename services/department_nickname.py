from __future__ import annotations

from config import Config

NICKNAME_MAX_LENGTH = 32


def get_transfer_nickname(target_dept: str, form_data: dict) -> str | None:
    target_dept = (target_dept or "").strip().lower()
    form_data = form_data or {}
    name = (form_data.get("name") or "").strip()
    surname = (form_data.get("surname") or "").strip()

    callsign = f"{name} {surname}".strip() or "Позывной"
    full_name = f"{name} {surname}".strip() or "Имя Фамилия"

    if target_dept == "pps":
        prefix = getattr(Config, "PPS_NICKNAME_PREFIX", "ППС |")
        nick = f"{prefix} {full_name}"
    elif target_dept == "grom":
        nick = f"ГРОМ [C] | {callsign}"
    elif target_dept == "orls":
        nick = f"Стажер ОРЛС | {full_name}"
    elif target_dept == "osb":
        nick = f"Стажер ОСБ | {full_name}"
    else:
        return None

    if len(nick) > NICKNAME_MAX_LENGTH:
        if target_dept == "pps":
            prefix = getattr(Config, "PPS_NICKNAME_PREFIX", "ППС |") + " "
            part = full_name
        elif target_dept == "grom":
            prefix = "ГРОМ [C] | "
            part = callsign
        elif target_dept == "orls":
            prefix = "Стажер ОРЛС | "
            part = full_name
        else:
            prefix = "Стажер ОСБ | "
            part = full_name
        max_part = NICKNAME_MAX_LENGTH - len(prefix)
        if max_part > 0 and len(part) > max_part:
            part = (part[: max_part - 1].rstrip() + "…") if max_part > 1 else part[:1]
        nick = prefix + part
    return nick[:NICKNAME_MAX_LENGTH]
