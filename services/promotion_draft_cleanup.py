from __future__ import annotations

from database import delete_orls_draft, delete_osb_draft, delete_grom_draft, delete_pps_draft
from services.worker_queue import get_worker
import state


def clear_promotion_draft_for_department(user_id: int, dept: str) -> None:
    if not user_id:
        return
    d = (dept or "").strip().lower()
    if d == "orls":
        state.orls_draft_reports.pop(user_id, None)
        state.orls_last_user_data.pop(user_id, None)
        get_worker().submit_fire(delete_orls_draft, user_id)
    elif d == "osb":
        state.osb_draft_reports.pop(user_id, None)
        state.osb_last_user_data.pop(user_id, None)
        get_worker().submit_fire(delete_osb_draft, user_id)
    elif d == "grom":
        state.grom_draft_reports.pop(user_id, None)
        state.grom_last_user_data.pop(user_id, None)
        get_worker().submit_fire(delete_grom_draft, user_id)
    elif d == "pps":
        state.pps_draft_reports.pop(user_id, None)
        state.pps_last_user_data.pop(user_id, None)
        get_worker().submit_fire(delete_pps_draft, user_id)


def clear_promotion_draft_for_user(user_id: int) -> None:
    if not user_id:
        return
    for dept in ("orls", "osb", "grom", "pps"):
        clear_promotion_draft_for_department(user_id, dept)
