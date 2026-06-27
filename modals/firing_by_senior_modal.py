
import discord
from discord.ui import Modal, TextInput
import logging
import asyncio

from config import Config
from views.message_texts import ErrorMessages
from utils.rate_limiter import apply_role_changes, safe_discord_call
from services.audit import send_to_audit
from views.theme import RED

logger = logging.getLogger(__name__)


class FiringBySeniorModal(Modal):
    def __init__(self):
        super().__init__(title="⚠️ Уволить по ID")
        self.discord_id_input = TextInput(
            label="Discord ID участника",
            placeholder="Например: 123456789012345678",
            min_length=17,
            max_length=20,
            required=True,
        )
        self.reason_input = TextInput(
            label="Причина увольнения",
            placeholder="Укажите причину для кадрового аудита",
            style=discord.TextStyle.paragraph,
            max_length=Config.MAX_REASON_LENGTH,
            required=True,
        )
        self.add_item(self.discord_id_input)
        self.add_item(self.reason_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw_id = (self.discord_id_input.value or "").strip()
        reason = (self.reason_input.value or "").strip()

        if not raw_id.isdigit():
            await interaction.response.send_message(
                "❌ Discord ID должен содержать только цифры.",
                ephemeral=True,
            )
            return

        try:
            target_id = int(raw_id)
        except ValueError:
            await interaction.response.send_message("❌ Некорректный Discord ID.", ephemeral=True)
            return

        if target_id == interaction.user.id:
            await interaction.response.send_message("❌ Нельзя уволить самого себя через эту кнопку.", ephemeral=True)
            return

        if not interaction.guild:
            await interaction.response.send_message("❌ Только на сервере.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            member = interaction.guild.get_member(target_id)
            if not member:
                try:
                    member = await interaction.guild.fetch_member(target_id)
                except discord.NotFound:
                    member = None
        except (discord.Forbidden, discord.HTTPException) as e:
            logger.warning("FiringBySenior: не удалось получить участника %s: %s", target_id, e)
            await interaction.followup.send(
                "❌ Не удалось найти участника на сервере или нет прав на просмотр.",
                ephemeral=True,
            )
            return

        full_name = "Сотрудник"
        if member:
            from utils.member_display import name_after_display_pipe
            raw = getattr(member, "display_name", None) or getattr(member, "name", None) or full_name
            full_name = name_after_display_pipe(str(raw)) or "Сотрудник"

        if not member:

            class _StubMember:
                def __init__(self, uid: int):
                    self.id = uid

            try:
                await send_to_audit(
                    interaction,
                    _StubMember(target_id),
                    Config.ACTION_FIRED,
                    Config.RANK_FIRED,
                    reason,
                )
            except Exception as e:
                logger.warning("FiringBySenior: аудит (участник не на сервере) %s: %s", target_id, e)
            try:
                from services.promotion_draft_cleanup import clear_promotion_draft_for_user
                clear_promotion_draft_for_user(target_id)
            except Exception:
                logger.debug("FiringBySenior: clear_promotion_draft_for_user(target_id) не удалось", exc_info=True)
                pass
            await interaction.followup.send(
                f"✅ Участник с ID **{target_id}** не найден на сервере. Кадровый аудит отправлен с причиной.",
                ephemeral=True,
            )
            return

        roles_to_keep_ids = set(Config.ROLES_TO_KEEP_ON_FIRE)
        roles_to_remove = []
        for role in member.roles:
            if role.is_default() or role.is_integration() or role.is_bot_managed():
                continue
            if role.id not in roles_to_keep_ids:
                roles_to_remove.append(role)

        if roles_to_remove:
            try:
                await apply_role_changes(member, remove=roles_to_remove)
            except discord.Forbidden:
                await interaction.followup.send("❌ У бота нет прав снять роли.", ephemeral=True)
                return
            except discord.HTTPException as e:
                logger.warning("FiringBySenior: снятие ролей %s: %s", member.id, e, exc_info=True)
                await interaction.followup.send("❌ Ошибка Discord API при снятии ролей.", ephemeral=True)
                return

        fired_role = interaction.guild.get_role(Config.FIRED_ROLE_ID)
        if fired_role:
            try:
                await apply_role_changes(member, add=[fired_role])
            except discord.Forbidden:
                await interaction.followup.send("❌ У бота нет прав выдать роль уволенного.", ephemeral=True)
                return
            except discord.HTTPException as e:
                logger.warning("FiringBySenior: выдача роли уволенного %s: %s", member.id, e, exc_info=True)
                await interaction.followup.send("❌ Ошибка Discord API при выдаче роли.", ephemeral=True)
                return

        prefix = (Config.FIRING_NICKNAME_PREFIX or "Уволен |").strip()
        name_for_nick = full_name or "Сотрудник"
        try:
            parts = name_for_nick.split(None, 1)
            new_nick = f"{prefix} {parts[0]} {parts[1]}" if len(parts) >= 2 else f"{prefix} {name_for_nick}"
            await safe_discord_call(member.edit, nick=new_nick)
        except (discord.Forbidden, discord.HTTPException) as e:
            logger.warning("FiringBySenior: смена ника %s: %s", member.id, e)
            new_nick = f"{prefix} {name_for_nick}"

        try:
            await send_to_audit(
                interaction,
                member,
                Config.ACTION_FIRED,
                Config.RANK_FIRED,
                reason,
            )
        except Exception as e:
            logger.warning("FiringBySenior: аудит %s: %s", member.id, e, exc_info=True)

        try:
            embed = discord.Embed(
                title="Увольнение по решению старшего состава",
                color=RED,
                description=f"Вы уволены с **{interaction.guild.name}**.",
                timestamp=discord.utils.utcnow(),
            )
            embed.add_field(name="Уволил", value=interaction.user.mention, inline=True)
            embed.add_field(name="Причина", value=reason[:1024], inline=False)
            embed.add_field(name="Новый ник", value=f"`{new_nick}`", inline=False)
            await member.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

        try:
            from services.promotion_draft_cleanup import clear_promotion_draft_for_user
            clear_promotion_draft_for_user(member.id)
        except Exception:
            logger.debug("FiringBySenior: clear_promotion_draft_for_user(member.id) не удалось", exc_info=True)
            pass

        try:
            await interaction.followup.send(
                f"✅ Пользователь {member.mention} уволен. Кадровый аудит отправлен с указанной причиной.",
                ephemeral=True,
            )
            logger.info("FiringBySenior: %s уволил %s (причина: %s)", interaction.user.id, member.id, reason[:50])
        except Exception as e:
            logger.error("FiringBySenior: неожиданная ошибка: %s", e, exc_info=True)
            await interaction.followup.send(ErrorMessages.GENERIC, ephemeral=True)
