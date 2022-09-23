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
from asyncio import AbstractEventLoop
from typing import Union, List, Optional

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
        playlist_info: List[dict] = []
        playlist_title: Optional[str] = None
        response_url: Optional[str] = None
        num_failed: int = 0
        response: dict = None
        response = await loop.run_in_executor(
            executor=None,
            func=lambda: ytdlconn.extract_info(
                url=query,
                download=not config.PLAYLIST_STREAMING))
        if ytdlconn.params.get("listformats") or config.LOGGING_CONSOLE:
            response_url = None if not response \
                            else response.get("url") if "url" in response.keys() \
                            else response.get("entries")[0].get("url") \
                            if any(response.get("entries")) \
                            else None
            print("Reply: {0}".format(response_url))
        if response:
            playlist_title = response.get("title") if "title" in response else None
            # Fetch all playlist items as an iterable if they exist, else wrap single item as an iterable
            playlist_info = response.get("entries") if "entries" in response else [response]
            # Trim out failed downloads from the playlist
            num_failed = sum(not entry for entry in playlist_info)
            playlist_info = [entry for entry in playlist_info if entry]
        return playlist_info, playlist_title, response_url, num_failed

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
        self._multiqueue: List[List[JukeboxItem]] = []
        self._multiqueue_index: int = 0
        self.bot: commands.Bot = None
        self.voice_client: discord.VoiceClient = None
        self.is_repeating: bool = False
        self.on_track_end_func = None

    # Queue managers

    def get_all(self) -> List[JukeboxItem]:
        return sum(self._multiqueue, [])

    def get_queue(self, user_id: int = None) -> List[JukeboxItem]:
        if not any(self._multiqueue):
            return []

        if not config.PLAYLIST_MULTIQUEUE:
            # Return the base queue
            return self._multiqueue[0]

        if user_id:
            # For multiqueue, fetch matching queue for a given user
            for queue in self._multiqueue:
                if any(queue) and queue[0].added_by.id == user_id:
                    return queue

        # Return matching queue in multiqueue if one exists
        return self._multiqueue[self._multiqueue_index] if len(self._multiqueue) >= self._multiqueue_index else []

    def get_range(self, index_start: int, index_end: int) -> List[JukeboxItem]:
        if not config.PLAYLIST_MULTIQUEUE:
            # Return items from a range in the queue
            queue: List[JukeboxItem] = self.get_queue()
            # Clamp to range of elements in queue
            index_start: int = max(0, index_start)
            index_end: int = min(len(queue), index_end)
            return queue[index_start:index_end]

        # For multiqueue, fetch items in row-major traversal (one item per queue per iter) of queues
        items: List[JukeboxItem] = []
        x_max: int = len(self._multiqueue)
        y_max: int = max(len(queue) for queue in self._multiqueue)
        # Clamp to range of elements in multiqueue
        index_start: int = max(0, index_start)
        index_end: int = min(sum(len(queue) for queue in self._multiqueue), index_end)
        index_counter: int = 0
        for y in range(0, y_max):
            for x in range(0, x_max):
                if y >= len(self._multiqueue[x]):
                    continue
                if index_counter >= index_end:
                    return items
                if index_counter >= index_start:
                    items.append(self._multiqueue[x][y])
                index_counter += 1
        return items

    def get_item_by_index(self, index: int) -> Optional[JukeboxItem]:
        if not any(self._multiqueue):
            return None

        if not config.PLAYLIST_MULTIQUEUE:
            # Return item by index in the queue
            return self._multiqueue[0][index] if any(self._multiqueue) and 0 <= index < len(self._multiqueue) else None

        # For multiqueue, return item by index in row-major traversal (one item per queue per iter) of queues
        x_max: int = len(self._multiqueue)
        y_max: int = max([len(queue) for queue in self._multiqueue])
        index_counter: int = 0
        for y in range(0, y_max):
            for x in range(0, x_max):
                if y >= len(self._multiqueue[x]):
                    continue
                if index == index_counter:
                    return self._multiqueue[x][y]
                index_counter += 1

    def get_index_of_item(self, item: JukeboxItem) -> int:
        if not any(self._multiqueue):
            return -1

        if not config.PLAYLIST_MULTIQUEUE:
            # Return index of item in the queue
            return self._multiqueue[0].index(item)

        # For multiqueue, return index of item in row-major traversal (one item per queue per iter) of queues
        x_max: int = len(self._multiqueue)
        y_max: int = max([len(queue) for queue in self._multiqueue])
        index_counter: int = 0
        for y in range(0, y_max):
            for x in range(0, x_max):
                if y >= len(self._multiqueue[x]):
                    continue
                if self._multiqueue[x][y] == item:
                    return index_counter
                index_counter += 1

        return -1

    def append(self, item: JukeboxItem) -> None:
        if config.PLAYLIST_MULTIQUEUE:
            if not any(any(queue) and queue[0].added_by == item.added_by for queue in self._multiqueue):
                # Create queue for user in multiqueue if none exists
                self._multiqueue.append([item])
            else:
                # Append to existing user queue
                self.get_queue(item.added_by.id).append(item)
        else:
            if not any(self._multiqueue) or not any(self._multiqueue[0]):
                # For multiqueue, create queue if none exists
                self._multiqueue.append([item])
            else:
                # Append to existing queue in multiqueue
                self.get_queue(item.added_by.id).append(item)

    def remove(self, item: JukeboxItem, is_deleting: bool, from_after_play: bool = False) -> None:
        try:
            queue: List[JukeboxItem] = self.get_queue(item.added_by.id)
            if from_after_play or not self.voice_client or not self.voice_client.is_playing():
                # Remove tracks not currently being played
                queue.remove(item)
                # Remove downloaded audio files from disk
                if is_deleting and not config.PLAYLIST_STREAMING:
                    os.remove(item.source)
            else:
                # Remove the currently-playing track from the queue
                # Stop the voice client if playing, triggering self._after_play
                self.stop()
            # Remove the item's queue from the multiqueue if empty
            if not any(queue):
                if self._multiqueue.index(queue) < self._multiqueue_index:
                    # Adjust queue index when removing a queue with a lower index than the current
                    self._multiqueue_index -= 1
                self._multiqueue.remove(queue)
        except FileNotFoundError as error:
            err.log(error)

    def play(self):
        # Reset index to default if out of bounds
        if self._multiqueue_index < 0 or self._multiqueue_index >= len(self._multiqueue):
            self._multiqueue_index = 0
        # Play or resume the jukebox queue
        if any(self.get_queue()) and self.voice_client and not self.voice_client.is_playing():
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
        # Clear any and all queues in the multiqueue
        for queue in self._multiqueue:
            queue.clear()
        self._multiqueue.clear()
        self.stop()

    def remove_many(self, tracks: List[JukeboxItem]) -> None:
        for track in tracks:
            self.remove(
                item=track,
                is_deleting=True)

    def shuffle(self, user_id: int) -> int:
        if config.PLAYLIST_MULTIQUEUE:
            current: JukeboxItem = self.current_track()
            if current and current.added_by == user_id:
                # Stop (but don't remove) the currently-playing track when shuffling a user's currently-playing queue
                self.stop()

        # Shuffle the queue in-place
        queue: List[JukeboxItem] = self.get_queue(user_id=user_id)
        random.shuffle(queue)
        return len(queue)

    def repeat(self) -> bool:
        self.is_repeating = not self.is_repeating
        return self.is_repeating

    # Queue events

    def _after_play(self, error: Exception):
        if error:
            err.log(error)

        # Remove the just-played track from the queue
        current: JukeboxItem = self.current_track()
        self.remove(
            item=current,
            is_deleting=not self.is_repeating,
            from_after_play=True)

        # Repeat playlist by re-appending items after removal
        if current and self.is_repeating:
            self.append(current)

        if config.LOGGING_CONSOLE:
            print("After: {0}".format(current.title))

        if config.PLAYLIST_MULTIQUEUE and self._multiqueue_index < len(self._multiqueue) - 1:
            # Go to the next item in the multiqueue
            self._multiqueue_index += 1

        # Play the next item in the queue
        self.play()

        # Do user-facing after-play behaviour
        if self.on_track_end_func and self.bot:
            # Run async bot funcs
            future = asyncio.run_coroutine_threadsafe(self.on_track_end_func(), self.bot.loop)
            future.result(timeout=config.CORO_TIMEOUT)

    # Queue utilities

    def is_in_voice_channel(self, member: discord.Member = None) -> bool:
        if not member:
            return self.voice_client and self.voice_client.is_connected()
        else:
            return member.voice and member.voice.channel and member.voice.channel.id == config.CHANNEL_VOICE

    def num_listeners(self) -> int:
        return len(self.voice_client.channel.members) - 1 if self.is_in_voice_channel() else 0

    def current_track(self) -> Optional[JukeboxItem]:
        queue: List[JukeboxItem] = self.get_queue()
        return queue[0] if any(queue) else None

    def num_tracks(self) -> int:
        return sum(len(queue) for queue in self._multiqueue)

    def is_empty(self) -> bool:
        return all(not any(queue) for queue in self._multiqueue)


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
