# -*- coding: utf-8 -*-
import asyncio
import logging
import time

import discord
from discord import app_commands

import state
from config import Config
from utils.interaction_helpers import safe_followup_or_response
from utils.slash_helpers import NO_ROLE_ABOVE_BOT, slash_require_role_above_bot
from views.grom_promotion_apply_view import GromPromotionApplyView
from views.orls_promotion_apply_view import OrlsPromotionApplyView
from views.osb_promotion_apply_view import OsbPromotionApplyView
from views.pps_promotion_apply_view import PpsPromotionApplyView

logger = logging.getLogger(__name__)


def get_promotion_view(dept: str) -> discord.ui.View:
    if dept == "orls":
        return OrlsPromotionApplyView()
    if dept == "osb":
        return OsbPromotionApplyView()
    if dept == "grom":
        return GromPromotionApplyView()
    if dept == "pps":
        return PpsPromotionApplyView()
    return OrlsPromotionApplyView()


async def move_promotion_setup_to_bottom(bot: discord.Client, channel: discord.TextChannel) -> None:
    if not isinstance(channel, discord.TextChannel):
        return
    if not isinstance(getattr(state, "promotion_setup_messages", None), dict):
        state.promotion_setup_messages = {}
    if not isinstance(getattr(state, "promotion_setup_move_cooldown", None), dict):
        state.promotion_setup_move_cooldown = {}
    now = time.time()
    cooldown_sec = 15
    if channel.id in state.promotion_setup_move_cooldown:
        if now - state.promotion_setup_move_cooldown[channel.id] < cooldown_sec:
            return
    state.promotion_setup_move_cooldown[channel.id] = now

    entries = state.promotion_setup_messages.get(channel.id, [])
    if not entries:
        return
    new_entries = []
    for item in entries:
        try:
            msg = await channel.fetch_message(item["message_id"])
            if msg.author != bot.user:
                continue
            await msg.delete()
        except (discord.NotFound, discord.HTTPException):
            pass
        try:
            view = get_promotion_view(item["dept"])
            new_msg = await channel.send(content=item["content"], view=view)
            new_entries.append({"message_id": new_msg.id, "dept": item["dept"], "content": item["content"]})
        except Exception as e:
            logger.debug("Перенос сообщения рапорта %s: %s", item.get("dept"), e)
    if new_entries:
        state.promotion_setup_messages[channel.id] = new_entries


async def promotion_setup_position_check_loop(bot: discord.Client) -> None:
    interval = getattr(Config, "PROMOTION_SETUP_CHECK_INTERVAL", 90) or 90
    if interval <= 0:
        return
    await asyncio.sleep(interval)
    while True:
        try:
            guild = bot.get_guild(Config.GUILD_ID) if Config.GUILD_ID else None
            if not guild:
                await asyncio.sleep(interval)
                continue
            for channel_id in list((getattr(state, "promotion_setup_messages", {}) or {}).keys()):
                try:
                    ch = guild.get_channel(channel_id)
                    if not ch or not isinstance(ch, discord.TextChannel):
                        continue
                    last_msg = None
                    async for m in ch.history(limit=1):
                        last_msg = m
                        break
                    if not last_msg:
                        continue
                    setup_ids = {
                        item["message_id"]
                        for item in ((getattr(state, "promotion_setup_messages", None) or {}).get(channel_id) or [])
                    }
                    if last_msg.id in setup_ids:
                        continue
                    await move_promotion_setup_to_bottom(bot, ch)
                except Exception as e:
                    logger.debug("Проверка канала рапортов %s: %s", channel_id, e, exc_info=True)
        except asyncio.CancelledError:
            logger.info("Фоновая задача promotion_setup_position_check_loop остановлена по CancelledError")
            raise
        except Exception as e:
            logger.warning("promotion_setup_position_check: %s", e, exc_info=True)
        await asyncio.sleep(interval)


async def send_promotion_message_at_bottom(
    bot: discord.Client,
    channel: discord.TextChannel,
    content: str,
    view: discord.ui.View,
    dept: str | None = None,
) -> discord.Message | None:
    msg = await channel.send(content=content, view=view)
    try:
        last_in_channel = None
        async for m in channel.history(limit=1):
            last_in_channel = m
            break
        if last_in_channel and last_in_channel.id != msg.id:
            await msg.delete()
            msg = await channel.send(content=content, view=view)
    except Exception as e:
        logger.warning(
            "promotion_setup: ошибка при проверке последнего сообщения в канале %s: %s",
            getattr(channel, "id", None),
            e,
            exc_info=True,
        )
    if dept:
        if not isinstance(getattr(state, "promotion_setup_messages", None), dict):
            state.promotion_setup_messages = {}
        entries = state.promotion_setup_messages.get(channel.id, []) or []
        new_entries = []
        # Удаляем старые сообщения подачи рапортов этого отдела в этом канале
        for item in entries:
            if item.get("dept") != dept:
                new_entries.append(item)
                continue
            old_id = item.get("message_id")
            if not old_id or old_id == msg.id:
                continue
            try:
                old_msg = await channel.fetch_message(old_id)
                if old_msg.author == bot.user:
                    await old_msg.delete()
            except (discord.NotFound, discord.HTTPException):
                pass
        new_entries.append({"message_id": msg.id, "dept": dept, "content": content})
        state.promotion_setup_messages[channel.id] = new_entries
    return msg


def promotion_setup_configs():
    return [
        (getattr(Config, "PROMOTION_APPLY_CHANNEL_ORLS", 0), "ОРЛС", "orls", OrlsPromotionApplyView(), (
            "📋 **Рапорты на повышение ОРЛС**\n\n"
            "1. Выберите ваше повышение из списка ниже.\n"
            "2. В форме укажите ФИО, Discord ID, паспорт.\n"
            "3. Вставьте ссылки по обязательным критериям (по одной в строке).\n"
            "4. Дополнительно можете указать ссылки для баллов ОРЛС.\n\n"
            "Бот создаст рапорт с кнопками для кадровика и отдельную ветку со всеми ссылками и требованиями."
        )),
        (getattr(Config, "PROMOTION_APPLY_CHANNEL_OSB", 0), "ОСБ", "osb", OsbPromotionApplyView(), (
            "📋 **Рапорты на повышение ОСБ (Отдел собственной безопасности)**\n\n"
            "1. Выберите ваше повышение из списка ниже.\n"
            "2. В форме укажите ФИО, Discord ID, паспорт.\n"
            "3. Вставьте ссылки по обязательным критериям (по одной в строке).\n"
            "4. Дополнительно укажите ссылки для баллов (общие и только ОСБ).\n\n"
            "Бот создаст рапорт с кнопками для кадровика и отдельную ветку со всеми ссылками и требованиями."
        )),
        (getattr(Config, "PROMOTION_APPLY_CHANNEL_GROM", 0), "ГРОМ", "grom", GromPromotionApplyView(), (
            "📋 **Рапорты на повышение ОСН «Гром» (ГРОМ)**\n\n"
            "1. Выберите ваше повышение из списка ниже.\n"
            "2. В форме укажите ФИО, Discord ID, паспорт.\n"
            "3. Вставьте ссылки по обязательным критериям (по одной в строке).\n"
            "4. Дополнительно укажите ссылки для баллов (общие, ГРОМ, инструкторы).\n\n"
            "Бот создаст рапорт с кнопками для кадровика и отдельную ветку со всеми ссылками и требованиями."
        )),
        (getattr(Config, "PROMOTION_APPLY_CHANNEL_PPS", 0), "ППС", "pps", PpsPromotionApplyView(), (
            "📋 **Рапорты на повышение ППС**\n\n"
            "1. Выберите ваше повышение из списка ниже.\n"
            "2. В форме укажите ФИО, Discord ID, паспорт.\n"
            "3. Вставьте ссылки по обязательным критериям (по одной в строке).\n"
            "4. Дополнительно укажите ссылки для баллов (общие, ППС, инструкторы).\n\n"
            "Бот создаст рапорт с кнопками для кадровика и отдельную ветку со всеми ссылками и требованиями."
        )),
    ]


async def ensure_promotion_messages_on_startup(bot: discord.Client, guild: discord.Guild) -> None:
    if not bot.user:
        return
    for channel_id, label, dept, view, content in promotion_setup_configs():
        if not channel_id:
            continue
        ch = guild.get_channel(channel_id)
        if not ch or not isinstance(ch, discord.TextChannel):
            continue
        try:
            last_in_channel = None
            async for m in ch.history(limit=1):
                last_in_channel = m
                break
            if last_in_channel and last_in_channel.author == bot.user and "Рапорты на повышение" in (last_in_channel.content or ""):
                # Сообщение уже есть — регистрируем канал в state, чтобы его держали внизу при новых сообщениях и по таймеру
                if not isinstance(getattr(state, "promotion_setup_messages", None), dict):
                    state.promotion_setup_messages = {}
                state.promotion_setup_messages[ch.id] = [
                    {"message_id": last_in_channel.id, "dept": dept, "content": content}
                ]
                continue
            await send_promotion_message_at_bottom(bot, ch, content, view, dept=dept)
            logger.info("При запуске создано сообщение для рапортов: %s (channel_id=%s)", label, channel_id)
        except Exception as e:
            logger.warning("Не создать сообщение для рапортов %s при запуске: %s", label, e)


def register_promotion_setup_commands(bot: discord.ext.commands.Bot) -> None:

    @bot.tree.command(
        name="orls_promotion_setup",
        description="Создать сообщение для подачи рапортов на повышение ОРЛС в этом канале",
    )
    @app_commands.guilds(discord.Object(id=Config.GUILD_ID))
    async def orls_promotion_setup_slash(interaction: discord.Interaction):
        if not slash_require_role_above_bot(interaction):
            await interaction.response.send_message(NO_ROLE_ABOVE_BOT, ephemeral=True)
            return
        channel = interaction.channel
        if not channel or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("❌ Команду нужно вызывать в текстовом канале сервера.", ephemeral=True)
            return
        if not isinstance(Config.PROMOTION_CHANNELS, dict) or channel.id not in Config.PROMOTION_CHANNELS:
            await interaction.response.send_message(
                "❌ Этот канал не настроен как канал рапортов на повышение. Вызовите команду в нужном канале повышений ОРЛС.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            view = OrlsPromotionApplyView()
            content = (
                "📋 **Рапорты на повышение ОРЛС**\n\n"
                "1. Выберите ваше повышение из списка ниже.\n"
                "2. В форме укажите ФИО, Discord ID, паспорт.\n"
                "3. Вставьте ссылки по обязательным критериям (по одной в строке).\n"
                "4. Дополнительно можете указать ссылки для баллов ОРЛС.\n\n"
                "Бот создаст рапорт с кнопками для кадровика и отдельную ветку со всеми ссылками и требованиями."
            )
            await send_promotion_message_at_bottom(bot, channel, content, view, dept="orls")
            await safe_followup_or_response(interaction, "✅ Сообщение для рапортов ОРЛС создано.", ephemeral=True)
        except Exception as e:
            logger.exception("orls_promotion_setup")
            await safe_followup_or_response(
                interaction,
                "❌ Произошла ошибка. Попробуйте позже или обратитесь к администратору.",
                ephemeral=True,
            )

    @bot.tree.command(
        name="osb_promotion_setup",
        description="Создать сообщение для подачи рапортов на повышение ОСБ в этом канале",
    )
    @app_commands.guilds(discord.Object(id=Config.GUILD_ID))
    async def osb_promotion_setup_slash(interaction: discord.Interaction):
        if not slash_require_role_above_bot(interaction):
            await interaction.response.send_message(NO_ROLE_ABOVE_BOT, ephemeral=True)
            return
        channel = interaction.channel
        if not channel or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("❌ Команду нужно вызывать в текстовом канале сервера.", ephemeral=True)
            return
        if not isinstance(Config.PROMOTION_CHANNELS, dict) or channel.id not in Config.PROMOTION_CHANNELS:
            await interaction.response.send_message(
                "❌ Этот канал не настроен как канал рапортов на повышение. Вызовите команду в нужном канале повышений ОСБ.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            view = OsbPromotionApplyView()
            content = (
                "📋 **Рапорты на повышение ОСБ (Отдел собственной безопасности)**\n\n"
                "1. Выберите ваше повышение из списка ниже.\n"
                "2. В форме укажите ФИО, Discord ID, паспорт.\n"
                "3. Вставьте ссылки по обязательным критериям (по одной в строке).\n"
                "4. Дополнительно укажите ссылки для баллов (общие и только ОСБ).\n\n"
                "Бот создаст рапорт с кнопками для кадровика и отдельную ветку со всеми ссылками и требованиями."
            )
            await send_promotion_message_at_bottom(bot, channel, content, view, dept="osb")
            await safe_followup_or_response(interaction, "✅ Сообщение для рапортов ОСБ создано.", ephemeral=True)
        except Exception as e:
            logger.exception("osb_promotion_setup")
            await safe_followup_or_response(
                interaction,
                "❌ Произошла ошибка. Попробуйте позже или обратитесь к администратору.",
                ephemeral=True,
            )

    @bot.tree.command(
        name="grom_promotion_setup",
        description="Создать сообщение для подачи рапортов на повышение ОСН «Гром» в этом канале",
    )
    @app_commands.guilds(discord.Object(id=Config.GUILD_ID))
    async def grom_promotion_setup_slash(interaction: discord.Interaction):
        if not slash_require_role_above_bot(interaction):
            await interaction.response.send_message(NO_ROLE_ABOVE_BOT, ephemeral=True)
            return
        channel = interaction.channel
        if not channel or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("❌ Команду нужно вызывать в текстовом канале сервера.", ephemeral=True)
            return
        if not isinstance(Config.PROMOTION_CHANNELS, dict) or channel.id not in Config.PROMOTION_CHANNELS:
            await interaction.response.send_message(
                "❌ Этот канал не настроен как канал рапортов на повышение. Вызовите команду в нужном канале повышений ГРОМ.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            view = GromPromotionApplyView()
            content = (
                "📋 **Рапорты на повышение ОСН «Гром» (ГРОМ)**\n\n"
                "1. Выберите ваше повышение из списка ниже.\n"
                "2. В форме укажите ФИО, Discord ID, паспорт.\n"
                "3. Вставьте ссылки по обязательным критериям (по одной в строке).\n"
                "4. Дополнительно укажите ссылки для баллов (общие, ГРОМ, инструкторы).\n\n"
                "Бот создаст рапорт с кнопками для кадровика и отдельную ветку со всеми ссылками и требованиями."
            )
            await send_promotion_message_at_bottom(bot, channel, content, view, dept="grom")
            await safe_followup_or_response(interaction, "✅ Сообщение для рапортов ГРОМ создано.", ephemeral=True)
        except Exception as e:
            logger.exception("grom_promotion_setup")
            await safe_followup_or_response(
                interaction,
                "❌ Произошла ошибка. Попробуйте позже или обратитесь к администратору.",
                ephemeral=True,
            )

    @bot.tree.command(
        name="pps_promotion_setup",
        description="Создать сообщение для подачи рапортов на повышение ППС в этом канале",
    )
    @app_commands.guilds(discord.Object(id=Config.GUILD_ID))
    async def pps_promotion_setup_slash(interaction: discord.Interaction):
        if not slash_require_role_above_bot(interaction):
            await interaction.response.send_message(NO_ROLE_ABOVE_BOT, ephemeral=True)
            return
        channel = interaction.channel
        if not channel or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("❌ Команду нужно вызывать в текстовом канале сервера.", ephemeral=True)
            return
        if not isinstance(Config.PROMOTION_CHANNELS, dict) or channel.id not in Config.PROMOTION_CHANNELS:
            await interaction.response.send_message(
                "❌ Этот канал не настроен как канал рапортов на повышение. Вызовите команду в нужном канале повышений ППС.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            view = PpsPromotionApplyView()
            content = (
                "📋 **Рапорты на повышение ППС**\n\n"
                "1. Выберите ваше повышение из списка ниже.\n"
                "2. В форме укажите ФИО, Discord ID, паспорт.\n"
                "3. Вставьте ссылки по обязательным критериям (по одной в строке).\n"
                "4. Дополнительно укажите ссылки для баллов (общие, ППС, инструкторы).\n\n"
                "Бот создаст рапорт с кнопками для кадровика и отдельную ветку со всеми ссылками и требованиями."
            )
            await send_promotion_message_at_bottom(bot, channel, content, view, dept="pps")
            await safe_followup_or_response(interaction, "✅ Сообщение для рапортов ППС создано.", ephemeral=True)
        except Exception as e:
            logger.exception("pps_promotion_setup")
            await safe_followup_or_response(
                interaction,
                "❌ Произошла ошибка. Попробуйте позже или обратитесь к администратору.",
                ephemeral=True,
            )

    @bot.tree.command(
        name="promotion_setup_all",
        description="Создать сообщения «Подать рапорт» во всех каналах повышения (ОРЛС, ОСБ, ГРОМ, ППС)",
    )
    @app_commands.guilds(discord.Object(id=Config.GUILD_ID))
    async def promotion_setup_all_slash(interaction: discord.Interaction):
        if not slash_require_role_above_bot(interaction):
            await interaction.response.send_message(NO_ROLE_ABOVE_BOT, ephemeral=True)
            return
        if not interaction.guild:
            await interaction.response.send_message("❌ Только на сервере.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        results = []
        for channel_id, label, dept, view, content in promotion_setup_configs():
            if not channel_id:
                continue
            ch = guild.get_channel(channel_id)
            if not ch or not isinstance(ch, discord.TextChannel):
                results.append("❌ %s: канал не найден" % label)
                continue
            try:
                await send_promotion_message_at_bottom(bot, ch, content, view, dept=dept)
                results.append("✅ %s" % label)
            except Exception as e:
                logger.exception("promotion_setup_all %s", label)
                results.append(
                    "❌ %s: произошла ошибка при создании сообщения. Обратитесь к администратору."
                    % label
                )
        if not results:
            await safe_followup_or_response(
                interaction,
                "Не настроено ни одного канала повышения (PROMOTION_CH_02..05 в .env).",
                ephemeral=True,
            )
            return
        await safe_followup_or_response(interaction, "**Готово:**\n" + "\n".join(results), ephemeral=True)
