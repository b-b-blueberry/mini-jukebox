# Mini-Jukebox
# config.py
# Written by blueberry et al., 2022
# https://github.com/StardewValleyDiscord/mini-jukebox

"""
Contents:
    Runtime
    Bot
    Tokens
    Discord
    HTTP
    FFMPEG
    Jukebox
    YTDL
"""

import os

import json

import discord
import yt_dlp


# Runtime

CONFIG_PATH: str = "/private/config.json"
"""Relative path to data file used for bot configuration."""
STRINGS_PATH = "/jukebox/assets/strings.json"
"""Relative path to data file used for logging, formatting, reply, and flavour strings."""
DATABASE_PATH: str = "/private/jukebox.db"
"""Relative path to database file used to store usage history."""
TEMP_DIR: str = "/private/temp"
"""Relative path to temporary folder used to store cached media data."""

# Bot

COG_COMMANDS: str = "Jukebox Commands"
"""Name of commands cog."""
PACKAGE_COMMANDS: str = "jukebox_commands"
"""Name of commands package."""

with open(file=CONFIG_PATH, mode="r") as config_file:
    cfg: dict = json.load(config_file)

# Tokens

TOKEN_DISCORD: str = cfg["tokens"]["discord"]
"""Token used to run Discord client."""

# Discord

DISCORD_INTENTS: discord.Intents = discord.Intents(
    guilds=True,
    guild_messages=True,
    guild_reactions=True,
    message_content=True,
    members=True,
    emojis=True,
    voice_states=True
)
"""List of allowed and disallowed intents when running Discord client."""

COMMAND_PREFIX: str = cfg["discord"]["command_prefix"]
"""Prefix required for all messages sent in command channel."""

ROLE_ADMIN: int = cfg["discord"]["roles"]["admin"]
"""Discord role ID for commands and features requiring admin privileges."""
ROLE_TRUSTED: int = cfg["discord"]["roles"]["trusted"]
"""Discord role ID for commands and features requiring elevated privileges."""
ROLE_DEFAULT: int = cfg["discord"]["roles"]["default"]
"""Discord role ID for commands requiring basic privileges."""
ROLE_JUKEBOX: int = cfg["discord"]["roles"]["bonus"]
"""Discord role ID for bonus flavour role themed around the jukebox."""

CHANNEL_VOICE: int = cfg["discord"]["channels"]["voice"]
"""Discord channel ID for the voice channel used for media playback."""
CHANNEL_TEXT: int = cfg["discord"]["channels"]["text"]
"""Discord channel ID for the text channel used for command interactions."""
CHANNEL_LOG: int = cfg["discord"]["channels"]["log"]
"""Discord channel ID used to send status and event logging if configured."""

CORO_TIMEOUT: int = cfg["discord"]["coro_timeout_seconds"]
"""Duration in seconds before coroutines are timed-out."""
VOICE_TIMEOUT: int = cfg["discord"]["voice_timeout_seconds"]
"""Duration in seconds before voice connections are timed-out."""
VOICE_RECONNECT: bool = cfg["discord"]["voice_reconnect_enabled"]
"""Whether to automatically reconnect to voice channels after time-out."""

LOGGING_CHANNEL: bool = cfg["discord"]["logging_channel"] and CHANNEL_LOG is not None
"""Whether a logging channel is configured and enabled for status and commands."""
LOGGING_CONSOLE: bool = cfg["discord"]["logging_console"]
"""Whether logging status and commands to console is enabled."""

# HTTP

HTTP_SEARCH_TIMEOUT: int = cfg["http"]["response_timeout_seconds"]
"""Duration in seconds before HTTP requests are timed-out."""

# FFMPEG

ffmpeg_options: str = cfg["ffmpeg"]["options"]
"""Command line parameters for FFMPEG process. Does not include before-options."""

# Jukebox

PLAYLIST_MULTIQUEUE: bool = cfg["jukebox"]["multiqueue_enabled"]
"""Whether multiqueue is enabled, allowing a more even playback of tracks from different users."""
PLAYLIST_STREAMING: bool = cfg["jukebox"]["streaming_enabled"]
"""Whether media data will be streamed from external sources, or preloaded and sourced from local drive."""
TRACK_DURATION_LIMIT: int = cfg["jukebox"]["track_duration_limit_seconds"]
"""Duration in seconds for track runtime before being blocked from the queue."""

# YTDL

YTDL_ALLOWED_EXTRACTORS = cfg["ytdl"]["allowed_extractors"]
"""List of permitted media extractors, used to enforce a list of trusted domains to source media from."""
YTDL_OPTIONS: dict = cfg["ytdl"]["options"]
"""Flags and values for YTDL connection process."""

YTDL_OPTIONS["outtmpl"] = os.path.join(TEMP_DIR, YTDL_OPTIONS["outtmpl"])
yt_dlp.utils.bug_reports_message = lambda: ""
