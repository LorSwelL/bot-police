import discord
from config import Config
from .base_position import BasePositionManager


class FiringStartView(discord.ui.View):
    timeout = None

    def __init__(self):
        super().__init__(timeout=None)
        btn = discord.ui.Button(
            label=Config.FIRING_BUTTON_LABEL,
            style=discord.ButtonStyle.danger,
            custom_id="firing_apply_btn",
        )
        btn.callback = self._on_click
        self.add_item(btn)

        senior_btn = discord.ui.Button(
            label="Уволить",
            style=discord.ButtonStyle.danger,
            custom_id="firing_senior_fire_btn",
            emoji="⚠️",
        )
        senior_btn.callback = self._on_senior_fire
        self.add_item(senior_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            await interaction.response.send_message("❌ Только на сервере.", ephemeral=True)
            return False
        return True

    async def _on_click(self, interaction: discord.Interaction):
        from modals.firing_apply_modal import FiringApplyModal
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        modal = FiringApplyModal(member=member)
        await interaction.response.send_modal(modal)

    async def _on_senior_fire(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ Только на сервере.", ephemeral=True)
            return
        senior_role_id = getattr(Config, "FIRING_SENIOR_ROLE_ID", 0) or 0
        if not senior_role_id:
            await interaction.response.send_message("❌ Кнопка «Уволить» не настроена (FIRING_SENIOR_ROLE_ID).", ephemeral=True)
            return
        senior_role = interaction.guild.get_role(int(senior_role_id))
        if not senior_role or senior_role not in (interaction.user.roles or []):
            await interaction.response.send_message("❌ Только старший состав может нажимать эту кнопку.", ephemeral=True)
            return
        from modals.firing_by_senior_modal import FiringBySeniorModal
        await interaction.response.send_modal(FiringBySeniorModal())


class FiringPositionManager(BasePositionManager):
    @property
    def channel_id(self) -> int:
        return Config.FIRING_CHANNEL_ID

    @property
    def check_interval(self) -> int:

        return 60

    async def get_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=Config.FIRING_HEADER_TITLE,
            description=Config.FIRING_HEADER_DESC,
            color=discord.Color.red(),
        )
        return embed

    async def get_view(self) -> discord.ui.View:
        return FiringStartView()

    async def should_keep_message(self, message: discord.Message) -> bool:
        if not message.embeds:
            return False
        e = message.embeds[0]
        return (
            (e.title or "").strip() == Config.FIRING_HEADER_TITLE
            and (e.description or "").strip() == Config.FIRING_HEADER_DESC
        )
