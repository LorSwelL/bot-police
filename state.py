from typing import Dict, Any, Optional, TYPE_CHECKING
import discord
from discord.ext import commands

if TYPE_CHECKING:
    from services.cache import RoleCache, ChannelCache

bot: Optional[commands.Bot] = None  # Теперь с правильным типом

# In-memory словари, которыми управляет слой Store
active_requests: Dict[int, Dict] = {}
active_firing_requests: Dict[int, Dict] = {}
active_promotion_requests: Dict[int, Dict] = {}
orls_draft_reports: Dict[int, Dict] = {}
orls_last_user_data: Dict[int, Dict[str, str]] = {}
osb_draft_reports: Dict[int, Dict] = {}
osb_last_user_data: Dict[int, Dict[str, str]] = {}
grom_draft_reports: Dict[int, Dict] = {}
grom_last_user_data: Dict[int, Dict[str, str]] = {}
pps_draft_reports: Dict[int, Dict] = {}
pps_last_user_data: Dict[int, Dict[str, str]] = {}
role_cache: Optional["RoleCache"] = None
channel_cache: Optional["ChannelCache"] = None
warehouse_requests: Dict[int, Dict] = {}  # Для заявок склада
active_department_transfers: Dict[int, Dict[str, Any]] = {}  # Заявки на перевод между отделами

# Store-слой для активных заявок; инициализируется в main.py
request_store: Any | None = None
firing_store: Any | None = None
promotion_store: Any | None = None
warehouse_store: Any | None = None

promotion_setup_messages: Dict[int, list] = {}
promotion_setup_move_cooldown: Dict[int, float] = {}

# Черновики и последние данные пользователя для рапортов академии (создаются при первом обращении, если не заданы)
academy_draft_reports: Dict[int, Dict] = {}
academy_last_user_data: Dict[int, Dict[str, str]] = {}

# Флаг фатальной ошибки при старте (заполняется в events.on_ready)
fatal_startup_error: Optional[str] = None