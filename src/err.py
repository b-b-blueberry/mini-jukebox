# Mini-Jukebox
# err.py
# Written by blueberry et al., 2022
# https://github.com/StardewValleyDiscord/mini-jukebox

import os
import traceback
from datetime import datetime
from io import StringIO
from typing import List

import discord

from src import strings


def log(error: Exception) -> None:
    print("[{0}]\t{1}".format(
        datetime.now(),
        error))

def format_traceback(error: Exception) -> str:
    curdir: str = os.path.abspath(os.path.curdir)
    tb_lines: List[str] = [
        "".join([
            f"\"{line.split(curdir, 1)[-1]}"
            if line.lstrip().startswith("File") else line
        ]) for line in
        traceback.format_exception(None, error, error.__traceback__)]
    return "\n".join(tb_lines)

def traceback_as_file(error: Exception) -> discord.File:
    s: StringIO = StringIO()
    s.write(format_traceback(error))
    s.seek(0)
    fp = datetime.now().strftime(strings.get("datetime_format_log")) + ".txt"
    return discord.File(s, filename=fp)
