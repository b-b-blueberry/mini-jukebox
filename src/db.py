# Mini-Jukebox
# db.py
# Written by blueberry et al., 2022
# https://github.com/StardewValleyDiscord/mini-jukebox

"""
Contents:
    Data models
        DBUser
    Constant values
    Utility methods
    Data queries
"""

import sqlite3
from sqlite3 import Connection
from typing import Tuple, Optional, List

from config import DATABASE_PATH


# Data models


class DBUser:
    user_id: int
    tracks_added: int
    tracks_listened: int
    duration_listened: int

    def __init__(
            self,
            user_id: int,
            tracks_added: int,
            tracks_listened: int,
            duration_listened: int,
            recent_month: int,
            monthly_listened: int,
    ):
        self.user_id = user_id
        self.tracks_added = tracks_added
        self.tracks_listened = tracks_listened
        self.duration_listened = duration_listened
        self.recent_month = recent_month
        self.montly_listened = monthly_listened


# Constant values


TABLE_USERS: str = "USERS"
KEY_USER_ID: str = "ID"
KEY_TRACKS_ADDED: str = "TRACKS_ADDED"
KEY_TRACKS_LISTENED: str = "TRACKS_LISTENED"
KEY_DURATION_LISTENED: str = "DURATION_LISTENED"
KEY_RECENT_MONTH: str = "RECENT_MONTH"
KEY_MONTH_LISTENED: str = "MONTHLY_LISTENED"

TABLE_GUILDS: str = "GUILDS"
KEY_GUILD_ID: str = "ID"
KEY_RULES_MESSAGE_IDS: str = "RULES_MESSAGE_IDS"


# Utility methods


def setup():
    """
    Generates database with required tables.
    """
    db: Connection = sqlite3.connect(DATABASE_PATH)
    # Guilds table
    db.execute(
        "CREATE TABLE IF NOT EXISTS {0} ({1} INT PRIMARY KEY, {2} INT)"
        .format(
            TABLE_GUILDS,
            KEY_GUILD_ID,
            KEY_RULES_MESSAGE_IDS
        ))
    # Users table
    db.execute(
        "CREATE TABLE IF NOT EXISTS {0} ({1} INT PRIMARY KEY, {2} INT, {3} INT, {4} INT, {5} INT, {6} INT)"
        .format(
            TABLE_USERS,
            KEY_USER_ID,
            KEY_TRACKS_ADDED,
            KEY_TRACKS_LISTENED,
            KEY_DURATION_LISTENED,
            KEY_RECENT_MONTH,
            KEY_MONTH_LISTENED
        ))
    db.commit()
    db.close()

def _db_read(_query: [tuple, str]) -> any:
    """
    Helper function to perform database reads.
    """
    sqlconn = sqlite3.connect(DATABASE_PATH)
    results: any
    results = sqlconn.execute(*_query).fetchall()
    sqlconn.close()
    return results

def _db_write(_query: [Tuple[str, list], str]):
    """
    Helper function to perform database writes.
    """
    sqlconn = sqlite3.connect(DATABASE_PATH)
    sqlconn.execute(*_query) if isinstance(_query, tuple) else sqlconn.execute(_query)
    sqlconn.commit()
    sqlconn.close()


# Guild queries


def get_rules_message_ids(guild_id: int) -> Optional[str]:
    """
    Gets the rules message IDs for the current guild as space-separated values in order.
    """
    query: tuple = (
        "SELECT {0} FROM {1} WHERE {2}=?"
        .format(
            KEY_RULES_MESSAGE_IDS,
            TABLE_GUILDS,
            KEY_GUILD_ID
        ), [
            guild_id
        ])
    result = _db_read(query)
    return result[0][0] if result and result[0] else None

def set_rules_message_ids(guild_id: int, message_ids: str) -> None:
    """
    Updates a guild's rules message IDs.
    """
    query: tuple = (
        "REPLACE INTO {0} ({1}, {2}) VALUES (?, ?)"
        .format(
            TABLE_GUILDS,
            KEY_GUILD_ID,
            KEY_RULES_MESSAGE_IDS
        ), [
            guild_id,
            message_ids
        ])
    _db_write(query)


# User queries


def _entry_to_user(entry: list) -> DBUser:
    """
    Creates a DBUser instance from a database entry
    """
    return DBUser(
        user_id=entry[0],
        tracks_added=entry[1],
        tracks_listened=entry[2],
        duration_listened=entry[3],
        recent_month=entry[4],
        monthly_listened=entry[5],
    )

def get_user(user_id: int) -> DBUser:
    """
    Gets the database entry for a given user.
    """
    query: tuple = (
        "SELECT * FROM {0} WHERE {1} = ?"
        .format(
            TABLE_USERS,
            KEY_USER_ID
        ), [
            user_id
        ])
    entry: list = _db_read(query)
    return _entry_to_user(entry[0] if entry and entry[0] else [user_id, 0, 0, 0, 0, 0])

def update_user(entry: DBUser) -> None:
    """
    Updates a user's database entry. Negative values will be ignored.
    """
    query: tuple = (
        "REPLACE INTO {0} ({1}, {2}, {3}, {4}, {5}, {6}) VALUES (?, ?, ?, ?, ?, ?)"
        .format(
            TABLE_USERS,
            KEY_USER_ID,
            KEY_TRACKS_ADDED,
            KEY_TRACKS_LISTENED,
            KEY_DURATION_LISTENED,
            KEY_RECENT_MONTH,
            KEY_MONTH_LISTENED,
        ), [
            entry.user_id,
            entry.tracks_added,
            entry.tracks_listened,
            entry.duration_listened,
            entry.recent_month,
            entry.montly_listened,
        ])
    _db_write(query)

def get_top_users(num: int) -> List[DBUser]:
    query: tuple = (
        "SELECT * FROM {0} ORDER BY {1} DESC LIMIT {2}"
        .format(
            TABLE_USERS,
            KEY_DURATION_LISTENED,
            num
        ), [
        ])
    entries: list = _db_read(query)
    users: list = [_entry_to_user(entry) for entry in entries]
    return users

def get_num_users() -> int:
    query: tuple = (
        "SELECT COUNT({0}) FROM {1}"
        .format(
            KEY_USER_ID,
            TABLE_USERS
        ), [
        ])
    result: list = _db_read(query)
    return result[0][0] if result and result[0] else 0
