# Mini-Jukebox
# strings.py
# Written by blueberry et al., 2022
# https://github.com/StardewValleyDiscord/mini-jukebox

"""
References:
    http://www.unicode.org/Public/UCD/latest/ucd/NamesList.txt
    https://unicode.org/emoji/charts/full-emoji-list.html
"""

import json


STRINGS_PATH = "./assets/strings.json"
with open(file=STRINGS_PATH, mode="r", encoding="utf8") as strings_file:
    _data = json.load(strings_file)


emoji_mod_keycap = "\u20E3"
emoji_exclamation = "\N{WHITE EXCLAMATION MARK ORNAMENT}"
emoji_question = "\N{WHITE QUESTION MARK ORNAMENT}"
emoji_error = "\N{NEGATIVE SQUARED CROSS MARK}"
emoji_confirm = "\N{WHITE HEAVY CHECK MARK}"
emoji_play = "\N{BLACK RIGHT-POINTING TRIANGLE}"
emoji_pause = "\N{DOUBLE VERTICAL BAR}"
emoji_stop = "\N{BLACK SQUARE FOR STOP}"
emoji_eject = "\N{EJECT SYMBOL}"
emoji_next = "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}"
emoji_refresh = "\N{ANTICLOCKWISE DOWNWARDS AND UPWARDS OPEN CIRCLE ARROWS}"
emoji_repeat = "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS}"
emoji_shuffle = "\N{TWISTED RIGHTWARDS ARROWS}"
emoji_continue = "\N{LEFTWARDS ARROW WITH HOOK}"
emoji_vote_yes = "\N{WHITE HEAVY CHECK MARK}"
emoji_vote_no = "\N{NEGATIVE SQUARED CROSS MARK}"
emoji_connection = "\N{ANTENNA WITH BARS}"
emoji_pin = "\N{PUSHPIN}"
emoji_lock_on = "\N{LOCK}"
emoji_lock_off = "\N{OPEN LOCK}"
emoji_mango = "\N{MANGO}"
emoji_keycap = "\N{LARGE BLUE SQUARE}"
emoji_hash = "\N{NUMBER SIGN}" + emoji_mod_keycap
emoji_star = "\N{ASTERISK}" + emoji_mod_keycap
emoji_digits = [
    "\N{DIGIT ZERO}" + emoji_mod_keycap,
    "\N{DIGIT ONE}" + emoji_mod_keycap,
    "\N{DIGIT TWO}" + emoji_mod_keycap,
    "\N{DIGIT THREE}" + emoji_mod_keycap,
    "\N{DIGIT FOUR}" + emoji_mod_keycap,
    "\N{DIGIT FIVE}" + emoji_mod_keycap,
    "\N{DIGIT SIX}" + emoji_mod_keycap,
    "\N{DIGIT SEVEN}" + emoji_mod_keycap,
    "\N{DIGIT EIGHT}" + emoji_mod_keycap,
    "\N{DIGIT NINE}" + emoji_mod_keycap,
    "\N{KEYCAP TEN}",
    emoji_star
]


def get(__name: str):
    return _data.get(__name)
