# Mini-Jukebox
# jukebox_checks.py
# Written by blueberry et al., 2022
# https://github.com/StardewValleyDiscord/mini-jukebox

from discord.ext.commands import Context

import config
import strings
from jukebox_impl import jukebox


async def is_admin(ctx: Context, send_message=True):
    facts = any(role.id == config.ROLE_ADMIN for role in ctx.author.roles)
    if not facts and send_message:
        msg = strings.get("error_command_role_permissions")
        await ctx.reply(content=msg)
    return facts


async def is_trusted(ctx: Context, send_message=True):
    facts = any(role.id == config.ROLE_TRUSTED for role in ctx.author.roles) \
           or await is_admin(ctx=ctx, send_message=False)
    if not facts and send_message:
        msg = strings.get("error_command_role_permissions")
        await ctx.reply(content=msg)
    return facts


async def is_default(ctx: Context, send_message=True):
    facts = any(role.id == config.ROLE_DEFAULT for role in ctx.author.roles) \
            or await is_trusted(ctx=ctx, send_message=False)
    if not facts and send_message:
        msg = strings.get("error_command_role_permissions")
        await ctx.reply(content=msg)
    return facts


async def is_voice_only(ctx: Context, send_message=True):
    # Filter voice-only command uses by users currently in the voice channel
    facts = jukebox.is_in_voice_channel(member=ctx.author) or await is_admin(ctx=ctx, send_message=False)
    if not facts and send_message:
        # Users can only play the jukebox if they're in the voice channel
        msg = strings.get("error_command_voice_only").format(
            jukebox.bot.get_channel(id=config.CHANNEL_VOICE).mention)
        await ctx.reply(content=msg)
    return facts
