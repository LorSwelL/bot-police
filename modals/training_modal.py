import discord
from discord.ui import Modal, TextInput
import logging
from config import Config
from views.training_buttons import ExamView
from constants import ExamMessages

logger = logging.getLogger(__name__)


def _exam_name_default(member):
    if not member:
        return ""
    from utils.member_display import get_member_full_name
    return get_member_full_name(member)


class ExamModal(Modal):
    def __init__(self, member=None):
        super().__init__(title="🎓 ЗАПИСЬ НА ЭКЗАМЕН")
        name_default = _exam_name_default(member)
        self.name = TextInput(
            label="Ваше имя и фамилия",
            placeholder="Иван Петров",
            required=True,
            max_length=50,
            default=name_default,
        )
        self.add_item(self.name)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.user:
            await interaction.response.send_message("❌ Ошибка контекста.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            from datetime import datetime
            import random

            now = datetime.now()
            month_name = ExamMessages.MONTHS.get(now.month, now.strftime("%B"))
            date_str = f"«{now.day}» {month_name} {now.year} года"

            congrats = Config.EXAM_CONGRATS
            greeting = random.choice(congrats) if congrats else "Добро пожаловать!"

            text = Config.EXAM_NOTIFICATION_TEMPLATE.format(
                header=Config.EXAM_HEADER,
                date=date_str,
                name=(self.name.value or "").strip(),
                greeting=greeting,
            )

            embed = discord.Embed(
                title="⚡ ПОВЕСТКА В АКАДЕМИЮ ⚡",
                description=text,
                color=0xFFD700
            )

            try:
                await interaction.user.send(embed=embed, view=ExamView())
            except discord.Forbidden:
                await interaction.followup.send(
                    "✅ Данные сохранены. Откройте личные сообщения (ЛС) от бота, чтобы увидеть повестку.",
                    ephemeral=True,
                )
                return
            except discord.HTTPException as e:
                import logging
                logging.getLogger(__name__).warning("ExamModal: HTTP при отправке ЛС: %s", e)
                await interaction.followup.send(
                    "⚠️ Не удалось отправить повестку в ЛС. Попробуйте позже или проверьте настройки приватности.",
                    ephemeral=True,
                )
                return

            await interaction.followup.send("✅ Проверьте личные сообщения!", ephemeral=True)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Ошибка в ExamModal: %s", e, exc_info=True)
            await interaction.followup.send("❌ Ошибка при отправке повестки.", ephemeral=True)