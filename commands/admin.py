# -*- coding: utf-8 -*-
import logging
from datetime import datetime, timedelta

import discord
from discord import app_commands

import state
from config import Config
from database import delete_request
from services.diag_report import build_diag_embed
from services.health_report import cleanup_orphan_records
from utils.slash_helpers import NO_ROLE_ABOVE_BOT, slash_require_role_above_bot
from utils.interaction_helpers import safe_followup_or_response

logger = logging.getLogger(__name__)


def register_admin_commands(bot: discord.ext.commands.Bot) -> None:

    @bot.tree.command(name="ping", description="Задержка бота")
    async def ping_slash(interaction: discord.Interaction):
        if not slash_require_role_above_bot(interaction):
            await interaction.response.send_message(NO_ROLE_ABOVE_BOT, ephemeral=True)
            return
        latency = round(bot.latency * 1000)
        await interaction.response.send_message(f"🏓 Понг! Задержка: {latency}мс")

    @bot.tree.command(name="diag", description="-")
    async def diag_slash(interaction: discord.Interaction):
        if not slash_require_role_above_bot(interaction):
            await interaction.response.send_message(NO_ROLE_ABOVE_BOT, ephemeral=True)
            return
        try:
            await interaction.response.defer(ephemeral=True)
            embed = await build_diag_embed(bot)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error("Ошибка /diag: %s", e, exc_info=True)
            await safe_followup_or_response(interaction, "❌ Ошибка при сборке диагностики.", ephemeral=True)

    @bot.tree.command(name="diag_clean_orphans", description="-")
    async def diag_clean_orphans_slash(interaction: discord.Interaction):
        if not slash_require_role_above_bot(interaction):
            await interaction.response.send_message(NO_ROLE_ABOVE_BOT, ephemeral=True)
            return
        try:
            await interaction.response.defer(ephemeral=True)
            await cleanup_orphan_records(bot, dry_run=False)
            await interaction.followup.send("✅ Очистка лишних записей завершена.", ephemeral=True)
        except Exception as e:
            logger.error("Ошибка /diag_clean_orphans: %s", e, exc_info=True)
            await safe_followup_or_response(interaction, "❌ Ошибка при очистке.", ephemeral=True)

    @bot.tree.command(name="clear_firing", description="-")
    async def clear_firing_slash(interaction: discord.Interaction, days: int = 7):
        if not slash_require_role_above_bot(interaction):
            await interaction.response.send_message(NO_ROLE_ABOVE_BOT, ephemeral=True)
            return
        try:
            await interaction.response.defer(ephemeral=True)
            cutoff_date = datetime.now() - timedelta(days=days)
            deleted_count = 0

            try:
                firing_store = getattr(state, "firing_store", None)
            except Exception as e:
                logger.debug("clear_firing: не удалось получить firing_store: %s", e, exc_info=True)
                firing_store = None

            if firing_store is not None:
                for msg_id, request in list(firing_store.iter_all()):
                    created_at = (request or {}).get("created_at")
                    need_delete = False
                    if not created_at:
                        need_delete = True
                    else:
                        try:
                            if datetime.fromisoformat(created_at) < cutoff_date:
                                need_delete = True
                        except Exception as e:
                            logger.debug("clear_firing: неверный created_at для msg_id=%s: %s", msg_id, e)
                            need_delete = True

                    if need_delete:
                        try:
                            await firing_store.remove_active(int(msg_id))
                            deleted_count += 1
                        except Exception as e:
                            logger.warning("Не удалось удалить firing_request msg_id=%s: %s", msg_id, e)
            else:
                to_delete = []
                for msg_id, request in (getattr(state, "active_firing_requests", {}) or {}).items():
                    created_at = request.get("created_at")
                    if not created_at:
                        to_delete.append(msg_id)
                        continue
                    try:
                        if datetime.fromisoformat(created_at) < cutoff_date:
                            to_delete.append(msg_id)
                    except Exception as e:
                        logger.debug("clear_firing: неверный created_at для msg_id=%s: %s", msg_id, e)
                        to_delete.append(msg_id)
                for msg_id in to_delete:
                    try:
                        await delete_request("firing_requests", int(msg_id))
                        state.active_firing_requests.pop(msg_id, None)
                        deleted_count += 1
                    except Exception as e:
                        logger.warning("Не удалось удалить firing_requests msg_id=%s: %s", msg_id, e)
            await interaction.followup.send(
                f"✅ Удалено {deleted_count} старых заявок на увольнение (память + БД)",
                ephemeral=True,
            )
            logger.info("Очистка заявок на увольнение /clear_firing: %s", deleted_count)
        except Exception as e:
            logger.error("Ошибка /clear_firing: %s", e, exc_info=True)
            await safe_followup_or_response(interaction, "❌ Ошибка при очистке.", ephemeral=True)
