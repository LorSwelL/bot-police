import asyncio
import time
from typing import Optional, List
import discord

class RoleCache:
    def __init__(self, bot):
        self.bot = bot
        self._roles = {}
        self._lock = asyncio.Lock()

    async def get_role(self, guild_id: int, role_id: int) -> Optional[discord.Role]:
        if not guild_id or not role_id or not isinstance(guild_id, int) or not isinstance(role_id, int):
            return None
        key = (guild_id, role_id)
        async with self._lock:
            cached = self._roles.get(key)
        if cached:
            return cached
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return None
        role = guild.get_role(role_id)
        if role:
            async with self._lock:
                self._roles[key] = role
        return role

    async def get_many_roles(self, guild_id: int, role_ids: List[int]) -> List[discord.Role]:
        tasks = [self.get_role(guild_id, rid) for rid in role_ids]
        return await asyncio.gather(*tasks)

    async def refresh_guild(self, guild_id: int):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        async with self._lock:
            for role in guild.roles:
                self._roles[(guild_id, role.id)] = role

class ChannelCache:
    def __init__(self, bot, ttl_seconds: int = 300):
        self.bot = bot
        self._channels: dict[int, tuple[discord.abc.GuildChannel, float]] = {}
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()

    async def get_channel(self, channel_id: int):
        if not channel_id or not isinstance(channel_id, int):
            return None
        now = time.monotonic()
        async with self._lock:
            cached = self._channels.get(channel_id)
            if cached:
                ch, ts = cached
                if now - ts < self._ttl:
                    return ch
                self._channels.pop(channel_id, None)
            ch = self.bot.get_channel(channel_id)
            if ch:
                self._channels[channel_id] = (ch, now)
        return ch