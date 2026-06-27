import discord
from discord.ui import TextInput
from utils.validators import Validators
from config import Config

class ReasonMixin:
    def add_reason_field(self):
        self.reason = TextInput(label='Причина', placeholder='Электронная заявка / собеседование', max_length=Config.MAX_REASON_LENGTH, style=discord.TextStyle.paragraph, required=True)
        self.add_item(self.reason)

    async def validate_reason(self, data):
        valid, reason = Validators.validate_reason(self.reason.value)
        if not valid:
            return False, {"error": f"ошибка: {reason}"}
        data['reason'] = reason
        return True, data

class ApprovalMixin:
    def add_approval_field(self):
        self.approval = TextInput(label='Одобрение', placeholder='Ссылка на одобрение / подтверждение', max_length=Config.MAX_REASON_LENGTH, style=discord.TextStyle.paragraph, required=True)
        self.add_item(self.approval)

    async def validate_approval(self, data):
        valid, approval = Validators.validate_reason(self.approval.value, require_link=True)
        if not valid:
            return False, {"error": f"ошибка: {approval}"}
        data['approval'] = approval
        return True, data

class RankMixin:
    def add_rank_field(self):
        self.rank = TextInput(label='Звание', placeholder='Введите ваше текущее звание', max_length=Config.MAX_RANK_LENGTH, required=True)
        self.add_item(self.rank)

    async def validate_rank(self, data):
        valid, rank = Validators.validate_rank(self.rank.value)
        if not valid:
            return False, {"error": f"ошибка в звании: {rank}"}
        data['rank'] = rank
        return True, data