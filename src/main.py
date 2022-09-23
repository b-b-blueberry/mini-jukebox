# Mini-Jukebox
# main.py
# Written by blueberry et al., 2022
# https://github.com/StardewValleyDiscord/mini-jukebox

"""
Contents:
    MusicBot
        Help commands
        Init
        Bot events
        Bot utilities
    Init
    Runtime events
    Global commands
    Startup
"""

import discord
from discord.ext import commands
from discord.ext.commands import Bot, Context, HelpCommand

import config
import err
import jukebox_commands
import strings
from jukebox_checks import is_admin
from jukebox_impl import jukebox


class MusicBot(Bot):

    # Help commands

    class MusicHelpCommand(HelpCommand):
        async def send_bot_help(self, ctx: Context):
            await self._send_help()

        async def send_cog_help(self, cog: commands.Cog):
            await self._send_help()

        async def send_group_help(self, group: commands.Group):
            await self._send_help()

        async def send_command_help(self, command: commands.Command):
            await self._send_help()

        async def _send_help(self):
            text_channel = self.get_destination()
            await text_channel.send(strings.get("info_help").format(
                text_channel.mention,
                strings.emoji_pin))

    # Init

    def __init__(self, **options):
        super().__init__(
            command_prefix=config.COMMAND_PREFIX,
            description=strings.get("client_description"),
            allowed_mentions=discord.AllowedMentions.none(),
            intents=config.DISCORD_INTENTS,
            **options)
        self.help_command = self.MusicHelpCommand()

    # Bot events

    async def on_command(self, ctx: Context):
        # Log all used jukebox commands for auditing
        await self.log_command(ctx=ctx)

    async def on_command_error(self, ctx: Context, error: Exception):
        # Add a reaction to posts with unknown commands or invalid uses
        msg = None
        reaction = None
        try:
            if isinstance(error, commands.CheckFailure):
                # Suppress failed command checks
                reaction = strings.emoji_error
            elif isinstance(error, commands.errors.CommandNotFound):
                # Suppress failed command calls
                reaction = strings.emoji_question
            elif isinstance(error, commands.errors.BadArgument):
                # Suppress failed command parameters
                reaction = strings.emoji_exclamation
            else:
                if isinstance(error, TimeoutError):
                    # Send message on connection timeout
                    msg = strings.get("info_connection_timed_out").format(strings.emoji_connection)
                reaction = strings.emoji_error
                err.log(error)
                raise error
        finally:
            if msg:
                await ctx.reply(content=msg)
            if reaction:
                await ctx.message.add_reaction(reaction)

    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # Stop playing music and leave the voice channel if all other users have disconnected
        if jukebox.voice_client and before.channel and before.channel.id == config.CHANNEL_VOICE and len(before.channel.members) < 2:
            jukebox.stop()
            await jukebox.voice_client.disconnect()

    # Bot utilities

    async def log_command(self, ctx: Context):
        if await is_valid_command_use(ctx=ctx):
            user = ctx.message.author
            if config.LOGGING_CONSOLE:
                msg = strings.get("log_console_command_used").format(
                    user.name,
                    user.discriminator,
                    user.id,
                    ctx.message.content)
                print(msg)

            if config.LOGGING_CHANNEL:
                emoji = await commands.EmojiConverter().convert(ctx=ctx, argument=strings.get("emoji_id_jukebox"))
                msg = strings.get("log_channel_command_used").format(
                    user.name,
                    user.discriminator,
                    user.id,
                    ctx.channel.mention,
                    ctx.message.content,
                    emoji)
                await self.get_channel(id=config.CHANNEL_LOG).send(content=msg)


# Init


bot = MusicBot()
bot.load_extension(name=jukebox_commands.__name__)
jukebox.bot = bot


# Runtime events


@bot.event
async def on_ready():
    msg = strings.get("log_console_client_ready").format(
        bot.user.name,
        bot.user.discriminator,
        bot.user.id)
    print(msg)

    if config.LOGGING_CHANNEL:
        channel = bot.get_channel(id=config.CHANNEL_LOG)
        msg = strings.get("log_channel_client_ready").format(
            bot.user.name,
            bot.user.discriminator,
            bot.user.id,
            strings.emoji_connection)
        await channel.send(content=msg)


# Global commands


@bot.check
async def is_valid_command_use(ctx: Context) -> bool:
    # Ignore commands from bots
    is_not_bot: bool = not ctx.author.bot

    # Ignore commands from channels other than the designated text channel (except admin commands used by admins)
    is_channel_ok: bool = ctx.channel.id == config.CHANNEL_TEXT \
        or (is_admin in ctx.command.checks and await is_admin(ctx=ctx, send_message=False))

    # Ignore commands while commands are blocked (except commands used by admins)
    is_not_blocked: bool = not bot.get_cog(config.COG_COMMANDS).is_blocking_commands \
        or await is_admin(ctx=ctx, send_message=False)

    return is_not_bot and is_channel_ok and is_not_blocked


# Startup


# Run bot
bot.run(config.DISCORD_TOKEN)
