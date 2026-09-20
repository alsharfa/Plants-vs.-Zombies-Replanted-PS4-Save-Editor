#!/usr/bin/env python3
"""
Plants vs. Zombies: Replanted - PS4 CUSA55613 Save Editor
Profile format: version 8 (0.pb.dat), raw DEFLATE compressed.

This editor intentionally edits only fields that were mapped from the game's
IL2CPP metadata and preserves all other bytes exactly.
"""

from __future__ import annotations

import os
import shutil
import struct
import time
import zlib
from dataclasses import dataclass
from pathlib import Path

APP_TITLE = "Plants vs. Zombies: Replanted - CUSA55613 Save Editor"
MAGIC = 0x13512241
SUPPORTED_VERSION = 8
MAX_I32 = 2_147_483_647

ACHIEVEMENTS = [
    "Home Security", "Gold Sunflower", "Better Off Dead", "China Shop",
    "Spudow", "Explodonator", "Morticulturalist", "Don't Pea in the Pool",
    "Roll Some Heads", "Grounded", "Zombologist", "Penny Pincher",
    "Sunny Days", "Popcorn Party", "Good Morning", "No Fungus Among Us",
    "Beat All Mini-Games", "Immortal", "Towering Wisdom", "Mustache Mode",
    "Hypnotize Dancer", "Final Rest", "Life Well Lived", "Cloud Cover",
    "Pyromaniac", "Alive and Planting", "Wall-not Attack", "Shooting Star",
    "Sol Invictus", "Sproing Sproing", "I Win", "Smashing",
    "Last Mown Standing", "Enlightened", "Second Life", "Life Half Empty",
    "Life Half Full",
]

STORE_ITEMS = [
    "Gatling Pea", "Twin Sunflower", "Gloom-shroom", "Cattail",
    "Winter Melon", "Gold Magnet", "Spikerock", "Cob Cannon", "Imitater",
    "Bonus Lawn Mower", "Potted Marigold 1", "Potted Marigold 2",
    "Potted Marigold 3", "Gold Watering Can", "Fertilizer", "Bug Spray",
    "Phonograph", "Gardening Glove", "Mushroom Garden", "Wheel Barrow",
    "Stinky the Snail", "Packet Upgrade", "Pool Cleaner", "Roof Cleaner",
    "Rake", "Aquarium Garden", "Chocolate", "Tree of Wisdom", "Tree Food",
    "First Aid",
]

SEED_NAMES = [
    "Peashooter", "Sunflower", "Cherry Bomb", "Wall-nut", "Potato Mine",
    "Snow Pea", "Chomper", "Repeater", "Puff-shroom", "Sun-shroom",
    "Fume-shroom", "Grave Buster", "Hypno-shroom", "Scaredy-shroom",
    "Ice-shroom", "Doom-shroom", "Lily Pad", "Squash", "Threepeater",
    "Tangle Kelp", "Jalapeno", "Spikeweed", "Torchwood", "Tall-nut",
    "Sea-shroom", "Plantern", "Cactus", "Blover", "Split Pea", "Starfruit",
    "Pumpkin", "Magnet-shroom", "Cabbage-pult", "Flower Pot", "Kernel-pult",
    "Coffee Bean", "Garlic", "Umbrella Leaf", "Marigold", "Melon-pult",
    "Gatling Pea", "Twin Sunflower", "Gloom-shroom", "Cattail",
    "Winter Melon", "Gold Magnet", "Spikerock", "Cob Cannon", "Imitater",
    "Explode-o-nut", "Giant Wall-nut", "Sprout", "Leftpeater",
]

# Challenge record index = GameMode - SurvivalNormalStage1.
CHALLENGE_NAMES = []
for difficulty, count in (("Survival Normal", 5), ("Survival Hard", 5), ("Survival Endless", 5)):
    CHALLENGE_NAMES += [f"{difficulty} Stage {i}" for i in range(1, count + 1)]
CHALLENGE_NAMES += [
    "War and Peas", "Wall-nut Bowling", "Slot Machine", "Raining Seeds",
    "Beghouled", "Invisighoul", "Seeing Stars", "Zombiquarium",
    "Beghouled Twist", "Little Trouble", "Portal Combat", "Column Like You See 'Em",
    "Bobsled Bonanza", "Speed", "Whack a Zombie", "Last Stand",
    "War and Peas 2", "Wall-nut Bowling 2", "Pogo Party", "Final Boss",
    "Art Challenge 1", "Sunny Day", "Resodded", "Big Time", "Art Challenge 2",
    "Air Raid", "Ice", "Zen Garden", "High Gravity", "Grave Danger", "Shovel",
    "Stormy Night", "Bungee Blitz", "Squirrel", "Tree of Wisdom",
]
CHALLENGE_NAMES += [f"Vasebreaker {i}" for i in range(1, 10)] + ["Vasebreaker Endless"]
CHALLENGE_NAMES += [f"I, Zombie {i}" for i in range(1, 10)] + ["I, Zombie Endless"]
CHALLENGE_NAMES += ["Upsell", "Intro", "Bonus China", "Co-op", "Versus"]
while len(CHALLENGE_NAMES) < 100:
    CHALLENGE_NAMES.append(f"Record {len(CHALLENGE_NAMES)}")

BOOL_FIELDS = [
    ("shownZombatarDesktopMessage", "Shown Zombatar desktop message"),
    ("acceptedZombatarULA", "Accepted Zombatar ULA"),
    ("ripModeActive", "R.I.P. mode active"),
    ("ripUsedLawnMower", "R.I.P. used lawn mower"),
    ("ripHasSeenHelp", "R.I.P. help seen"),
    ("preOrderContentActive", "Pre-order content active"),
    ("platformContentActive", "Platform content active"),
    ("retroContentActive", "Retro content active"),
    ("danceModeActive", "Dance mode active"),
    ("mustacheModeActive", "Mustache mode active"),
    ("futureModeActive", "Future mode active"),
    ("trickedOutModeActive", "Tricked-out mode active"),
    ("daisesModeActive", "Daisies mode active"),
    ("pinataModeActive", "Pinata mode active"),
    ("sukhbirModeActive", "Sukhbir mode active"),
    ("hasSeenMultiplayerUnlocked", "Multiplayer unlock message seen"),
    ("hasSeenLimboUnlocked", "Limbo unlock message seen"),
    ("hasSeenRIPUnlocked", "R.I.P. unlock message seen"),
    ("hasSeenCloudyDayUnlocked", "Cloudy Day unlock message seen"),
    ("harderEnabled", "Harder mode enabled"),
    ("zenGardenTutorialCompleted", "Zen Garden tutorial completed"),
]

SCALAR_FIELDS = [
    "level", "ripLevel", "coins", "finishedAdventure", "finishedRipAdventure",
    "playTimeActive", "playTimeInactive", "hasUsedCheatKeys", "hasWokenStinky",
    "didntPurchasePacketUpgrade", "lastStinkyChocolateTime", "stinkyPosX", "stinkyPosY",
    "hasUnlockedMinigames", "hasUnlockedPuzzleMode", "hasNewMiniGame",
    "hasNewVasebreaker", "hasNewIZombie", "hasNewSurvival",
    "hasUnlockedSurvivalMode", "needsMessageOnGameSelector", "needsMagicTacoReward",
    "hasSeenStinky", "hasSeenUpsell", "numPottedPlants",
]


class FormatError(Exception):
    pass


def _i32(buf: bytes | bytearray, off: int) -> int:
    return struct.unpack_from("<i", buf, off)[0]


def _i64(buf: bytes | bytearray, off: int) -> int:
    return struct.unpack_from("<q", buf, off)[0]


def _u64(buf: bytes | bytearray, off: int) -> int:
    return struct.unpack_from("<Q", buf, off)[0]


@dataclass
class ArrayRef:
    count_offset: int
    data_offset: int
    count: int
    elem_size: int


class ProfileV8:
    def __init__(self, compressed: bytes):
        self.compressed = compressed
        try:
            dec = zlib.decompressobj(wbits=-15)
            raw = dec.decompress(compressed) + dec.flush()
            if dec.unused_data or dec.unconsumed_tail or not dec.eof:
                raise FormatError("Compressed profile contains trailing or incomplete DEFLATE data")
            self.raw = bytearray(raw)
        except zlib.error as exc:
            raise FormatError(f"Not a supported raw-DEFLATE 0.pb.dat file: {exc}") from exc

        self.scalar_offsets: dict[str, tuple[int, str]] = {}
        self.bool_offsets: dict[str, int] = {}
        self.arrays: dict[str, ArrayRef] = {}
        self._parse()

    def _need(self, off: int, size: int):
        if off < 0 or off + size > len(self.raw):
            raise FormatError("Unexpected end of profile data")

    def _read_string(self, off: int):
        self._need(off, 4)
        n = _i32(self.raw, off)
        if n < 0 or n > 4096:
            raise FormatError(f"Invalid string length {n} at 0x{off:X}")
        self._need(off + 4, n)
        try:
            s = bytes(self.raw[off + 4:off + 4 + n]).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FormatError("Invalid UTF-8 profile string") from exc
        return s, off + 4 + n

    def _read_bool_array(self, off: int, name: str, expected: int):
        self._need(off, 4)
        n = _i32(self.raw, off)
        if n != expected:
            raise FormatError(f"{name}: expected {expected} entries, found {n}")
        self._need(off + 4, n)
        self.arrays[name] = ArrayRef(off, off + 4, n, 1)
        return off + 4 + n

    def _read_i32_array(self, off: int, name: str, expected: int):
        self._need(off, 4)
        n = _i32(self.raw, off)
        if n != expected:
            raise FormatError(f"{name}: expected {expected} entries, found {n}")
        self._need(off + 4, n * 4)
        self.arrays[name] = ArrayRef(off, off + 4, n, 4)
        return off + 4 + n * 4

    def _parse(self):
        if len(self.raw) < 16:
            raise FormatError("Profile is too small")
        magic, version, data_size, total_size = struct.unpack_from("<IIII", self.raw, 0)
        if magic != MAGIC:
            raise FormatError(f"Unexpected profile magic 0x{magic:08X}")
        if version != SUPPORTED_VERSION:
            raise FormatError(f"Unsupported profile version {version}; expected {SUPPORTED_VERSION}")
        if total_size != len(self.raw) or data_size != len(self.raw) - 16:
            raise FormatError(
                f"Header size mismatch (data={data_size}, total={total_size}, actual={len(self.raw)})"
            )
        self.version = version

        o = 16
        self.name, o = self._read_string(o)
        self.guid, o = self._read_string(o)

        self._need(o, 12)
        self.use_seq_offset = o
        self.use_seq = _u64(self.raw, o); o += 8
        self.id_offset = o
        self.profile_id = _i32(self.raw, o); o += 4

        def scalar(name: str, fmt: str = "i"):
            nonlocal o
            size = 8 if fmt == "q" else 4
            self._need(o, size)
            self.scalar_offsets[name] = (o, fmt)
            o += size

        for name in ["level", "ripLevel", "coins", "finishedAdventure", "finishedRipAdventure",
                     "playTimeActive", "playTimeInactive", "hasUsedCheatKeys", "hasWokenStinky",
                     "didntPurchasePacketUpgrade"]:
            scalar(name)
        scalar("lastStinkyChocolateTime", "q")
        for name in ["stinkyPosX", "stinkyPosY", "hasUnlockedMinigames", "hasUnlockedPuzzleMode",
                     "hasNewMiniGame", "hasNewVasebreaker", "hasNewIZombie", "hasNewSurvival",
                     "hasUnlockedSurvivalMode", "needsMessageOnGameSelector", "needsMagicTacoReward",
                     "hasSeenStinky", "hasSeenUpsell", "numPottedPlants"]:
            scalar(name)

        for name, _label in BOOL_FIELDS:
            self._need(o, 1)
            self.bool_offsets[name] = o
            o += 1

        o = self._read_bool_array(o, "earnedAchievements", 37)
        o = self._read_bool_array(o, "shownAchievements", 37)
        o = self._read_i32_array(o, "challengeRecords", 100)
        o = self._read_i32_array(o, "purchases", 80)

        self.stinky_wakeup_offset = o
        self._need(o, 8)
        o += 8

        o = self._read_bool_array(o, "miniGamesCompleted", 20)
        o = self._read_bool_array(o, "cloudyDayLevelsCompleted", 13)
        o = self._read_bool_array(o, "coopLevelsCompleted", 15)
        o = self._read_bool_array(o, "collectedZenGardenPlants", 40)

        self._need(o, 4)
        pcount = _i32(self.raw, o)
        if pcount != 200:
            raise FormatError(f"Expected 200 potted-plant slots, found {pcount}")
        self.potted_count_offset = o
        self.potted_data_offset = o + 4
        self._need(self.potted_data_offset, 200 * 80)
        o = self.potted_data_offset + 200 * 80

        o = self._read_i32_array(o, "coopChallengeRecords", 15)
        o = self._read_i32_array(o, "cloudyDayRecords", 13)

        if o != len(self.raw):
            raise FormatError(f"Unexpected {len(self.raw)-o} trailing bytes at 0x{o:X}")

    def get_scalar(self, name: str) -> int:
        off, fmt = self.scalar_offsets[name]
        return _i64(self.raw, off) if fmt == "q" else _i32(self.raw, off)

    def set_scalar(self, name: str, value: int):
        off, fmt = self.scalar_offsets[name]
        if fmt == "q":
            value = int(value)
            if not (-9_223_372_036_854_775_808 <= value <= 9_223_372_036_854_775_807):
                raise ValueError(f"{name} must fit a signed 64-bit integer")
            struct.pack_into("<q", self.raw, off, value)
        else:
            value = int(value)
            if not (-2_147_483_648 <= value <= MAX_I32):
                raise ValueError(f"{name} must fit a signed 32-bit integer")
            struct.pack_into("<i", self.raw, off, value)

    def get_bool(self, name: str) -> bool:
        return bool(self.raw[self.bool_offsets[name]])

    def set_bool(self, name: str, value: bool):
        self.raw[self.bool_offsets[name]] = 1 if value else 0

    def get_array(self, name: str):
        ref = self.arrays[name]
        if ref.elem_size == 1:
            return [int(x) for x in self.raw[ref.data_offset:ref.data_offset + ref.count]]
        return list(struct.unpack_from("<" + "i" * ref.count, self.raw, ref.data_offset))

    def set_array_item(self, name: str, index: int, value: int):
        ref = self.arrays[name]
        if not 0 <= index < ref.count:
            raise IndexError(index)
        if ref.elem_size == 1:
            self.raw[ref.data_offset + index] = 1 if value else 0
        else:
            value = int(value)
            if not (-2_147_483_648 <= value <= MAX_I32):
                raise ValueError("Array value must fit a signed 32-bit integer")
            struct.pack_into("<i", self.raw, ref.data_offset + index * 4, value)

    def set_array_all(self, name: str, value: int):
        ref = self.arrays[name]
        for i in range(ref.count):
            self.set_array_item(name, i, value)

    @property
    def stinky_wakeup_time(self) -> int:
        return _i64(self.raw, self.stinky_wakeup_offset)

    @stinky_wakeup_time.setter
    def stinky_wakeup_time(self, value: int):
        value = int(value)
        if not (-9_223_372_036_854_775_808 <= value <= 9_223_372_036_854_775_807):
            raise ValueError("stinky_wakeup_time must fit a signed 64-bit integer")
        struct.pack_into("<q", self.raw, self.stinky_wakeup_offset, value)

    def potted_plant(self, index: int):
        if not 0 <= index < 200:
            raise IndexError(index)
        off = self.potted_data_offset + index * 80
        values = struct.unpack_from("<5iq5iqqqq", self.raw, off)
        keys = [
            "seedType", "whichZenGarden", "x", "y", "facing", "lastWateredTime",
            "drawVariation", "plantAge", "timesFed", "feedingsPerGrow", "plantNeed",
            "lastNeedFulfilledTime", "lastFertilizedTime", "lastChocolateTime", "futureAttribute",
        ]
        return dict(zip(keys, values))

    def set_potted_field(self, index: int, field: str, value: int):
        if not 0 <= index < 200:
            raise IndexError(index)
        layout = {
            "seedType": (0, "i"), "whichZenGarden": (4, "i"), "x": (8, "i"),
            "y": (12, "i"), "facing": (16, "i"), "lastWateredTime": (20, "q"),
            "drawVariation": (28, "i"), "plantAge": (32, "i"), "timesFed": (36, "i"),
            "feedingsPerGrow": (40, "i"), "plantNeed": (44, "i"),
            "lastNeedFulfilledTime": (48, "q"), "lastFertilizedTime": (56, "q"),
            "lastChocolateTime": (64, "q"), "futureAttribute": (72, "q"),
        }
        if field not in layout:
            raise KeyError(field)
        rel, fmt = layout[field]
        value = int(value)
        if fmt == "i" and not (-2_147_483_648 <= value <= MAX_I32):
            raise ValueError(f"{field} must fit a signed 32-bit integer")
        if fmt == "q" and not (-9_223_372_036_854_775_808 <= value <= 9_223_372_036_854_775_807):
            raise ValueError(f"{field} must fit a signed 64-bit integer")
        off = self.potted_data_offset + index * 80 + rel
        struct.pack_into("<" + fmt, self.raw, off, value)

    def compressed_bytes(self) -> bytes:
        # No checksum trailer is present in this format. Rebuild header sizes anyway.
        struct.pack_into("<I", self.raw, 8, len(self.raw) - 16)
        struct.pack_into("<I", self.raw, 12, len(self.raw))
        c = zlib.compressobj(level=9, method=zlib.DEFLATED, wbits=-15)
        out = c.compress(bytes(self.raw)) + c.flush()
        # Verify both the DEFLATE stream and the complete profile structure.
        check = ProfileV8(out)
        if bytes(check.raw) != bytes(self.raw):
            raise RuntimeError("Internal recompression verification failed")
        return out
