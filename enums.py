#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from enum import Enum
import discord
from config import Config

class RequestType(Enum):

    CADET = "cadet"
    TRANSFER = "transfer"
    GOV = "gov"

    def get_title(self) -> str:
        titles = {
            RequestType.CADET: "👤 Курсант",
            RequestType.TRANSFER: "🔄 Перевод",
            RequestType.GOV: "🏛️ Гос сотрудник"
        }
        return titles.get(self, "📋 Заявка")

    def get_color(self) -> discord.Color:
        colors = {
            RequestType.CADET: discord.Color.green(),
            RequestType.TRANSFER: discord.Color.blue(),
            RequestType.GOV: discord.Color.light_grey()
        }
        return colors.get(self, discord.Color.default())

    def get_staff_role_id(self) -> int:
        staff_roles = {
            RequestType.CADET: Config.STAFF_ROLE_ID,
            RequestType.TRANSFER: Config.TRANSFER_STAFF_ROLE_ID,
            RequestType.GOV: Config.GOV_STAFF_ROLE_ID
        }
        return staff_roles.get(self, Config.STAFF_ROLE_ID)

    def get_roles_to_give(self) -> list:
        roles = {
            RequestType.CADET: Config.CADET_ROLES_TO_GIVE,
            RequestType.TRANSFER: Config.TRANSFER_ROLES_TO_GIVE,
            RequestType.GOV: [Config.GOV_ROLE_TO_GIVE]
        }
        return roles.get(self, [])

    def get_nickname_prefix(self) -> str:
        prefixes = {
            RequestType.CADET: Config.CADET_NICKNAME_PREFIX,
            RequestType.TRANSFER: Config.TRANSFER_NICKNAME_PREFIX,
            RequestType.GOV: Config.GOV_NICKNAME_PREFIX
        }
        return prefixes.get(self, "")