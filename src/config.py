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
DATABASE_PATH: str = "/private/jukebox.db"
TEMP_DIR: str = "/private/temp"

# Bot

COG_COMMANDS: str = "Jukebox Commands"
PACKAGE_COMMANDS: str = "jukebox_commands"

with open(file=CONFIG_PATH, mode="r") as config_file:
    cfg: dict = json.load(config_file)

# Tokens

TOKEN_DISCORD: str = cfg["tokens"]["discord"]
TOKEN_LYRICS: str = cfg["tokens"]["azlyrics"]

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

COMMAND_PREFIX: str = cfg["discord"]["command_prefix"]

ROLE_ADMIN: int = cfg["discord"]["roles"]["admin"]
ROLE_TRUSTED: int = cfg["discord"]["roles"]["trusted"]
ROLE_DEFAULT: int = cfg["discord"]["roles"]["default"]
ROLE_JUKEBOX: int = cfg["discord"]["roles"]["bonus"]

CHANNEL_VOICE: int = cfg["discord"]["channels"]["voice"]
CHANNEL_TEXT: int = cfg["discord"]["channels"]["text"]
CHANNEL_LOG: int = cfg["discord"]["channels"]["log"]

CORO_TIMEOUT: int = cfg["discord"]["coro_timeout_seconds"]
VOICE_TIMEOUT: int = cfg["discord"]["voice_timeout_seconds"]
VOICE_RECONNECT: bool = cfg["discord"]["voice_reconnect_enabled"]

LOGGING_CHANNEL: bool = cfg["discord"]["logging_channel"] and CHANNEL_LOG is not None
LOGGING_CONSOLE: bool = cfg["discord"]["logging_console"]

# HTTP

HTTP_SEARCH_TIMEOUT: int = cfg["http"]["response_timeout_seconds"]

# FFMPEG

ffmpeg_options: str = cfg["ffmpeg"]["options"]

# Jukebox

PLAYLIST_MULTIQUEUE: bool = cfg["jukebox"]["multiqueue_enabled"]
PLAYLIST_STREAMING: bool = cfg["jukebox"]["streaming_enabled"]
TRACK_DURATION_LIMIT: int = cfg["jukebox"]["track_duration_limit_seconds"]
PLAYLIST_LENGTH_WARNING: int = cfg["jukebox"]["total_tracks_warning_len"]
PLAYLIST_DURATION_WARNING: int = cfg["jukebox"]["total_duration_warning_seconds"]
PLAYLIST_FILESIZE_WARNING: int = cfg["jukebox"]["total_filesize_warning_mebibytes"]

# YTDL

YTDL_ALLOWED_EXTRACTORS = cfg["ytdl"]["allowed_extractors"]

ytdlp_options: dict = cfg["ytdl"]["options"]
ytdlp_options["outtmpl"] = os.path.join(TEMP_DIR, ytdlp_options["outtmpl"])
yt_dlp.utils.bug_reports_message = lambda: ""
