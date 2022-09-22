# Mini-Jukebox
# config.py
# Written by blueberry et al., 2022
# https://github.com/StardewValleyDiscord/mini-jukebox

"""
Contents:
    Runtime
    Bot
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

CONFIG_PATH = "./private/config.json"
DATABASE_PATH = "./private/jukebox.db"
TEMP_DIR = "./private/temp"

# Bot

COG_COMMANDS = "Jukebox Commands"
PACKAGE_COMMANDS = "jukebox_commands"

with open(file=CONFIG_PATH, mode="r") as config_file:
    cfg = json.load(config_file)

# Discord

DISCORD_TOKEN = cfg["discord"]["token"]
DISCORD_INTENTS: discord.Intents = discord.Intents(
    guilds=True,
    guild_messages=True,
    guild_reactions=True,
    members=True,
    emojis=True,
    voice_states=True
)

COMMAND_PREFIX = cfg["discord"]["command_prefix"]

ROLE_ADMIN = cfg["discord"]["roles"]["admin"]
ROLE_TRUSTED = cfg["discord"]["roles"]["trusted"]
ROLE_DEFAULT = cfg["discord"]["roles"]["default"]
ROLE_JUKEBOX = cfg["discord"]["roles"]["bonus"]

CHANNEL_VOICE = cfg["discord"]["channels"]["voice"]
CHANNEL_TEXT = cfg["discord"]["channels"]["text"]
CHANNEL_LOG = cfg["discord"]["channels"]["log"]

CORO_TIMEOUT = cfg["discord"]["coro_timeout_seconds"]
VOICE_TIMEOUT = cfg["discord"]["voice_timeout_seconds"]
VOICE_RECONNECT = cfg["discord"]["voice_reconnect_enabled"]

LOGGING_CHANNEL = cfg["discord"]["logging_channel"] and CHANNEL_LOG is not None
LOGGING_CONSOLE = cfg["discord"]["logging_console"]

# HTTP

HTTP_SEARCH_TIMEOUT = cfg["http"]["response_timeout_seconds"]

# FFMPEG

ffmpeg_options = cfg["ffmpeg"]["options"]

# Jukebox

PLAYLIST_STREAMING = cfg["jukebox"]["streaming_enabled"]
TRACK_DURATION_LIMIT = cfg["jukebox"]["track_duration_limit_seconds"]
PLAYLIST_LENGTH_WARNING = cfg["jukebox"]["total_tracks_warning_len"]
PLAYLIST_DURATION_WARNING = cfg["jukebox"]["total_duration_warning_seconds"]
PLAYLIST_FILESIZE_WARNING = cfg["jukebox"]["total_filesize_warning_mebibytes"]

# YTDL

YTDL_ALLOWED_EXTRACTORS = cfg["ytdl"]["allowed_extractors"]

ytdlp_options = cfg["ytdl"]["options"]
ytdlp_options["outtmpl"] = os.path.join(TEMP_DIR, ytdlp_options["outtmpl"])
yt_dlp.utils.bug_reports_message = lambda: ""
