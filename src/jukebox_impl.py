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
import io
import os
import shutil
from asyncio import AbstractEventLoop
from typing import List, Optional, Union

import discord
import random
import yt_dlp
from discord import FFmpegPCMAudio
from discord.ext import commands

import err
import strings
import config


class TrackingAudio(FFmpegPCMAudio):
    """
    An override of the FFmpegPCMAudio class with tracking information.
    :param source: The input that ffmpeg will take and convert to PCM bytes.
    :param options: Extra command line arguments to pass to ffmpeg.
    """
    def __init__(self, source: Union[str, io.BufferedIOBase], duration_seconds: int) -> None:
        super().__init__(
            source=source,
            before_options=config.FFMPEG_BEFORE_OPTIONS,
            options=config.FFMPEG_OPTIONS)

        self._sec_total: int = duration_seconds
        self._ms_current: float = 0

    def read(self) -> bytes:
        """
        Override of AudioSource read method with tracking behaviour.
        """
        self._ms_current += discord.opus.Encoder.FRAME_LENGTH
        return super().read()

    def progress(self) -> int:
        """
        Gets current track progress in seconds.
        """
        return round(self._ms_current / 1000)

    def duration(self) -> int:
        """
        Gets track duration in seconds.
        """
        return self._sec_total

    def ratio(self) -> float:
        """
        Gets ratio of track progress to duration.
        """
        return (self.progress() / self.duration()) if self._sec_total > 0 else 0


class YTDLSource(discord.PCMVolumeTransformer):
    """
    Audio transform override for handling YTDLP connections.
    """
    @classmethod
    async def get_playlist_info(cls, query: str, *, loop: AbstractEventLoop = None, ambiguous: bool = False) -> any:
        """
        Fetch playlist info for a search query or URL, returning media metadata and source URL on success.
        :param query: A generic search query or URL to use with YTDLP, searching queries with the default domain.
        :param loop: Bot async event loop.
        """
        if ytdlconn.params.get("listformats") or config.LOGGING_CONSOLE:
            print(strings.get("log_console_media_query").format(query))

        loop = loop or asyncio.get_event_loop()

        # Process and download track metadata where available
        entries: List[dict] = []
        title: Optional[str] = None
        source: Optional[str] = None
        num_failed: int = 0

        response: Optional[dict] = await loop.run_in_executor(
            executor=None,
            func=lambda: ytdlconn.extract_info(
                url=query if not ambiguous else f"ytsearch5:{query}",
                download=not ambiguous and not config.PLAYLIST_STREAMING))

        # Fetch all playlist items as an iterable if they exist, else wrap single item as an iterable
        entries = response.get("entries") if "entries" in response else [response]

        if response:
            # Fetch relevant fields from response and trim out failed downloads from the playlist
            entries = [entry for entry in entries if entry]

            if ambiguous:
                return entries

            title = response.get("title") if "title" in response else None
            source = response.get("url") if "url" in response else entries[0].get("url")
            num_failed = len(response.get("entries")) - len(entries)

            if ytdlconn.params.get("listformats") or config.LOGGING_CONSOLE:
                if config.LOGGING_CONSOLE:
                    print(strings.get("log_console_media_response").format(source))

        return entries, title, source, num_failed

    @classmethod
    async def get_playlist_files(cls, playlist_info, is_streaming: bool, added_by: discord.member) -> List["JukeboxItem"]:
        """
        Fetch the audio data for all items in a playlist.
        :param playlist_info: List of metadata for items in a playlist.
        :param is_streaming: Whether media is streaming from external sources, rather than preloading to the local drive.
        :param added_by: Discord user instance to attach to each track for later reference.
        """
        playlist_items: List[JukeboxItem] = []
        for entry in playlist_info:
            # Process and download the track audio
            source = entry.get("url") if is_streaming else ytdlconn.prepare_filename(entry)
            # Add tracks as jukebox queue items
            playlist_items.append(YTDLSource.entry_to_track(entry=entry, source=source, added_by=added_by))
        return playlist_items

    @classmethod
    def entry_to_track(cls, entry: dict, source: str, added_by: discord.member):
        return JukeboxItem(
                source=source,
                title=entry.get("title"),
                url=entry.get("original_url"),
                duration=int(entry.get("duration")),
                added_by=added_by)


class JukeboxItem:
    """
    Item representing a track in the queue, containing basic media metadata, source URL, and audio data once playing.
    """
    def __init__(self, source: str, title: str, url: str, duration: int, added_by: discord.member) -> None:
        self.source: str = source
        self.title: str = title
        self.url: str = url
        self.duration: int = duration
        self.added_by: discord.User = added_by
        self.audio: Optional[TrackingAudio] = None

    def audio_from_source(self) -> TrackingAudio:
        """
        Fetch audio data from self source URL.
        """
        self.audio = TrackingAudio(
            source=self.source,
            duration_seconds=self.duration)
        return self.audio


class Jukebox:
    """
    Handler for all queue management and voice client behaviour.
    """

    def __init__(self) -> None:
        _clear_temp_folders()
        self._multiqueue: List[List[JukeboxItem]] = []
        self._multiqueue_index: int = 0
        self.bot: commands.Bot = None
        self.voice_client: Optional[discord.VoiceClient] = None
        self.is_repeating: bool = False
        self.on_track_end_func = None

    # Queue managers

    def get_all(self) -> List[JukeboxItem]:
        """
        Fetch all tracks in the queue, flattened into a single list in column-major order with multiqueue enabled.
        """
        return sum(self._multiqueue, []) if config.PLAYLIST_MULTIQUEUE \
            else self._multiqueue[0] if any(self._multiqueue) \
            else []

    def get_queue(self, user_id: int = None) -> List[JukeboxItem]:
        """
        Fetch the queue containing a given user's tracks.
        With multiqueue enabled, this queue will exclusively contain tracks from this user, if any, in order of insertion.
        With multiqueue disabled, this queue will contain all tracks from all users in order of insertion.
        :param user_id: Discord unique ID of a user to compare against the submitter of tracks in a queue.
        """
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
        """
        Fetch a list of tracks from a range of user-facing (row-major) indexes in the queue.
        """
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
        """
        Fetch an item in the queue by its user-facing (row-major) index.
        :param index: Queue index to fetch item at.
        """
        if not any(self._multiqueue) or index < 0 or index >= len(self.get_all()):
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
        """
        Fetch the user-facing (row-major) index of an item in the queue.
        :param item: Item in the queue to find the index of.
        """
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
        """
        Add a track to the tail of the queue.
        """
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
        """
        Remove a track from the queue, stop playback, and remove any associated cached or preloaded files.
        :param item: Track to be removed.
        :param is_deleting: Whether to delete associated files if not streaming.
        :param from_after_play: Whether being called to remove a track immediately after finishing playback.
        """
        try:
            current: JukeboxItem = self.current_track()
            queue: List[JukeboxItem] = self.get_queue(item.added_by.id)
            queue.remove(item)

            if from_after_play or item is current:
                # For the currently-playing track, stop playing, triggering self._after_play
                if self.voice_client and self.voice_client.is_playing():
                    self.stop()

            if is_deleting and not config.PLAYLIST_STREAMING:
                # Remove downloaded audio files from disk
                os.remove(item.source)

            if config.PLAYLIST_MULTIQUEUE and not any(queue):
                # Remove the item's queue from the multiqueue if empty
                if self._multiqueue.index(queue) < self._multiqueue_index:
                    # Adjust queue index when removing a queue with a lower index than the current
                    self._multiqueue_index -= 1
                self._multiqueue.remove(queue)
        except FileNotFoundError as error:
            err.log(error)

    def play(self) -> None:
        """
        Start media playback, or resume if paused.
        """
        # Reset index to default if out of bounds
        if self._multiqueue_index < 0 or self._multiqueue_index >= len(self._multiqueue):
            self._multiqueue_index = 0

        # Play or resume the jukebox queue
        current: JukeboxItem = self.current_track()
        if current and self.voice_client and not self.voice_client.is_playing():
            if config.LOGGING_CONSOLE:
                print(strings.get("log_console_media_start").format(current.title))

            if not self.voice_client.is_paused():
                self.voice_client.play(
                    source=current.audio_from_source(),
                    after=self._after_play)
            self.voice_client.resume()

    def resume(self) -> None:
        """
        Resume playback of paused media.
        """
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()

    def pause(self) -> None:
        """
        Pause media playback without affecting tracking.
        """
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()

    def stop(self) -> None:
        """
        Stop media playback.
        """
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()

    def clear(self) -> None:
        """
        Remove all tracks from the queue, clear all temporary files and folders, and stop playback.
        """
        _clear_temp_folders()
        # Clear any and all queues in the multiqueue
        for queue in self._multiqueue:
            queue.clear()
        self._multiqueue.clear()
        self.stop()

    def remove_many(self, tracks: List[JukeboxItem]) -> None:
        """
        Remove all tracks in a list from the queue.
        """
        for track in tracks:
            self.remove(
                item=track,
                is_deleting=True)

    def shuffle(self, user_id: int) -> int:
        """
        Shuffles the queue in-place, stopping the currently-playing track and restarting with the new current track.
        """
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
        """
        Toggles global looping on the queue, re-appending the currently-played track when removed if enabled.
        """
        self.is_repeating = not self.is_repeating
        return self.is_repeating

    # Queue events

    def _after_play(self, error: Exception) -> None:
        """
        Logic and cleanup run after the currently-playing track has finished playback.
        :param error: Any exception raised by the playback task.
        """
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
            print(strings.get("log_console_media_end").format(current.title))

        if config.PLAYLIST_MULTIQUEUE:
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
        """
        Gets whether either a given user or this bot is currently connected to the voice channel.
        :param member: User instance to find in the voice channel users.
        """
        if not member:
            return self.voice_client and self.voice_client.is_connected()
        else:
            return member.voice and member.voice.channel and member.voice.channel.id == config.CHANNEL_VOICE

    def num_listeners(self) -> int:
        """
        Gets the number of users in the voice channel other than this bot.
        """
        return len(self.voice_client.channel.members) - 1 if self.is_in_voice_channel() else 0

    def current_track(self) -> Optional[JukeboxItem]:
        """
        Gets the track at the head of the queue.
        """
        if self.is_empty() or not any(self._multiqueue[self._multiqueue_index]):
            return None

        return self._multiqueue[self._multiqueue_index][0]

    def num_tracks(self) -> int:
        """
        Gets the total number of tracks in the queue.
        """
        return sum(len(queue) for queue in self._multiqueue)

    def is_empty(self) -> bool:
        """
        Gets whether the queue contains no tracks.
        """
        return all(not any(queue) for queue in self._multiqueue)


# Utility functions


def filter_func(info, *, incomplete) -> str:
    """
    Filter applied to all media being downloaded via YTDLP.
    """
    duration: int = info.get("duration")
    if duration > config.TRACK_DURATION_LIMIT:
        return strings.get("info_duration_exceeded").format(
            duration,
            config.TRACK_DURATION_LIMIT)


def _clear_temp_folders() -> None:
    """
    Clear all temporary files and folders, removing any cached or preloaded media, and restoring the empty folders.
    """
    try:
        fp: str = config.TEMP_DIR
        if os.path.exists(fp):
            shutil.rmtree(fp)
        os.mkdir(fp)
    except Exception as error:
        err.log(error)


# YTDL config


config.YTDL_OPTIONS["match_filter"] = filter_func
ytdlconn: yt_dlp.YoutubeDL = yt_dlp.YoutubeDL(config.YTDL_OPTIONS)
"""YoutubeDL connection instance."""


# Init


jukebox: Jukebox = Jukebox()
"""Main instance of jukebox handler."""
