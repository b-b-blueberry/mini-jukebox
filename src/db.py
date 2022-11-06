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
from typing import Tuple

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
            duration_listened: int
    ):
        self.user_id = user_id
        self.tracks_added = tracks_added
        self.tracks_listened = tracks_listened
        self.duration_listened = duration_listened


# Constant values


TABLE_USERS: str = "USERS"
KEY_USER_ID: str = "ID"
KEY_TRACKS_ADDED: str = "TRACKS_ADDED"
KEY_TRACKS_LISTENED: str = "TRACKS_LISTENED"
KEY_DURATION_LISTENED: str = "DURATION_LISTENED"


# Utility methods


def setup():
    """
    Generates database with required tables.
    """
    db: Connection = sqlite3.connect(DATABASE_PATH)
    db.execute(
        "CREATE TABLE IF NOT EXISTS {0} ({1} INT PRIMARY KEY, {2} INT, {3} INT, {4} INT)"
        .format(
            TABLE_USERS,
            KEY_USER_ID,
            KEY_TRACKS_ADDED,
            KEY_TRACKS_LISTENED,
            KEY_DURATION_LISTENED
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


# Data queries


def get(user_id: int) -> DBUser:
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

    if not entry or not entry[0]:
        return DBUser(
            user_id=user_id,
            tracks_added=0,
            tracks_listened=0,
            duration_listened=0
        )
    else:
        return DBUser(
            user_id=entry[0][0],
            tracks_added=entry[0][1],
            tracks_listened=entry[0][2],
            duration_listened=entry[0][3]
        )

def update(entry: DBUser) -> None:
    """
    Updates a user's database entry. Negative values will be ignored.
    """
    query: tuple = (
        "REPLACE INTO {0} ({1}, {2}, {3}, {4}) VALUES (?, ?, ?, ?)"
        .format(
            TABLE_USERS,
            KEY_USER_ID,
            KEY_TRACKS_ADDED,
            KEY_TRACKS_LISTENED,
            KEY_DURATION_LISTENED,
        ), [
            entry.user_id,
            entry.tracks_added,
            entry.tracks_listened,
            entry.duration_listened
        ])
    _db_write(query)
