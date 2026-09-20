from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
import zlib

MAGIC_BYTES = b"AcQS"
MAX_SUN = 9999
MAX_RUN_STAGE = 9999
SUN_RELATIVE_OFFSET = 257
SUN_P2_RELATIVE_OFFSET = 261

# Replanted's serialized Challenge state contains a 9x6 boolean grid. In every
# supplied CUSA55613 board payload the actual Challenge object is the occurrence
# after the board's early fixed grid data (normally around +0x5C80). The live
# mSurvivalStage / endless-streak value is +98 bytes from that Challenge block.
CHALLENGE_GRID_X = 9
CHALLENGE_GRID_Y = 6
CHALLENGE_STAGE_RELATIVE_OFFSET = 98
CHALLENGE_SEARCH_MIN = 4096

KNOWN_LEVEL_NAMES = {
    95: "Survival Day Endless",
    105: "Vasebreaker Endless",
    115: "I, Zombie Endless",
}


class InGameFormatError(Exception):
    pass


@dataclass(frozen=True)
class InGameRecord:
    header_offset: int
    payload_offset: int
    version: int
    level_id: int
    data_size: int
    total_size: int

    @property
    def end_offset(self) -> int:
        return self.header_offset + self.total_size


class InGameSave:
    """Parser/editor for Replanted .ig.dat raw-DEFLATE containers.

    The supplied CUSA55613 samples use a 20-byte SaveHeader::
        MagicNumber, Version, LevelID, DataSize, TotalSize
    where TotalSize == DataSize + 20.

    Verified mappings used here:
      * P1/P2 mSunMoney: payload +257 / +261
      * Challenge.mSurvivalStage: dynamically located Challenge block +98

    mSurvivalStage is the live endless-puzzle streak for I, Zombie/Vasebreaker.
    For Survival Endless it is the completed survival stage counter. The classic
    board logic uses 20 waves per endless stage and 10 waves per flag, so each
    fully completed survival stage represents two flags before current-wave
    contribution is added.
    """

    def __init__(self, compressed: bytes):
        self.compressed = bytes(compressed)
        try:
            dec = zlib.decompressobj(wbits=-15)
            raw = dec.decompress(self.compressed) + dec.flush()
            if dec.unused_data or dec.unconsumed_tail or not dec.eof:
                raise InGameFormatError("Compressed in-game save contains trailing or incomplete DEFLATE data")
        except zlib.error as exc:
            raise InGameFormatError(f"Not a supported raw-DEFLATE .ig.dat file: {exc}") from exc

        if len(raw) < 32:
            raise InGameFormatError("In-game save is too small")
        if raw[:4] != MAGIC_BYTES:
            raise InGameFormatError("Missing AcQS in-game save signature")

        self.raw = bytearray(raw)
        self.records = self._find_records()
        if not self.records:
            raise InGameFormatError("No populated SaveHeader records were found in this .ig.dat")

        # Cache dynamic challenge-object locations. Not every possible mode is
        # required to contain a Challenge block, so None is allowed.
        self._challenge_offsets: dict[int, int | None] = {
            i: self._find_challenge_block(rec) for i, rec in enumerate(self.records)
        }

    @classmethod
    def from_path(cls, path: str | Path) -> "InGameSave":
        return cls(Path(path).read_bytes())

    def _find_records(self) -> list[InGameRecord]:
        out: list[InGameRecord] = []
        raw = self.raw
        pos = 0
        seen = set()
        while True:
            p = raw.find(MAGIC_BYTES, pos)
            if p < 0:
                break
            pos = p + 1
            if p + 20 > len(raw):
                continue
            version, level_id, data_size, total_size = struct.unpack_from("<iiii", raw, p + 4)
            if not (1 <= version <= 100):
                continue
            if not (0 <= level_id <= 100000):
                continue
            if data_size <= SUN_P2_RELATIVE_OFFSET + 4:
                continue
            if total_size != data_size + 20:
                continue
            if p + total_size > len(raw):
                continue
            # CUSA55613 containers wrap populated records in an AcQS+size pair.
            # Requiring the wrapper prevents payload bytes that happen to equal
            # the magic from being misidentified as a SaveHeader.
            if p < 8 or raw[p - 8:p - 4] != MAGIC_BYTES:
                continue
            wrapped_size = struct.unpack_from("<i", raw, p - 4)[0]
            if wrapped_size != total_size:
                continue
            key = (p, level_id, total_size)
            if key in seen:
                continue
            seen.add(key)
            out.append(InGameRecord(
                header_offset=p,
                payload_offset=p + 20,
                version=version,
                level_id=level_id,
                data_size=data_size,
                total_size=total_size,
            ))
        out.sort(key=lambda r: r.header_offset)
        return out

    def _record(self, index: int) -> InGameRecord:
        if not 0 <= index < len(self.records):
            raise IndexError(index)
        return self.records[index]

    def mode_name(self, index: int) -> str:
        return KNOWN_LEVEL_NAMES.get(self._record(index).level_id, "")

    def _find_challenge_block(self, rec: InGameRecord) -> int | None:
        """Return absolute raw offset of the serialized Challenge block.

        The early board payload also contains a 9x6 grid around +265. To avoid
        confusing it with Challenge.mBeghouledEated, only matches after +4096
        are considered. Across every supplied populated CUSA55613 record there
        is one such later 9x6 boolean grid, at about +23.7 KiB.
        """
        start = rec.payload_offset + CHALLENGE_SEARCH_MIN
        end = rec.payload_offset + rec.data_size
        pat = struct.pack("<ii", CHALLENGE_GRID_X, CHALLENGE_GRID_Y)
        pos = start
        candidates: list[int] = []
        while True:
            p = self.raw.find(pat, pos, end)
            if p < 0:
                break
            pos = p + 1
            bool_start = p + 8
            bool_end = bool_start + CHALLENGE_GRID_X * CHALLENGE_GRID_Y
            stage_end = p + CHALLENGE_STAGE_RELATIVE_OFFSET + 4
            if bool_end > end or stage_end > end:
                continue
            bools = self.raw[bool_start:bool_end]
            if all(v in (0, 1) for v in bools):
                candidates.append(p)

        if not candidates:
            return None
        # Supplied files have exactly one later Challenge-grid signature. If a
        # future save contains more, prefer the earliest later object; this is
        # closest to the verified ~23.7 KiB Challenge location.
        return candidates[0]

    def has_run_stage(self, index: int) -> bool:
        self._record(index)
        return self._challenge_offsets.get(index) is not None

    def get_run_stage(self, index: int) -> int:
        self._record(index)
        off = self._challenge_offsets.get(index)
        if off is None:
            raise InGameFormatError("No verified Challenge streak/stage block was found for this slot")
        return struct.unpack_from("<i", self.raw, off + CHALLENGE_STAGE_RELATIVE_OFFSET)[0]

    def set_run_stage(self, index: int, value: int):
        value = int(value)
        if not 0 <= value <= MAX_RUN_STAGE:
            raise ValueError(f"Streak/stage must be between 0 and {MAX_RUN_STAGE}")
        self._record(index)
        off = self._challenge_offsets.get(index)
        if off is None:
            raise InGameFormatError("No verified Challenge streak/stage block was found for this slot")
        struct.pack_into("<i", self.raw, off + CHALLENGE_STAGE_RELATIVE_OFFSET, value)

    def run_stage_label(self, index: int) -> str:
        level = self._record(index).level_id
        if level in (105, 115):
            return "Current Streak"
        if level == 95:
            return "Survival Stage"
        return "Challenge Stage"

    def estimated_survival_flags(self, index: int) -> int | None:
        """Return completed flags represented by full stages only.

        Current-wave progress can add 0-1 additional flags in-game. For the
        verified Survival Day Endless slot (Level ID 95), each full stage is
        two flags (20 waves / 10 waves per flag).
        """
        if self._record(index).level_id != 95 or not self.has_run_stage(index):
            return None
        return self.get_run_stage(index) * 2

    def get_sun(self, index: int, player: int = 1) -> int:
        rec = self._record(index)
        rel = SUN_RELATIVE_OFFSET if player == 1 else SUN_P2_RELATIVE_OFFSET
        if player not in (1, 2):
            raise ValueError("player must be 1 or 2")
        return struct.unpack_from("<i", self.raw, rec.payload_offset + rel)[0]

    def set_sun(self, index: int, value: int, player: int = 1):
        value = int(value)
        if not 0 <= value <= MAX_SUN:
            raise ValueError(f"Sun must be between 0 and {MAX_SUN}")
        rec = self._record(index)
        rel = SUN_RELATIVE_OFFSET if player == 1 else SUN_P2_RELATIVE_OFFSET
        if player not in (1, 2):
            raise ValueError("player must be 1 or 2")
        struct.pack_into("<i", self.raw, rec.payload_offset + rel, value)

    def max_sun(self, index: int, include_player2: bool = False):
        self.set_sun(index, MAX_SUN, 1)
        if include_player2:
            self.set_sun(index, MAX_SUN, 2)

    def compressed_bytes(self, level: int = 9) -> bytes:
        obj = zlib.compressobj(level=level, wbits=-15)
        out = obj.compress(bytes(self.raw)) + obj.flush()
        # Structural round-trip validation.
        check = InGameSave(out)
        if len(check.raw) != len(self.raw):
            raise InGameFormatError("In-game save recompression validation failed")
        if bytes(check.raw) != bytes(self.raw):
            raise InGameFormatError("In-game save round-trip did not preserve raw data")
        return out

    def verify_record(self, compressed: bytes, index: int, p1: int, p2: int, run_stage: int | None = None):
        check = InGameSave(compressed)
        if len(check.records) != len(self.records):
            raise InGameFormatError("SaveHeader record count changed unexpectedly")
        if check.get_sun(index, 1) != p1 or check.get_sun(index, 2) != p2:
            raise InGameFormatError("Sun value verification failed after recompression")
        if run_stage is not None:
            if not check.has_run_stage(index) or check.get_run_stage(index) != run_stage:
                raise InGameFormatError("Streak/stage verification failed after recompression")

    # Backward-compatible name used by v2.5 callers.
    def verify_sun(self, compressed: bytes, index: int, p1: int, p2: int):
        self.verify_record(compressed, index, p1, p2, None)

    def record_summary(self, index: int) -> dict[str, int | str | None]:
        r = self._record(index)
        stage = self.get_run_stage(index) if self.has_run_stage(index) else None
        return {
            "slot": index,
            "version": r.version,
            "level_id": r.level_id,
            "mode": self.mode_name(index),
            "data_size": r.data_size,
            "sun_p1": self.get_sun(index, 1),
            "sun_p2": self.get_sun(index, 2),
            "run_stage": stage,
            "stage_label": self.run_stage_label(index) if stage is not None else "",
            "header_offset": r.header_offset,
        }
