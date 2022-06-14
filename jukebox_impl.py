# Mini-Jukebox
# jukebox_impl.py
# Written by blueberry et al., 2022
# https://github.com/StardewValleyDiscord/mini-jukebox

"""
Contents:
    YTDLSource
    JukeboxItem
    Jukebox
        Queue managers
        Queue events
        Queue utilities
    Utility functions
    YTDL config
    Init
"""

import asyncio
import os
import shutil
from typing import Union

import discord
import random
import yt_dlp
from discord.ext import commands

import err
import strings
import config


class YTDLSource(discord.PCMVolumeTransformer):
    @classmethod
    async def get_playlist_info(cls, query, *, loop=None):
        if ytdlconn.params.get("listformats") or config.LOGGING_CONSOLE:
            print("Query: {0}".format(query))
        loop = loop or asyncio.get_event_loop()
        # Process and download track metadata where available
        entries = None
        playlist_title = None
        response_url = None
        response = await loop.run_in_executor(
            executor=None,
            func=lambda: ytdlconn.extract_info(
                url=query,
                download=not config.PLAYLIST_STREAMING))
        if ytdlconn.params.get("listformats") or config.LOGGING_CONSOLE:
            response_url = None if not response or any(not entry for entry in response.get("entries", [])) \
                            else response.get("url") if "url" in response.keys() \
                            else response.get("entries")[0].get("url")
            print("Reply: {0}".format(response_url))
        if response:
            playlist_title = response.get("title") if "title" in response else None
            # Fetch all playlist items as an iterable if they exist, else wrap single item as an iterable
            entries = response.get("entries") if "entries" in response else [response]
        return entries, playlist_title, response_url

    @classmethod
    async def get_playlist_files(cls, playlist_info, is_streaming: bool, added_by):
        playlist_items = []
        for entry in playlist_info:
            # Process and download the track audio
            source = entry.get("url") if is_streaming else ytdlconn.prepare_filename(entry)
            # Add tracks as jukebox queue items
            playlist_items.append(JukeboxItem(
                source=source,
                title=entry.get("title"),
                url=entry.get("original_url"),
                duration=int(entry.get("duration")),
                added_by=added_by))
        return playlist_items


class JukeboxItem:
    def __init__(self, source: str, title: str, url: str, duration: int, added_by: discord.member):
        self.source = source
        self.title = title
        self.url = url
        self.duration = duration
        self.added_by = added_by
        self.audio: discord.FFmpegPCMAudio = None

    def audio_from_source(self) -> discord.FFmpegPCMAudio:
        self.audio = discord.FFmpegPCMAudio(
            source=self.source,
            options=config.ffmpeg_options)
        return self.audio


class Jukebox:
    def __init__(self):
        _clear_temp_folders()
        self.queue = []
        self.bot: commands.Bot = None
        self.voice_client: discord.VoiceClient = None
        self.is_repeating: bool = False
        self.on_track_end_func = None

    # Queue managers

    def append(self, item: JukeboxItem):
        self.queue.append(item)

    def remove(self, index: int, is_deleting: bool, from_after_play: bool = False) -> Union[JukeboxItem, None]:
        removed_item = None
        try:
            if not any(self.queue) or index < 0 or index >= len(self.queue):
                # Ignore invalid uses
                pass
            elif index > 0 or from_after_play or not self.voice_client or not self.voice_client.is_playing():
                # Remove the item from the queue
                removed_item = self.queue.pop(index)
                # Remove downloaded audio files from disk
                if is_deleting and not config.PLAYLIST_STREAMING:
                    os.remove(removed_item.link)
            else:
                # Stop the voice client if playing, triggering self._after_play
                self.stop()
                # Return the queue item which will be removed for real from self._after_play
                removed_item = self.queue[index]
        except FileNotFoundError as error:
            err.log(error)
        finally:
            return removed_item

    def play(self):
        if any(self.queue) and self.voice_client and not self.voice_client.is_playing():
            if not self.voice_client.is_paused():
                self.voice_client.play(
                    source=self.current_track().audio_from_source(),
                    after=self._after_play)
            self.voice_client.resume()

    def resume(self):
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()

    def pause(self):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()

    def stop(self):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()

    def clear(self):
        _clear_temp_folders()
        self.queue.clear()
        self.stop()

    def shuffle(self) -> int:
        self.stop()
        random.shuffle(self.queue)
        return len(self.queue)

    def repeat(self) -> bool:
        self.is_repeating = not self.is_repeating
        return self.is_repeating

    # Queue events

    def _after_play(self, error: Exception):
        if error:
            err.log(error)

        current = self.remove(
            index=0,
            is_deleting=self.is_repeating,
            from_after_play=True)

        if config.LOGGING_CONSOLE:
            print("After: {0}".format(current.title))

        # Repeat playlist by re-appending items after removal
        if self.is_repeating and current:
            self.append(current)
        # Continue to the next track
        if any(self.queue):
            self.play()
        # Do user-facing after-play behaviour
        if self.on_track_end_func and self.bot:
            future = asyncio.run_coroutine_threadsafe(self.on_track_end_func(), self.bot.loop)
            try:
                future.result(timeout=config.CORO_TIMEOUT)
            except Exception as e:
                err.log(e)

    # Queue utilities

    def is_in_voice_channel(self, member: discord.Member = None) -> bool:
        if not member:
            return self.voice_client and self.voice_client.is_connected()
        else:
            return member.voice and member.voice.channel and member.voice.channel.id == config.CHANNEL_VOICE

    def num_listeners(self) -> int:
        return len(self.voice_client.channel.members) - 1 if self.is_in_voice_channel() else 0

    def current_track(self) -> Union[JukeboxItem, None]:
        return self.queue[0] if any(self.queue) else None


# Utility functions


def filter_func(info, *, incomplete) -> str:
    duration: int = info.get("duration")
    if duration > config.TRACK_DURATION_LIMIT:
        return strings.get("info_duration_exceeded").format(
            duration,
            config.TRACK_DURATION_LIMIT)


def _clear_temp_folders():
    try:
        fp = config.TEMP_DIR
        if os.path.exists(fp):
            shutil.rmtree(fp)
        os.mkdir(fp)
    except Exception as error:
        err.log(error)


# YTDL config


config.ytdlp_options["match_filter"] = filter_func
ytdlconn: yt_dlp.YoutubeDL = yt_dlp.YoutubeDL(config.ytdlp_options)


# Init


jukebox: Jukebox = Jukebox()
