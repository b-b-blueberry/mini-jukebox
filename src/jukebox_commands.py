# Mini-Jukebox
# jukebox_commands.py
# Written by blueberry et al., 2022
# https://github.com/StardewValleyDiscord/mini-jukebox

"""
Contents:
    Votes
        Values
        Constants
        Init
        Utility functions
        Runtime events
    Command use restrictions
    Commands
        Classes
            MusicActivity
            AmbiguousSearchView
            AmbiguousSearchSelect
        Constants
        Init
        Default user commands
        Trusted user commands
        Admin commands
        Runtime events
        Vote finalisers
    Utility functions
    Discord.py boilerplate
"""

import json
import os
from io import StringIO

# import pkg_resources
import random
import re
import sys
from datetime import date, datetime
from importlib import reload
from importlib import metadata
from math import ceil, floor
from typing import List, Dict, Union, Optional, Any, Tuple
from urllib import request

import discord
import yt_dlp
from discord import utils, Interaction, ClientException
from discord.ext import commands
from discord.ext.commands import Context
from lyricsgenius import Genius
from lyricsgenius.song import Song

import config
import jukebox_checks
import jukebox_impl
import strings
from jukebox_checks import is_admin, is_trusted, is_default, is_voice_only, is_looping_enabled, is_pausing_enabled
from jukebox_impl import jukebox, JukeboxItem
from db import DBUser


class Vote:
    # Values

    votes: Dict[discord.Message, "Vote"] = {}
    """Map of current votes keyed by their respective messages."""

    # Constants

    VOTE_SKIP: int = 1
    VOTE_DELETE: int = 2
    VOTE_WIPE: int = 3
    VOTE_RATIO: float = 0.3
    """Ratio of votes, for or against, to current listeners in order for a vote to be completed."""

    # Init

    def __init__(self, vote_type: int, allow_no: bool, extra_data: any = None, end_func: any = None) -> None:
        self.vote_type: int = vote_type
        """Type of vote being initiated."""
        self.allow_no: bool = allow_no
        """Whether the vote may be vetoed by people voting against it."""
        self.vote_data: any = extra_data
        """Any additional data to be parsed by the vote finaliser."""
        self.end_func: any = end_func
        """Function finalising the vote after vote succeeds, whether for or against."""

    # Utility functions

    @classmethod
    async def start_vote(cls, ctx: Context, vote: "Vote", start_msg: str) -> None:
        """
        Creates a message for a given vote and prepares reactions for users to add to.
        :param ctx:
        :param vote:
        :param start_msg: String to use as a subtitle in the vote message.
        """
        if any(v.vote_type == vote.vote_type for v in Vote.votes.values()):
            msg: str = strings.get("info_vote_in_progress")
            await ctx.reply(content=msg)
            return

        msg: str = strings.get("info_vote_start").format(start_msg)
        vote_message: discord.Message = await ctx.reply(content=msg)
        cls.votes[vote_message] = vote
        await vote_message.add_reaction(strings.emoji_vote_yes)
        if vote.allow_no:
            await vote_message.add_reaction(strings.emoji_vote_no)

    @classmethod
    async def check_vote(cls, reaction: discord.Reaction) -> None:
        """
        Checks whether a vote is completed based on a given reaction, and if so, runs its on-end function.
        :param reaction: Reaction object with emoji and number of reactions used to check vote progress.
        """
        vote: Vote = cls.votes.get(reaction.message)
        if vote:
            vote_count = reaction.count - 1  # We subtract 1 to discount this bots original reaction
            required_count = Vote.required_votes()
            vote_succeeded = reaction.emoji == strings.emoji_vote_yes and vote_count >= required_count
            vote_failed = vote.allow_no and reaction.emoji == strings.emoji_vote_no and vote_count > required_count
            if vote_succeeded or vote_failed:
                end_msg = strings.get("info_vote_success" if vote_succeeded else "info_vote_failure").format(
                    "{0}",
                    vote_count,
                    required_count,
                    reaction.emoji)
                cls.votes.pop(reaction.message)
                await vote.end_func(
                    ctx=reaction.message,
                    vote=vote,
                    success=vote_succeeded,
                    end_msg=end_msg)

    @classmethod
    async def clear_votes(cls) -> None:
        """
        Clears all current votes, replacing their respective messages with a self-destructing notice.
        """
        for message in cls.votes.keys():
            await message.edit(
                content=strings.get("info_vote_expire"),
                delete_after=10)
        cls.votes.clear()

    @classmethod
    def required_votes(cls) -> int:
        """
        Gets the number of votes, for or against, required for a vote to be completed.
        """
        return ceil(jukebox.num_listeners() * cls.VOTE_RATIO)

    # Runtime events

    @staticmethod
    async def on_reaction_add(reaction: discord.Reaction, user: discord.User) -> None:
        # Update votes based on reactions, ignoring reactions from users not in the designated text channel
        if reaction.message.channel.id == config.CHANNEL_TEXT \
                and not user.bot \
                and isinstance(user, discord.Member) \
                and jukebox.is_in_voice_channel(member=user):
            await Vote.check_vote(reaction=reaction)


# Commands


class Commands(commands.Cog, name=config.COG_COMMANDS):
    # Classes

    class MusicActivity(discord.Activity):
        def __init__(self, title):
            super().__init__(
                type=discord.ActivityType.listening,
                name=title
            )

    class AmbiguousTrackView(discord.ui.View):
        """
        Component view for a track selection menu used with ambiguous search commands.
        """
        def __init__(self, entries: List[dict], added_by: discord.User):
            super().__init__()

            self.added_by = added_by
            self.add_item(Commands.AmbiguousTrackSelect(entries=entries))

        async def interaction_check(self, interaction: Interaction, /) -> bool:
            """
            Override.
            Search queries can only be fulfilled by the original author.
            """
            return self.added_by.id == interaction.user.id

    class AmbiguousTrackSelect(discord.ui.Select):
        """
        Component view item for selecting a track from a limited set of similar results.
        """

        VALUE_CANCEL: str = "CANCEL"

        def __init__(self, entries: List[dict]):
            # Trim entries down to max allowed in a select menu
            self.entries: List[dict] = entries[:25]

            # Track result items
            options: List[discord.SelectOption] = [discord.SelectOption(
                label=track.get("title"),
                value=str(i),
                description=strings.get("jukebox_found_description").format(
                    track.get("uploader"),
                    format_duration(sec=track.get("duration"))),
                emoji=strings.emoji_digits[i + 1]
            ) for i, track in enumerate(entries)]

            # Cancel interaction item
            options.append(discord.SelectOption(
                label=strings.get("jukebox_found_cancel"),
                value=self.VALUE_CANCEL,
                emoji=strings.emoji_cancel))

            super().__init__(
                placeholder=strings.get("jukebox_found_placeholder"),
                min_values=0,
                max_values=1,
                options=options)

        async def callback(self, interaction: Interaction) -> Any:
            """
            Override.
            Handles interactions with track result options in select item.
            """
            if not any(self.values):
                return

            if self.values[0] == self.VALUE_CANCEL:
                # Delete original message on cancel
                await interaction.message.delete()
                return

            entry: dict = self.entries[int(self.values[0])]
            track: JukeboxItem = jukebox_impl.YTDLSource.entry_to_track(entry=entry, source=entry.get("url"), added_by=interaction.user)
            starting_from_empty: bool = jukebox.is_empty()

            # Join voice channel and start playing
            jukebox.append(track)
            await ensure_voice()
            if not jukebox.voice_client.is_playing() and not jukebox.voice_client.is_paused():
                jukebox.play()

            # Generate embed with track info
            description: str
            if starting_from_empty:
                description = strings.get("jukebox_current_added_by").format(
                    track.added_by.mention,
                    format_duration(sec=track.duration))
            else:
                index = jukebox.get_index_of_item(item=track)
                description = strings.get("jukebox_added_one").format(
                    track.title,
                    format_duration(sec=track.duration),
                    index + 1)
            embed: discord.Embed = get_current_track_embed(
                guild=interaction.guild,
                show_tracking=False,
                description=description)
            if embed:
                await interaction.response.edit_message(embed=embed, view=None)

    class AmbiguousLyricsView(discord.ui.View):
        """
        Component view for a lyrics selection menu used with ambiguous search commands.
        """
        def __init__(self, entries: List[dict], added_by: discord.User):
            super().__init__()

            self.added_by = added_by
            self.add_item(Commands.AmbiguousLyricsSelect(entries=entries))

    class AmbiguousLyricsSelect(discord.ui.Select):
        """
        Component view item for selecting lyrics from a limited set of similar results.
        """

        VALUE_CANCEL: str = "CANCEL"

        def __init__(self, entries: List[dict]):
            # Trim entries down to max allowed in a select menu
            self.entries: List[dict] = entries[:25]

            # Lyrics result items
            options: List[discord.SelectOption] = [discord.SelectOption(
                label=song.get("title"),
                value=str(i),
                description=strings.get("jukebox_found_description").format(
                    song.get("artist_names"),
                    song.get("release_date_components").get("year"))
                if song.get("release_date_components")
                else song.get("artist_names"),
                emoji=strings.emoji_digits[i + 1]
            ) for i, song in enumerate(entries)]

            # Cancel interaction item
            options.append(discord.SelectOption(
                label=strings.get("jukebox_found_cancel"),
                value=self.VALUE_CANCEL,
                emoji=strings.emoji_cancel))

            super().__init__(
                placeholder=strings.get("jukebox_found_placeholder"),
                min_values=0,
                max_values=1,
                options=options)

        async def callback(self, interaction: Interaction) -> Any:
            """
            Override.
            Handles interactions with track result options in select item.
            """
            if not any(self.values):
                return

            if self.values[0] == self.VALUE_CANCEL:
                # Delete original message on cancel
                await interaction.message.delete()
                return

            # Generate response
            await interaction.response.defer()
            genius: Genius = get_genius()
            entry: dict = self.entries[int(self.values[0])]
            response: dict = genius.song(song_id=entry.get("id"))
            lyrics: str = genius.lyrics(song_url=entry.get("url"))
            song: Song = Song(json_dict=response, lyrics=lyrics)
            embed: discord.Embed = get_lyrics_embed(guild=interaction.guild, song=song)
            await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=None)

    # Values

    bot: commands.Bot = None
    """Reference bot instance."""
    is_blocking_commands: bool = False
    """Whether commands are blocked for non-admin users."""
    listening_users: Dict[int, int] = {}
    """Map of users in the voice channel on track playback started, and the track timestamp they joined at."""
    start_time: datetime = datetime.utcnow()
    """Datetime instance recording start time for commands cog."""

    # Constants

    ERROR_BAD_PARAMS: str = "Bad command paramters: {0}"
    """Error string for commands with invalid parameters."""

    # Init

    def __init__(self):
        pass

    # Default user commands

    @commands.command(name="add?", aliases=["a?"])
    @commands.check(is_default)
    @commands.check(is_voice_only)
    async def add_ambiguous(self, ctx: Context, *, query: str = None) -> None:
        """
        :param ctx:
        :param query: A URL or generic search for the default configured domains for artist, album, or song title.
        """
        msg: Optional[str] = None
        embed: Optional[discord.Embed] = None

        # Resolve query
        query = parse_query(query=query)

        async with ctx.typing():
            try:
                if not jukebox.is_in_voice_channel(member=ctx.author):
                    # Users can only play the jukebox if they're in the voice channel
                    msg = strings.get("error_command_voice_only").format(
                        Commands.bot.get_channel(config.CHANNEL_VOICE).mention)
                else:
                    # Fetch metadata for tracks based on the given query
                    entries: List[dict] = await jukebox_impl.YTDLSource.get_playlist_info(
                        query=query,
                        loop=Commands.bot.loop,
                        ambiguous=True)

                    if not any(entries):
                        msg = strings.get("error_track")
                    else:
                        title: str = strings.get("jukebox_found_title").format(ctx.author.display_name)
                        embed = discord.Embed(
                            colour=get_embed_colour(ctx.guild))
                        embed.set_author(name=title, icon_url=ctx.author.display_avatar.url)
            except yt_dlp.DownloadError:
                # Suppress and message download errors
                msg = strings.get("error_download")

            if embed:
                view: Commands.AmbiguousTrackView = Commands.AmbiguousTrackView(entries=entries, added_by=ctx.author)
                await ctx.reply(embed=embed, view=view)
            elif msg:
                await ctx.reply(content=msg)

    @commands.command(name="add", aliases=["a"])
    @commands.check(is_default)
    @commands.check(is_voice_only)
    async def add(self, ctx: Context, *, query: str = None) -> None:
        """
        Adds a track to the tail of the queue, searching online for a given query to source audio.
        :param ctx:
        :param query: A URL or generic search for the default configured domains for artist, album, or song title.
        """
        msg: Optional[str] = None
        embed: Optional[discord.Embed] = None
        description: Optional[str] = None
        current: Optional[JukeboxItem] = None

        if query and query.isdigit():
            # Digit queries search by index in queue to re-add a track
            current = jukebox.get_item_by_index(index=int(query))
            if not current:
                raise commands.errors.BadArgument(self.ERROR_BAD_PARAMS.format(query))
            else:
                query = current.title

            # Resolve query
            query = parse_query(query=query)

        async with ctx.typing():
            try:
                if not query:
                    # Without a search query, try to resume the last-playing track if paused
                    if jukebox.is_empty():
                        # Resuming an empty queue does nothing
                        embed = get_empty_queue_embed(guild=ctx.guild)
                    else:
                        if not jukebox.is_in_voice_channel(member=ctx.author):
                            # Users can only play the jukebox if they're in the voice channel
                            msg = strings.get("error_command_voice_only").format(
                                Commands.bot.get_channel(config.CHANNEL_VOICE).mention)
                        else:
                            # Playing a populated queue will continue from the current track
                            await ensure_voice()
                            if not jukebox.voice_client.is_playing() and not jukebox.voice_client.is_paused():
                                jukebox.play()

                            current = jukebox.current_track()
                            description = strings.get("jukebox_current_added_by").format(
                                current.added_by.mention,
                                format_duration(sec=current.duration))
                            embed = get_current_track_embed(
                                guild=ctx.guild,
                                show_tracking=current and current.audio and current.audio.progress() > 5,
                                description=description)
                else:
                    # Otherwise, try to play a track based on the given URL or search query
                    entries: List[dict]
                    title: str
                    source: str
                    num_failed: int
                    playlist_items: List[JukeboxItem] = []
                    playlist_duration: int = 0

                    # Fetch metadata for tracks
                    entries, title, source, num_failed = await jukebox_impl.YTDLSource.get_playlist_info(
                        query=query,
                        loop=Commands.bot.loop)

                    # Parse results into an embed, add as many tracks as possible
                    if not source:
                        msg = strings.get("error_track")
                    elif not any(entries):
                        msg = strings.get("error_track" if num_failed < 2 else "error_track_all")
                    else:
                        extractor: str = entries[0].get("extractor").split(sep=":")[0] \
                            if entries[0] and "extractor" in entries[0].keys() \
                            else None
                        if not extractor:
                            # Check for invalid extractors
                            msg = strings.get("error_extractor_not_found").format(query)
                        elif extractor not in config.YTDL_ALLOWED_EXTRACTORS:
                            # Check for untrusted extractors
                            msg = strings.get("error_domain_not_whitelisted").format(extractor)
                        else:
                            # Check for excessively large track lists
                            playlist_duration = sum([int(track.get("duration", 0)) for track in entries])

                            # Prepare the playlist audio files
                            playlist_items = await jukebox_impl.YTDLSource.get_playlist_files(
                                playlist_info=entries,
                                is_streaming=config.PLAYLIST_STREAMING,
                                added_by=ctx.author)

                    # If no messages (errors) were made, add tracks to the queue
                    if not msg and any(playlist_items):
                        for playlist_item in playlist_items:
                            jukebox.append(item=playlist_item)

                        playlist_head: JukeboxItem = playlist_items[0]

                        # Join voice and start playing if not currently playing and command user is in voice
                        if not (jukebox.voice_client and jukebox.voice_client.is_playing()) and jukebox.is_in_voice_channel(ctx.author):
                            await ensure_voice()
                            jukebox.play()

                            if len(playlist_items) == 1:
                                # One track was added to an empty queue
                                description = strings.get("jukebox_current_added_by").format(
                                    playlist_head.added_by.mention,
                                    format_duration(sec=playlist_head.duration))
                            elif num_failed < 1:
                                # Several tracks in a playlist were added to an empty queue
                                description = strings.get("jukebox_current_added_playlist").format(
                                    title,
                                    format_duration(sec=playlist_duration, is_playlist=True),
                                    len(playlist_items))
                        elif len(playlist_items) == 1:
                            # One track was added to a populated queue
                            description = strings.get("jukebox_added_one").format(
                                playlist_head.title,
                                format_duration(sec=playlist_head.duration),
                                jukebox.get_index_of_item(playlist_head) + 1)
                        elif 0 < num_failed < len(entries):
                            # One or more tracks in a playlist failed to download
                            description = strings.get("jukebox_current_added_playlist").format(
                                title,
                                format_duration(sec=playlist_duration, is_playlist=True),
                                len(playlist_items)) + "\n" + strings.get("error_track_some").format(num_failed)
                        else:
                            # Several tracks in a playlist were added to a populated queue
                            description = strings.get("jukebox_added_many").format(
                                title,
                                format_duration(sec=playlist_duration, is_playlist=True),
                                jukebox.get_index_of_item(playlist_head) + 1,
                                len(playlist_items))
            except yt_dlp.DownloadError:
                # Suppress and message download errors
                msg = strings.get("error_download")
            if description and not embed:
                embed = get_current_track_embed(
                    guild=ctx.guild,
                    show_tracking=False,
                    description=description)
            if msg or embed:
                await ctx.reply(content=msg, embed=embed)

        # Update rich presence
        await self._update_presence()

    @commands.command(name="resume", aliases=["r"])
    @commands.check(is_default)
    @commands.check(is_voice_only)
    async def resume(self, ctx: Context) -> None:
        """
        Resumes playback if paused. Equivalent to using Add command without a query.
        """
        await self.add(ctx)

    @commands.command(name="skip", aliases=["s"])
    @commands.check(is_default)
    @commands.check(is_voice_only)
    async def skip(self, ctx: Context, skip_count: int = 1) -> None:
        """
        Removes a given number of tracks from the head of the queue.
        :param ctx:
        :param skip_count: Number of tracks to remove.
        """
        msg: Optional[str] = None
        async with ctx.typing():
            if jukebox.is_empty():
                msg = get_empty_queue_msg()
            else:
                tracks: List[JukeboxItem] = jukebox.get_range(index_start=0, index_end=skip_count)
                if all(track.added_by is ctx.message.author for track in tracks) or await is_admin(ctx=ctx, send_message=False) \
                        or Vote.required_votes() <= 1:
                    await self._do_skip(
                        ctx=ctx,
                        extra_data=tracks)
                elif await is_trusted(ctx=ctx, send_message=False):
                    vote_msg: str = strings.get("info_vote_skip").format(
                        skip_count,
                        ctx.message.author.mention)
                    vote: Vote = Vote(
                        vote_type=Vote.VOTE_SKIP,
                        allow_no=False,
                        extra_data=tracks,
                        end_func=self._do_skip)
                    await Vote.start_vote(
                        ctx=ctx,
                        vote=vote,
                        start_msg=vote_msg)
                else:
                    msg = strings.get("error_privileges_other").format(
                        ctx.guild.get_role(config.ROLE_TRUSTED).mention,
                        ctx.command)
            if msg:
                await ctx.reply(content=msg)

    @commands.command(name="delete", aliases=["d"])
    @commands.check(is_default)
    async def delete(self, ctx: Context, index: int = 1) -> None:
        """
        Removes a track from the queue.
        :param ctx:
        :param index: Index of the track to remove from the queue.
        Index is user-facing, starting from 1, adjusted for row-major traversal.
        """
        index -= 1
        track: JukeboxItem = jukebox.get_item_by_index(index=index)
        if not track:
            raise commands.errors.BadArgument(self.ERROR_BAD_PARAMS.format(index))

        msg: Optional[str] = None
        async with ctx.typing():
            if jukebox.is_empty():
                msg = get_empty_queue_msg()
            elif track.added_by.id == ctx.author.id or await is_admin(ctx=ctx, send_message=False) \
                    or Vote.required_votes() <= 1:
                # For track-owner and admin calls, wipe the queue immediately
                await self._do_delete(
                    ctx=ctx,
                    extra_data=index)
            elif await is_trusted(ctx=ctx, send_message=False):
                # Start a vote to wipe the target track
                vote_msg: str = strings.get("info_vote_delete").format(
                    track.title,
                    ctx.message.author.mention,
                    track.added_by.mention)
                vote: Vote = Vote(
                        vote_type=Vote.VOTE_DELETE,
                        allow_no=False,
                        extra_data=index,
                        end_func=self._do_delete)
                await Vote.start_vote(
                    ctx=ctx,
                    vote=vote,
                    start_msg=vote_msg)
            else:
                msg = strings.get("error_privileges_other").format(
                    ctx.guild.get_role(config.ROLE_TRUSTED).mention,
                    ctx.command)
        if msg:
            await ctx.reply(content=msg)

    @commands.command(name="shuffle", aliases=["f"])
    @commands.check(is_default)
    @commands.check(is_voice_only)
    async def shuffle(self, ctx: Context) -> None:
        """
        Shuffles the queue in-place, stopping the currently-playing track and restarting with the new current track.
        """
        async with ctx.typing():
            msg: str
            queue: List[JukeboxItem] = jukebox.get_queue(ctx.author.id)
            if not any(queue):
                # Shuffling an empty queue does nothing
                msg = get_empty_queue_msg()
            elif len(queue) == 1:
                # Shuffling a single track also does nothing
                msg = strings.get("jukebox_shuffled_one").format(
                    strings.emoji_refresh)
            else:
                # Shuffling a populated queue reorders the tracks and restarts the new currently-playing track
                shuffle_count: int = jukebox.shuffle(user_id=queue[0].added_by.id)
                msg = strings.get("jukebox_shuffled").format(
                    queue[0].title,
                    shuffle_count,
                    strings.emoji_shuffle)
            await ctx.reply(content=msg)

    @commands.command(name="bump", aliases=["b"])
    @commands.check(is_default)
    @commands.check(is_voice_only)
    async def bump(self, ctx: Context, index: int = -1) -> None:
        """
        Bumps a track up to the head of the queue.
        """
        msg: Optional[str] = None
        async with ctx.typing():
            is_implicit: bool = index != -1
            queue: List[JukeboxItem] = jukebox.get_queue(user_id=ctx.author.id)
            index = index if index > 0 else len(queue) if queue else 0  # Use track at end of queue if index not given
            current: JukeboxItem = jukebox.current_track()  # Current track is ignored for bumping
            track: JukeboxItem = jukebox.get_item_by_index(index=index - 1)  # Reduce given index for 0-indexing
            is_valid_user = track.added_by.id == ctx.author.id \
                or (await is_admin(ctx=ctx, send_message=False) and not is_implicit)
            if jukebox.is_empty():
                # Ignore if no tracks are in the queue
                msg = get_empty_queue_msg()
            elif not track:
                # Ignore if no track was at the given index
                msg = strings.get("error_bump_not_found")
            elif not is_valid_user:
                # Ignore tracks added by other users, and prevent admins from bumping others implicitly
                msg = strings.get("error_bump_user").format(
                    track.title,
                    track.added_by.mention,
                    index)
            elif (current and track and current is track) \
                    or (current and queue and len(queue) > 1 and current in queue and queue[1] is track) \
                    or (queue and any(queue) and queue[0] is track):
                # Ignore attempts to bump the currently-playing track or tracks at the head of the queue
                msg = strings.get("error_bump_current_at_end" if is_implicit else "error_bump_current")
            else:
                # Bump the track
                jukebox.bump(item=track)
                msg = strings.get("jukebox_bump").format(
                    strings.emoji_bump,
                    track.title,
                    format_duration(sec=track.duration, is_playlist=False),
                    jukebox.get_index_of_item(item=track) + 1)  # Increase result index for 1-indexing
        if msg:
            await ctx.reply(content=msg)

    @commands.command(name="wipe", aliases=["w"])
    @commands.check(is_default)
    async def wipe(self, ctx: Context, *, query: str = None) -> None:
        """
        Removes all tracks added by a given user from the queue.
        :param ctx:
        :param query: A generic search query for users by name or ID, defaults to the command user.
        """
        msg: Optional[str] = None
        async with ctx.typing():
            try:
                # Accept users by fuzzy query
                if not query:
                    query = ctx.author.id
                user: discord.User = await commands.UserConverter().convert(
                    ctx=ctx,
                    argument=str(query))
                # Wipe all tracks from a user in the given queue
                queue: List[JukeboxItem] = jukebox.get_queue(user_id=user.id)
                if not any(queue):
                    msg = get_empty_queue_msg()
                # For multiqueue, we can assume all tracks in a user's queue are their own
                tracks: List[JukeboxItem] = [track for track in queue if track.added_by.id == user.id] \
                    if not config.PLAYLIST_MULTIQUEUE \
                    else [*queue]  # Use a copy of the tracks to avoid issues when removing
                if not any(tracks):
                    # Ignore calls to wipe an empty queue
                    msg = strings.get("info_wipe_failure")
                elif user.id == ctx.author.id or await is_admin(ctx=ctx, send_message=False) \
                        or all(track.added_by.id == ctx.author.id for track in tracks) \
                        or Vote.required_votes() <= 1:
                    # For queue-owner and admin calls, wipe the queue immediately
                    await self._do_wipe(
                        ctx=ctx,
                        extra_data=tracks)
                elif await is_trusted(ctx=ctx, send_message=False):
                    # For non-queue-owner calls, start a vote to wipe the target user's queue
                    vote_msg: str = strings.get("info_vote_wipe").format(
                        len(tracks),
                        ctx.message.author.mention,
                        tracks[0].added_by.mention)
                    vote: Vote = Vote(
                        vote_type=Vote.VOTE_WIPE,
                        allow_no=False,
                        extra_data=tracks,
                        end_func=self._do_wipe)
                    await Vote.start_vote(
                        ctx=ctx,
                        vote=vote,
                        start_msg=vote_msg)
                else:
                    msg = strings.get("error_privileges_other").format(
                        ctx.guild.get_role(config.ROLE_TRUSTED).mention,
                        ctx.command)
            except commands.UserNotFound:
                msg = strings.get("error_user_not_found").format(query)
            if msg:
                await ctx.reply(content=msg)

    @commands.command(name="queue", aliases=["q"])
    @commands.check(is_default)
    async def print_all(self, ctx: Context, page_num: Union[str, int] = "1") -> None:
        """
        Generate a formatted embed with info for a paginated set of tracks from the queue to send in the command channel.
        :param ctx:
        :param page_num: Page number to print from paginated queue.
        """
        async with ctx.typing():
            embed: discord.Embed
            if jukebox.is_empty():
                embed = get_empty_queue_embed(guild=ctx.guild)
            else:
                queue_length: int = jukebox.num_tracks()
                queue_duration: str = format_duration(sec=sum([track.duration for track in jukebox.get_all()]), is_playlist=True)

                # Pagination is bounded to length of the playlist
                pagination_count: int = 10
                page_max: int = ceil(queue_length / pagination_count)
                page_num = int(page_num)
                if page_num * pagination_count > queue_length:
                    page_num = page_max
                if page_num < 1:
                    page_num = 1
                page_num -= 1

                # Print playlist by elements for the selected (or default) page
                msg_lines: List[str] = []
                current: JukeboxItem = jukebox.current_track()

                # aggregated tracks
                index_start: int = pagination_count * page_num
                index_end: int = index_start + pagination_count
                tracks: List[JukeboxItem] = jukebox.get_range(index_start=index_start, index_end=index_end)
                track_msgs: List[str] = [strings.get("jukebox_queue_item").format(
                    index_start + i + 1,
                    format_duration(sec=track.duration),
                    track.added_by.mention,
                    track.title)
                        for i, track in enumerate(iterable=tracks)]

                # currently-playing track
                title: str = strings.get("jukebox_title").format(
                    strings.get("status_playing").format(current.title, strings.emoji_play)
                    if jukebox.voice_client and jukebox.voice_client.is_playing()
                    else strings.get("status_paused").format(current.title, strings.emoji_pause))

                # all other queued tracks on the current page
                msg_lines.append("\n".join(iter(track_msgs)))

                # queue loop status
                if await is_looping_enabled(ctx=ctx):
                    msg_lines.append("\n" + strings.get("status_looping").format(
                        strings.get("on") if jukebox.is_looping else strings.get("off"),
                        strings.emoji_loop))

                # queue summary
                footer: str = strings.get("jukebox_queue_footer").format(
                    queue_length,
                    queue_duration,
                    page_num + 1,
                    page_max)

                emoji: discord.Emoji = utils.get(Commands.bot.emojis, name=strings.get("emoji_id_jukebox"))
                embed = discord.Embed(
                    title=title,
                    description="\n".join(msg_lines),
                    colour=get_embed_colour(ctx.guild),
                    url=current.url
                    if current
                    else None)
                embed \
                    .set_footer(text=footer) \
                    .set_thumbnail(url=emoji.url)

            if embed:
                await ctx.reply(embed=embed)

    @commands.command(name="current", aliases=["c"])
    @commands.check(is_default)
    async def print_current(self, ctx: Context) -> None:
        """
        Fetch a formatted embed for the currently-playing track to send in the command channel.
        """
        embed: discord.Embed = get_current_track_embed(guild=ctx.guild, show_tracking=True)
        await ctx.reply(embed=embed)

    @commands.command(name="user", aliases=["u"])
    @commands.check(is_admin)
    async def print_user(self, ctx: Context, query: str = None) -> None:
        """
        Generate a formatted embed with info for a user's stats to send in the command channel.
        :param ctx:
        :param query: A generic search query for users by name or ID, defaults to the command user.
        """
        msg: Optional[str] = None
        embed: Optional[discord.Embed] = None
        async with ctx.typing():
            msg, embed = await self._do_print_user(ctx=ctx, query=query)
            if msg or embed:
                await ctx.reply(content=msg, embed=embed)

    @commands.command(name="jukebox", aliases=["j"])
    @commands.check(is_admin)
    async def print_jukebox(self, ctx: Context) -> None:
        """
        Generate a formatted embed with info for the jukebox stats to send in the command channel.
        """
        msg: Optional[str] = None
        embed: Optional[discord.Embed] = None
        async with ctx.typing():
            msg, embed = await self._do_print_user(ctx=ctx, query=str(Commands.bot.user.id))
            if msg or embed:
                await ctx.reply(content=msg, embed=embed)

    @commands.command(name="info", aliases=["i"])
    @commands.check(is_default)
    async def print_info(self, ctx: Context) -> None:
        """
        Send info about the jukebox in the command channel.
        """
        await ctx.reply(strings.get("info_help").format(
            ctx.guild.get_channel(config.CHANNEL_TEXT).mention,
            strings.emoji_pin))

    # Trusted user commands

    @commands.command(name="lyrics?", aliases=["l?"])
    @commands.check(is_trusted)
    async def lyrics_ambiguous(self, ctx: Context, *, query: str = None) -> None:
        """
        :param ctx:
        :param query: A generic search query relating to an artist, album, or song title.
        """
        msg: Optional[str] = None
        embed: Optional[discord.Embed] = None
        genius: Genius = get_genius()

        async with ctx.typing():
            # Resolve query
            query = parse_query(query=query)
            if not query and jukebox.is_empty():
                embed = get_empty_queue_embed(guild=ctx.guild)
            else:
                # Generate response
                response: dict = genius.search_songs(search_term=query)
                entries: List[Dict[str, str]] = [hit.get("result") for hit in response.get("hits", [])]
                if not any(entries):
                    msg = strings.get("error_lyrics_not_found").format(query)
                else:
                    title: str = strings.get("jukebox_found_lyrics").format(ctx.author.display_name)
                    embed = discord.Embed(
                        colour=get_embed_colour(ctx.guild))
                    embed.set_author(name=title, icon_url=ctx.author.display_avatar.url)

            if embed:
                view: Commands.AmbiguousLyricsView = Commands.AmbiguousLyricsView(entries=entries, added_by=ctx.author)
                await ctx.reply(embed=embed, view=view)
                pass
            elif msg:
                await ctx.reply(content=msg)

    @commands.command(name="lyrics", aliases=["l"])
    @commands.check(is_trusted)
    async def lyrics(self, ctx: Context, *, query: str = None) -> None:
        """
        Fetch lyrics for a given index or search query and generate a formatted embed.
        :param ctx:
        :param query: A generic search query relating to an artist, album, or song title.
        """
        msg: Optional[str] = None
        embed: Optional[discord.Embed] = None
        genius: Genius = get_genius()

        async with ctx.typing():
            # Resolve query
            query = parse_query(query=query)
            if not query and jukebox.is_empty():
                embed = get_empty_queue_embed(guild=ctx.guild)
            else:
                # Generate response
                song: Optional[Song] = genius.search_song(title=query)
                if not song:
                    msg = strings.get("error_lyrics_not_found").format(query)
                else:
                    embed = get_lyrics_embed(guild=ctx.guild, song=song)
            if msg or embed:
                await ctx.reply(
                    content=msg,
                    embed=embed)

    @commands.command(name="pause", aliases=["p"])
    @commands.check(is_trusted)
    @commands.check(is_voice_only)
    @commands.check(is_pausing_enabled)
    async def toggle_pause(self, ctx: Context) -> None:
        """
        Pauses or resumes the currently-playing track with no change to the tracking.
        """
        async with ctx.typing():
            current: JukeboxItem = jukebox.current_track()
            if not current:
                # Empty jukebox queue does nothing when paused
                pass
            elif jukebox.voice_client and jukebox.voice_client.is_playing():
                # Pause the audio stream if playing
                jukebox.pause()
            else:
                # Playing a populated queue will continue from the current track
                await ensure_voice()
                if jukebox.voice_client.is_paused():
                    jukebox.resume()
                else:
                    jukebox.play()

            embed: discord.Embed = get_current_track_embed(guild=ctx.guild, show_tracking=True)
            await ctx.reply(embed=embed)

        # Update rich presence
        await self._update_presence()

    @commands.command(name="loop", aliases=["o"])
    @commands.check(is_trusted)
    @commands.check(is_voice_only)
    @commands.check(is_looping_enabled)
    async def toggle_loop(self, ctx: Context) -> None:
        """
        Toggles global looping on the queue, re-appending the currently-played track when removed if enabled.
        """
        jukebox.loop()
        msg: str = strings.get("status_looping").format(
            strings.get("on")
            if jukebox.is_looping
            else strings.get("off"),
            strings.emoji_loop)
        if msg:
            await ctx.reply(content=msg)

    # Admin commands

    @commands.command(name="leave", aliases=[])
    @commands.check(is_admin)
    async def leave_voice(self, ctx: Context) -> None:
        """
        Removes the bot from the voice channel and stops the currently-playing track.
        """
        print("Leaving voice with {3} listeners. [{0}#{1} ({2})]".format(
            ctx.author.name,
            ctx.author.discriminator,
            ctx.author.id,
            jukebox.num_listeners()))
        jukebox.stop()
        if jukebox.voice_client:
            await jukebox.voice_client.disconnect()
        await ctx.message.add_reaction(strings.emoji_confirm)

        # Update rich presence
        await self._update_presence()

    @commands.command(name="cleartracks", aliases=[])
    @commands.check(is_admin)
    async def clear_tracks(self, ctx: Context) -> None:
        """
        Clears any tracks from the queue without running their after-play behaviours.
        Also clears temp files and folders.
        """
        print("Clearing {3} tracks. [{0}#{1} ({2})]".format(
            ctx.author.name,
            ctx.author.discriminator,
            ctx.author.id,
            jukebox.num_tracks()))
        jukebox.clear()
        await ctx.message.add_reaction(strings.emoji_confirm)

        # Update rich presence
        await self._update_presence()

    @commands.command(name="clearvotes", aliases=[])
    @commands.check(is_admin)
    async def clear_votes(self, ctx: Context) -> None:
        """
        Clears any current votes without running their after-vote behaviours.
        """
        print("Clearing {3} votes. [{0}#{1} ({2})]".format(
            ctx.author.name,
            ctx.author.discriminator,
            ctx.author.id,
            len(Vote.votes)))
        await Vote.clear_votes()
        await ctx.message.add_reaction(strings.emoji_confirm)

    @commands.command(name="lock", aliases=[])
    @commands.check(is_admin)
    async def block_commands(self, ctx: Context) -> None:
        """
        Block all commands from being used by non-admin users.
        """
        print("Blocking commands. [{0}#{1} ({2})]".format(
            ctx.author.name,
            ctx.author.discriminator,
            ctx.author.id))
        Commands.is_blocking_commands = True
        await ctx.message.add_reaction(strings.emoji_lock_on)

    @commands.command(name="unlock", aliases=[])
    @commands.check(is_admin)
    async def unblock_commands(self, ctx: Context) -> None:
        """
        Unblock commands, re-enabling the jukebox for non-admin users.
        """
        print("Unblocking commands. [{0}#{1} ({2})]".format(
            ctx.author.name,
            ctx.author.discriminator,
            ctx.author.id))
        Commands.is_blocking_commands = False
        await ctx.message.add_reaction(strings.emoji_lock_off)

    @commands.command(name="mango", aliases=[])
    @commands.check(is_admin)
    async def activate_mango(self, ctx: Context) -> None:
        """
        Activates mango.
        """
        print("Activating mango. [{0}#{1} ({2})]".format(
            ctx.author.name,
            ctx.author.discriminator,
            ctx.author.id))
        emoji: discord.Emoji = utils.get(jukebox.bot.emojis, name=strings.get("emoji_id_mango"))
        await ctx.message.add_reaction(emoji)

    @commands.command(name="reloadcommands", aliases=[], hidden=True)
    @commands.check(is_admin)
    async def reload_commands(self, ctx: Context) -> None:
        """
        Reloads the commands extension, reapplying code changes and reloading the strings data file.
        """
        print("Reloading commands. [{0}#{1} ({2})]".format(
            ctx.author.name,
            ctx.author.discriminator,
            ctx.author.id))
        await Commands.bot.reload_extension(name=config.PACKAGE_COMMANDS)
        await ctx.message.add_reaction(strings.emoji_confirm)

    @commands.command(name="send", hidden=True)
    @commands.check(is_admin)
    async def send_message(self, ctx: Context, query: str, *, content: str) -> None:
        """
        Sends a message in a given channel.
        :param ctx:
        :param query: Query for Discord channel to send message in.
        :param content: Message content to send.
        :return:
        """
        if not content:
            content = " "
        content = content[:2000]
        channel: discord.abc.GuildChannel = query_channel(guild=ctx.guild, query=query)
        if content and isinstance(channel, discord.TextChannel):
            message: discord.Message = await channel.send(content=content)
            msg = strings.get("info_send_message").format(message.jump_url)
        else:
            msg = strings.get("error_send_message")
        await ctx.reply(content=msg)

    @commands.command(name="edit", hidden=True)
    @commands.check(is_admin)
    async def edit_message(self, ctx: Context, message_id: int, *, content: str) -> None:
        """
        Edits a message in the current guild.
        :param ctx:
        :param message_id: Discord message ID to edit.
        :param content: Message content to use.
        """
        if not content:
            content = " "
        content = content[:2000]
        msg: str
        message: discord.Message = await get_guild_message(guild=ctx.guild, message_id=message_id)
        if content and message:
            await message.edit(content=content, embeds=message.embeds)
            msg = strings.get("info_send_message").format(message.jump_url)
        else:
            msg = strings.get("error_send_message")
        await ctx.reply(content=msg)

    @commands.command(name="pins", hidden=True)
    @commands.check(is_admin)
    async def update_pinned_messages(self, ctx: Context) -> None:
        """
        Sends or updates pinned messages in the commands channel.
        """
        print("Updating pinned messages. [{0}#{1} ({2})]".format(
            ctx.author.name,
            ctx.author.discriminator,
            ctx.author.id))
        channel: discord.TextChannel = Commands.bot.get_channel(config.CHANNEL_TEXT)
        messages: List[discord.Message] = await self._do_update_pinned_messages(
            ctx=ctx,
            channel=channel)
        msg: str = strings.get("info_update_pinned_messages").format(
            channel.mention,
            messages[0].jump_url)
        await ctx.reply(content=msg)
        await ctx.message.add_reaction(strings.emoji_confirm)

    @commands.command(name="avatar", hidden=True)
    @commands.check(is_admin)
    async def update_avatar(self, ctx: Context) -> None:
        """
        Updates bot client display picture.
        """
        print("Updating avatar. [{0}#{1} ({2})]".format(
            ctx.author.name,
            ctx.author.discriminator,
            ctx.author.id))

        msg: str = None
        attachment: discord.Attachment = None
        original_avatar: discord.File = None
        size_denom: int = 1000 * 1000
        size_max: int = 8

        # Fetch avatar from attachments
        if any(ctx.message.attachments):
            images: list = [a for a in ctx.message.attachments if re.match(r"image/(png|jpe?g)", a.content_type)]
            if any(images):
                images_usable: list = [a for a in images if a.size < size_denom * size_max]
                if not any(images_usable):
                    msg = strings.get("error_avatar_size").format(size_max)
                else:
                    attachment = images_usable[0]
        if not attachment:
            if not msg:
                msg = strings.get("error_avatar_not_found")
        else:
            original_avatar = await Commands.bot.user.display_avatar.to_file()
            attachment_bytes: bytes = await attachment.read()
            await Commands.bot.user.edit(avatar=attachment_bytes)
            await ctx.message.add_reaction(strings.emoji_confirm)
            msg = strings.get("info_update_avatar").format(attachment.filename)

        await ctx.reply(content=msg, file=original_avatar)

    @commands.command(name="str", hidden=True)
    @commands.check(is_admin)
    async def test_string(self, ctx: Context, string: str) -> None:
        """
        Test strings without formatting in the command channel.
        :param ctx:
        :param string: Key of string in strings data file.
        """
        msg: str = strings.get(string)
        await ctx.reply(content="{0}: {1}".format(string, msg)
                        if msg
                        else strings.get("error_string_not_found").format(string))

    @commands.command(name="send_bulletin", hidden=True)
    @commands.check(is_admin)
    async def send_bulletin(self, ctx: Context) -> None:
        embed: discord.Embed = await self._get_bulletin_embed(guild=ctx.guild)
        channel: discord.TextChannel = ctx.guild.get_channel(config.CHANNEL_BULLETIN)
        message: discord.Message = await channel.send(embed=embed)
        for emoji_id in ["emoji_id_nukebox", "emoji_id_pam", "emoji_id_mango"]:
            emoji: discord.Emoji = utils.get(Commands.bot.emojis, name=strings.get(emoji_id))
            await message.add_reaction(emoji)

    @commands.command(name="uptime", aliases=["runtime"], hidden=True)
    @commands.check(is_admin)
    async def send_uptime(self, ctx: Context):
        """
        Prints start and current running times for the bot.
        """
        msg: str
        embed: discord.Embed = discord.Embed(colour=get_embed_colour(ctx.guild))

        delta_uptime = datetime.utcnow() - Commands.bot.start_time
        hours, remainder = divmod(int(delta_uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)

        msg = strings.get("info_uptime_bot").format(
            days, hours, minutes, seconds,
            Commands.bot.start_time.strftime(strings.get("datetime_format_uptime")))
        embed.add_field(name=strings.get("info_uptime_heading_bot"), value=msg, inline=False)

        msg = strings.get("info_uptime_cog").format(
            Commands.start_time.strftime(strings.get("datetime_format_uptime")))
        embed.add_field(name=strings.get("info_uptime_heading_cog"), value=msg, inline=False)

        await ctx.reply(embed=embed)

    # @commands.command(name="versions", aliases=["version", "vers", "ver"], hidden=True)
    # @commands.check(is_admin)
    # async def send_versions(self, ctx: Context) -> None:
    #     msg: str
    #     embed: discord.Embed = discord.Embed(colour=get_embed_colour(ctx.guild))

    #     # List major packages with additional information and source links
    #     embed.description = strings.get("info_package_major")
    #     embed.set_footer(text="Python " + sys.version)
    #     packages: dict = pkg_resources.working_set.by_key
    #     for key in config.PACKAGE_CHECKS:
    #         meta_dict: dict = dict(metadata.metadata(key))
    #         url = f'https://pypi.python.org/pypi/{key}/json'
    #         releases = json.loads(request.urlopen(url).read())['releases']
    #         msg = strings.get("info_package_major_entry").format(
    #             meta_dict["Version"],
    #             meta_dict["Summary"],
    #             meta_dict["Home-page"])
    #         release_key: str = list(releases.keys())[-1]
    #         if release_key != meta_dict["Version"]:
    #             msg += strings.get("info_package_update").format(
    #                 strings.emoji_star,
    #                 release_key,
    #                 re.split(r"([a-z])", releases[release_key][-1]["upload_time"], 1, flags=re.I)[0]
    #             )
    #         embed.add_field(name=meta_dict["Name"], value=msg, inline=False)

    #     # List minor packages with minimal name and version information
    #     embed.add_field(name=strings.get("info_package_minor"), value="  ".join([
    #         strings.get("info_package_minor_entry").format(key, packages[key].version)
    #         for key in packages
    #         if key not in config.PACKAGE_CHECKS
    #     ]))

    #     await ctx.reply(embed=embed)

    @commands.command(name="logs", aliases=["log"], hidden=True)
    @commands.check(is_admin)
    async def send_logs(self, ctx: Context) -> None:
        fps: List[str] = [
            os.path.join(config.LOG_DIR, file)
            for file in os.listdir(config.LOG_DIR)
        ]
        files: List[discord.File] = []
        for fp in fps:
            with open(file=fp, mode="r", encoding="utf8") as file:
                s: StringIO = StringIO()
                s.write(file.read())
                s.seek(0)
                files.append(discord.File(s, filename=os.path.basename(fp)))

        hours: float = float(datetime.now().astimezone().strftime("%z")) / 100
        msg: str = strings.get("info_logs" if files else "info_logs_none").format(
            Commands.bot.start_time.strftime(strings.get("datetime_format_uptime")),
            f"+{hours}" if hours > 0 else hours)
        await ctx.reply(content=msg, files=files)

    @commands.command(name="config", aliases=["cfg"], hidden=True)
    @commands.check(is_admin)
    async def send_config(self, ctx: Context) -> None:
        cfg = None
        with open(file=config.CONFIG_PATH, mode="r", encoding="utf8") as file:
            js: dict = json.load(file)
            js.pop("tokens")
            s: StringIO = StringIO()
            s.write(json.dumps(js, indent=2, sort_keys=False))
            s.seek(0)
            cfg = discord.File(s, filename=os.path.basename(config.CONFIG_PATH))
        msg: str = strings.get("info_config").format(Commands.bot.start_time.strftime(strings.get("datetime_format_uptime")))
        await ctx.reply(content=msg, file=cfg)

    # Runtime events

    @staticmethod
    async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        """
        Update state based on listeners in voice channel.
        """
        current: JukeboxItem = jukebox.current_track()
        if not after.channel or not after.channel.id == config.CHANNEL_VOICE or after.deaf or after.self_deaf:
            # Dismiss users who have left the voice channel or have deafened themselves
            if member.id in Commands.listening_users.keys():
                Commands.listening_users.pop(member.id)
        elif after.channel and after.channel.id == config.CHANNEL_VOICE:
            # Note the time that the user joined the voice channel or undeafened themselves
            Commands.listening_users[member.id] = current.audio.progress() if current and current.audio else 0

    def before_play(self, track: JukeboxItem) -> None:
        """
        Behaviours to be run before the currently-playing track first starts playback.
        """
        # Add all users in the voice channel as current listeners joining at 0 seconds
        Commands.listening_users = {user.id: 0 for user in jukebox.voice_client.channel.members}

        # Update tracks added for user once their track has begun playing:
        current: JukeboxItem = jukebox.current_track()
        entry: DBUser = Commands.bot.db.get_user(user_id=current.added_by.id)
        entry.tracks_added += 1
        Commands.bot.db.update_user(entry=entry)

    async def after_play(self, track: JukeboxItem) -> None:
        """
        Logic and cleanup to be run after the currently-playing track is removed from the queue.
        """
        # Clear votes
        await Vote.clear_votes()

        curr_month = format_month()
        # Update db
        for user_id in Commands.listening_users.keys():
            joined_at_duration: int = Commands.listening_users[user_id]
            entry: DBUser = Commands.bot.db.get_user(user_id=user_id)
            entry.tracks_listened += 1
            entry.duration_listened += track.duration - joined_at_duration
            if curr_month != entry.recent_month:
                entry.recent_month = curr_month
                entry.montly_listened = 0
            entry.montly_listened += track.duration - joined_at_duration
            Commands.bot.db.update_user(entry=entry)

        # Post now-playing update
        channel: discord.TextChannel = jukebox.bot.get_channel(config.CHANNEL_TEXT)
        embed: discord.Embed = get_current_track_embed(
            guild=channel.guild,
            show_tracking=False,
            previous_track=track)
        await channel.send(embed=embed)

        # Update rich presence
        await self._update_presence()

    # Activity methods

    async def _update_presence(self, track: JukeboxItem = None) -> None:
        activity: Optional[Commands.MusicActivity] = None
        if not track:
            track = jukebox.current_track()
        if track and jukebox.voice_client and jukebox.voice_client.is_playing():
            activity = Commands.MusicActivity(title=track.title)
        await Commands.bot.change_presence(activity=activity)

    # Vote finalisers

    async def _after_vote(self, ctx: Context):
        """
        Logic and cleanup called once any vote ends.
        """
        if any(Vote.votes):
            msg: str = strings.get("info_vote_collection_modified").format(len(Vote.votes))
            await ctx.send(content=msg)
            await Vote.clear_votes()

        # Update rich presence
        await self._update_presence()

    async def _do_skip(self, ctx: Context, vote: Optional[Vote] = None, success: bool = True,
                       extra_data: Optional[List[JukeboxItem]] = None, end_msg: str = "{0}") -> None:
        """
        Behaviours for handling a skip request.
        On success, a number of tracks will be removed from the head of the queue.
        :param ctx:
        :param vote: Vote for this action, if one exists.
        :param success: Whether to carry out the skip action.
        :param extra_data: List of tracks to be skipped, if no vote exists.
        :param end_msg: String to use as a subtitle in the vote-ended message.
        """
        msg: str = None
        if success:
            tracks: List[JukeboxItem] = vote.vote_data if vote else extra_data
            jukebox.remove_many(tracks=tracks)
            msg = strings.get("info_skip_success").format(
                len(tracks),
                strings.emoji_next)
        else:
            msg = strings.get("info_skip_failure")
        if msg:
            await ctx.reply(content=end_msg.format(msg))
        await self._after_vote(ctx=ctx)

    async def _do_delete(self, ctx: Context, vote: Optional[Vote] = None, success: bool = True,
                         extra_data: Optional[int] = None, end_msg: str = "{0}") -> None:
        """
        Behaviours for handling a delete request.
        On success, a single track at a given index will be removed from the queue.
        :param ctx:
        :param vote: Vote for this action, if one exists.
        :param success: Whether to carry out the delete action..
        :param extra_data: User-facing index (row-major) of item to be removed, if no vote exists.
        :param end_msg: String to use as a subtitle in the vote-ended message.
        """
        msg: str = None
        if success:
            index: int = vote.vote_data if vote else extra_data
            track: JukeboxItem = jukebox.get_item_by_index(index=index)
            if track:
                jukebox.remove(
                    track=track,
                    is_deleting=not jukebox.is_looping)
                msg = strings.get("info_delete_success").format(
                    track.title,
                    format_duration(sec=track.duration),
                    track.added_by.mention,
                    index + 1,
                    strings.emoji_next)
        else:
            msg = strings.get("info_skip_failure")
        if msg:
            await ctx.reply(content=end_msg.format(msg))
        await self._after_vote(ctx=ctx)

    async def _do_wipe(self, ctx: Context, vote: Optional[Vote] = None, success: bool = True,
                       extra_data: Optional[List[JukeboxItem]] = None, end_msg: str = "{0}") -> None:
        """
        Behaviours for handling a wipe request.
        On success, all tracks added by a certain user will be removed from the queue.
        :param ctx:
        :param vote: Vote for this action, if one exists.
        :param success: Whether to carry out the wipe action.
        :param extra_data: List of tracks to be removed, if no vote exists.
        :param end_msg: String to use as a subtitle in the vote-ended message.
        """
        msg: str = None
        if success:
            tracks = vote.vote_data if vote else extra_data
            num_tracks: int = len(tracks)
            jukebox.remove_many(tracks=tracks)
            msg = strings.get("info_wipe_success").format(
                num_tracks,
                tracks[0].added_by.mention,
                strings.emoji_next)
        else:
            msg = strings.get("info_skip_failure")
        if msg:
            await ctx.reply(content=end_msg.format(msg))
        await self._after_vote(ctx=ctx)

    async def _do_print_user(self, ctx: Context, query: str) -> Tuple[Optional[str], Optional[discord.Embed]]:
        """
        Behaviours for creating a formatted embed with jukebox usage stats.
        """
        msg: str = None
        embed: discord.Embed = None
        try:
            # Accept users by fuzzy query
            if not query:
                query = ctx.author.id
            user: discord.User = await commands.UserConverter().convert(
                ctx=ctx,
                argument=str(query))
            member: discord.Member = ctx.guild.get_member(user.id)
            is_jukebox: bool = user.id == Commands.bot.user.id

            # Cancel if user is valid but not in guild
            if not member:
                raise commands.UserNotFound(query)

            # Fetch user's jukebox stats
            entry: DBUser = Commands.bot.db.get_user(user_id=member.id)
            duration_formatted: str = format_user_playtime(sec=entry.duration_listened)
            monthly_formatted: str = format_user_playtime(sec=entry.montly_listened)
            curr_month: int = format_month()

            # Set description to user's jukebox stats
            is_new: bool = False
            info: List[str] = []
            if entry.tracks_added > 0:
                info.append(strings.get("jukebox_user_info_added").format(entry.tracks_added))
            if entry.tracks_listened > 0 or entry.duration_listened > 0:
                info.append(strings.get("jukebox_user_info_listened").format(entry.tracks_listened))
                info.append(strings.get("jukebox_user_info_duration").format(duration_formatted))
            if entry.recent_month == curr_month and entry.montly_listened > 0:
                info.append(strings.get("jukebox_user_info_monthly").format(monthly_formatted))
            info_str: str = "\n".join(info)

            visible_roles: Dict[int, str] = {
                config.ROLE_ADMIN: "emoji_id_junimo",
                config.ROLE_JUKEBOX: "emoji_id_jukebox",
                config.ROLE_TRUSTED: "emoji_id_gold",
                config.ROLE_DEFAULT: "emoji_id_vinyl"
            }

            # Set thumbnail to user's privilege icon
            member_visible_roles: List[Tuple[int, str]] = [
                (role_id, visible_roles.get(role_id))
                for role_id in visible_roles.keys()
                if any(role.id == role_id for role in member.roles)]
            emoji_id: str = member_visible_roles[0][1] if any(member_visible_roles) else "emoji_id_pam"
            emoji: discord.Emoji = utils.get(jukebox.bot.emojis, name=strings.get(emoji_id))
            role: discord.Role = ctx.guild.get_role(member_visible_roles[0][0]) if any(member_visible_roles) else None
            roles_str: str = "{0} {1}".format(emoji, role.mention) if role else None

            # Create embed
            embed = discord.Embed(
                description=strings.get("jukebox_user_empty") if is_new else None,
                colour=get_embed_colour(ctx.guild))
            embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
            if any(info):
                embed_name: str = strings.get("jukebox_user_info_guild") if is_jukebox else strings.get("jukebox_user_info_user")
                embed.add_field(name=embed_name, value=info_str, inline=False)
            if is_jukebox:
                embed.set_thumbnail(url=emoji.url)
            elif roles_str:
                embed.add_field(name=strings.get("jukebox_user_info_roles"), value=roles_str, inline=False)
        except commands.UserNotFound:
            msg = strings.get("error_user_not_found").format(query)

        return msg, embed

    async def _do_update_pinned_messages(self, ctx: Context, channel: discord.TextChannel) -> List[discord.Message]:
        """
        Behaviours for sending or editing pinned text channel messages outlining jukebox info and rules.
        """
        message_contents: List[str]
        with open(file=config.PINS_PATH, mode="r", encoding="utf8") as file:
            message_contents = json.load(file).get("messages")

        message_ids_separator: str = ' '
        message_ids_raw: str = Commands.bot.db.get_rules_message_ids(guild_id=ctx.guild.id)
        messages: List[discord.Message] = []
        if message_ids_raw:
            try:
                # Fetch messages from saved IDs
                messages = [await channel.fetch_message(int(s)) for s in message_ids_raw.split(message_ids_separator)]
            except discord.NotFound:
                # Send new messages if any saved IDs have expired
                pass

        if not any(messages):
            # Send messages and save IDs to persistent data for later updates
            for i, message_content in enumerate(message_contents):
                message: discord.Message = await channel.send(
                    content=message_content,
                    allowed_mentions=discord.AllowedMentions.none())
                messages.append(message)
            Commands.bot.db.set_rules_message_ids(
                guild_id=ctx.guild.id,
                message_ids=str.join(message_ids_separator, [str(message.id) for message in messages]))
            # Add messages to channel pins in bottom-to-top order
            reason: str = strings.get("info_reason").format(
                ctx.author.name,
                ctx.author.discriminator,
                ctx.author.id)
            for message in reversed(messages):
                await message.pin(reason=reason)
        elif len(messages) == len(message_contents):
            # Update existing messages from saved IDs in persistent data
            for i, message_content in enumerate(message_contents):
                if messages[i].content != message_content:
                    await messages[i].edit(content=message_content)
        else:
            # Require that messages or message contents are reviewed if a mismatch is found
            msg: str = strings.get("error_edit_messages").format(
                len(messages),
                len(message_contents))
            await ctx.reply(content=msg)
            raise Exception(msg)

        return messages

    async def _get_bulletin_embed(self, guild: discord.Guild) -> discord.Embed:
        channel: discord.TextChannel = guild.get_channel(config.CHANNEL_TEXT)
        emoji_jukebox: discord.Emoji = utils.get(Commands.bot.emojis, name=strings.get("emoji_id_jukebox"))
        role_listen: discord.Role = guild.get_role(config.ROLE_LISTEN)
        role_default: discord.Role = guild.get_role(config.ROLE_DEFAULT)
        embed: discord.Embed = discord.Embed(
            title=strings.get("bulletin_title").format(strings.emoji_play),
            description=strings.get("bulletin_text").format(
                strings.emoji_connection,
                emoji_jukebox,
                channel.mention,
                role_listen.mention,
                role_default.mention),
            colour=get_embed_colour(guild),
            url="https://discord.com/channels/392995143428341762/1021393197978619924"
        )
        embed.set_thumbnail(url=emoji_jukebox.url)
        return embed


# Utility functions


def parse_query(query: any) -> any:
    """
    Fixes up a given search query.
    """
    current: JukeboxItem = jukebox.current_track()
    remove_chars: str = "<>"

    if query:
        # Strip chars to be removed from query
        query = "".join([c for c in query.strip() if c not in remove_chars])

    if query and query.isdigit():
        # Treat digit queries as a queue index, assuming they're starting from 1
        index: int = int(query)
        if index < 1 or index > jukebox.num_tracks():
            raise commands.errors.BadArgument(Commands.ERROR_BAD_PARAMS.format(query))
        query = jukebox.get_item_by_index(index=index - 1).title

    if not query and current:
        # Default to the current track name
        query = current.title

    return query


def mention_to_id(mention: [str, int]) -> int:
    """
    Strips mention formatting from a Discord ID.
    :param mention: Discord ID or mention string.
    :return: Discord ID as digits only.
    """
    return int(re.sub(r"\D", "", mention))

def query_channel(guild: discord.Guild, query: str) -> Optional[discord.abc.GuildChannel]:
    """
    Converts a Discord channel ID or mention to a channel instance, if a visible matching channel exists.
    :param guild:
    :param query: Discord channel ID or mention.
    :return: Channel instance, if found.
    """
    return guild.get_channel_or_thread(mention_to_id(query))


async def get_guild_message(guild: discord.Guild, message_id: int) -> discord.Message:
    """
    Source: Governor by StardewValleyDiscord.

    Returns a message in a guild by querying individual channels.
    :param guild: Guild with channels to search in.
    :param message_id: Discord message ID to search for.
    :return: Message instance if found.
    """
    for channel in guild.channels:
        try:
            if isinstance(channel, discord.TextChannel):
                message = await channel.fetch_message(int(message_id))
                return message
        except discord.Forbidden as e:
            # Ignore channels we're unable to search
            if e.code == 50001:
                pass
        except discord.NotFound as e:
            # Ignore channels that don't contain a matching message
            if e.code == 10008:
                pass


def get_embed_colour(guild: discord.Guild) -> discord.Colour:
    # return guild.get_role(config.ROLE_JUKEBOX).colour
    return guild.get_role(config.ROLE_JUKEBOX).colour


def get_current_track_embed(guild: discord.Guild, show_tracking: bool, description: Optional[str] = None, previous_track: JukeboxItem = None) -> discord.Embed:
    """
    Generates an embed preview for the currently-playing track, or for an empty queue if no track is found.
    :param guild: Discord server to use for role checks.
    :param show_tracking: Whether to show track progress bar.
    :param description: Description to use in place of generic text.
    :param previous_track: Track to use for just-played info text.
    """
    embed: discord.Embed
    current: JukeboxItem = jukebox.current_track()
    emoji: discord.Emoji = utils.get(jukebox.bot.emojis, name=strings.get("emoji_id_vinyl"))
    description_played: str = strings.get("jukebox_played").format(
        previous_track.title,
        format_duration(sec=previous_track.duration)) \
        if previous_track else None
    thumbnail_url: str = None
    image_url: str = None
    if not current:
        # Show embed for empty queue
        embed = get_empty_queue_embed(guild=guild)
        if description_played:
            embed.description = description_played
    else:
        # Show info about the currently-playing track
        title: str = strings.get("jukebox_title").format(
            strings.get("status_playing").format(current.title, strings.emoji_play)
            if jukebox.voice_client and jukebox.voice_client.is_playing()
            else strings.get("status_paused").format(current.title, strings.emoji_pause))

        if description_played:
            # previous track info
            description = f"{description}\n{description_played}" if description else description_played

        if show_tracking and current.audio:
            # track progress bar
            tracking_str: list = ["▬"] * min(10, max(6, len(current.title) - 6))
            tracking_str[floor(len(tracking_str) * current.audio.ratio())] = \
                strings.emoji_blue_circle if random.randint(0, 200) > 0 \
                else str(utils.get(jukebox.bot.emojis, name=strings.get("emoji_id_nukebox")))
            description = strings.get("jukebox_current_track_progress").format(
                "".join(tracking_str),
                format_duration(sec=current.audio.progress()),
                format_duration(sec=current.audio.duration()),
                format_duration(sec=current.audio.duration() - current.audio.progress()),
                current.added_by.mention) + (("\n" + description) if description else "")
            image_url = current.thumbnail
        else:
            # added-by user
            added_by_str: str = strings.get("jukebox_current_added_by").format(
                current.added_by.mention,
                format_duration(sec=current.duration))
            if description and description != added_by_str:
                description = f"{added_by_str}\n\n{description}"

        # embed icon
        thumbnail_url = emoji.url if show_tracking else current.thumbnail

        # queue summary
        embed = discord.Embed(
            title=title,
            description=description,
            colour=get_embed_colour(guild),
            url=current.url if current else None)
        embed.set_thumbnail(url=thumbnail_url)
        if image_url:
            embed.set_image(url=image_url)
    return embed


def get_empty_queue_embed(guild: discord.Guild, description: Optional[str] = None) -> discord.Embed:
    """
    Generates an embed preview for an empty queue.
    :param guild: Discord server to use for role checks.
    :param description: Description to use in place of generic text.
    """
    emoji: discord.Emoji = utils.get(jukebox.bot.emojis, name=strings.get("emoji_id_jukebox"))
    embed: discord.Embed = discord.Embed(
        title=strings.get("jukebox_empty_title"),
        description=description if description else strings.get("jukebox_empty_description"),
        colour=get_embed_colour(guild))
    embed.set_thumbnail(url=emoji.url)
    return embed


def get_empty_queue_msg():
    """
    Generates a preview message for an empty queue.
    """
    emoji: discord.Emoji = utils.get(jukebox.bot.emojis, name=strings.get("emoji_id_vinyl"))
    msg = strings.get("jukebox_empty").format(emoji)
    return msg


def get_lyrics_embed(guild: discord.Guild, song: Song) -> discord.Embed:
    heading: str = song.artist
    title: str = song.title
    text: str = song.lyrics
    url: str = song.url

    # Crop useless artefacts out of raw text
    text = re.sub(r"You might also like|\d*Embed", "", text.split("Lyrics", 1)[1])

    # Crop text to fit character limit
    limit_chars: int = config.LYRICS_CHARACTER_LIMIT
    limit_lines: int = config.LYRICS_LINE_LIMIT
    text_limited: str = "\n".join(text.split("\n", limit_lines))[:limit_chars].strip()
    text_after_limit: List[str] = text[len(text_limited):].split("\n")

    # Vanity text for lines remaining
    text = text_limited + "…" + strings.get("jukebox_lyrics_more").format(len(text_after_limit)) \
        if any(line for line in text_after_limit if line.strip()) \
        else text_limited

    # Italicise context tags
    text = re.sub(pattern=r"\[.+\]", repl=lambda match: f"*{match.group()}*", string=text)

    # Create embed
    emoji: discord.Emoji = utils.get(Commands.bot.emojis, name=strings.get("emoji_id_vinyl"))
    embed: discord.Embed = discord.Embed(
        title=title,
        description=text,
        url=url,
        colour=get_embed_colour(guild))
    embed \
        .set_author(name=heading) \
        .set_footer(
            text=strings.get("jukebox_lyrics_credit"),
            icon_url="https://assets.genius.com/images/apple-touch-icon.png") \
        .set_thumbnail(url=emoji.url)

    return embed

async def ensure_voice() -> None:
    """
    Attempts to join the configured voice channel.
    """
    voice_channel: discord.VoiceChannel = jukebox.bot.get_channel(config.CHANNEL_VOICE)
    if not jukebox.voice_client \
            or not isinstance(jukebox.voice_client, discord.VoiceClient) \
            or not jukebox.voice_client.is_connected() \
            or not jukebox.voice_client.channel \
            or not jukebox.voice_client.channel.id == voice_channel.id:
        # Ensure that the bot has a voice connection
        try:
            if jukebox.voice_client:
                await jukebox.voice_client.disconnect(force=True)
        finally:
            try:
                jukebox.voice_client = await voice_channel.connect(
                    timeout=config.VOICE_TIMEOUT,
                    reconnect=config.VOICE_RECONNECT)
            except ClientException as e:
                # Ignore exceptions raised by concurrent voice connection attempts
                if str(e) == 'Already connected to a voice channel.':
                    return
    if not jukebox.voice_client:
        raise Exception(strings.get("error_voice_not_found"))


def bytes_to_mib(b: int) -> float:
    """
    Conversion of bytes to mebibytes.
    """
    return b / 1048576


def format_duration(sec: int, is_playlist: bool = False) -> str:
    """
    Formats a duration in seconds for playlists and playlist items.
    """
    return datetime.utcfromtimestamp(sec) \
        .strftime(strings.get("datetime_format_playlist")
                  if is_playlist
                  else strings.get("datetime_format_track"))

def format_month() -> int:
    """
    Converts a Year/Month pair into a single unique value to store in the database
    """
    today = date.today()
    year = today.year
    month = today.month - 1
    return year * 12 + month

def format_user_playtime(sec: int) -> str:
    """
    Formats a duration in seconds for user duration listened.
    """
    mins: float = sec / 60
    return strings.get(
        "duration_format_user_short"
        if mins < 60
        else "duration_format_user_long").format(
        int(mins % 60),
        int(mins / 60)
    )


def get_genius() -> Genius:
    genius: Genius = Genius(config.TOKEN_LYRICS)
    genius.timeout = config.LYRICS_SEARCH_TIMEOUT
    genius.verbose = config.LYRICS_VERBOSE
    return genius


# Discord.py boilerplate


async def setup(bot: commands.Bot) -> None:
    cog: Commands = Commands()
    Commands.bot = cog.bot = bot
    await bot.add_cog(cog)
    bot.add_listener(Vote.on_reaction_add)
    bot.add_listener(Commands.on_voice_state_update)
    jukebox.on_track_start_func = cog.before_play
    jukebox.on_track_end_func = cog.after_play
    bot.reload_strings()
    reload(strings)
    reload(jukebox_checks)
