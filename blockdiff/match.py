# match.py — recover which file each piece of a diff belongs to.
#
# Git reports a cross-file move as a delete in one file plus an insert in
# another, indistinguishable from loss. To SEE the move, we glue all old files
# into one blob and all new files into another, then diff ONCE. A cross-file
# move becomes an in-blob move the engine finds natively.
#
# THE MODEL: one list, ONE COORDINATE SYSTEM (characters), read off each block.
# ---------------------------------------------------------------------------
# The engine now speaks characters at its border (old_char / new_char on every
# block). This file never tokenizes, never searches, never compares content to
# decide a file. A DiffBlock is ONE object carrying TWO addresses:
#
#     '='  : both old_char and new_char. If they sit behind DIFFERENT sentinels,
#            the content flew between files -> MOVE, read off ONE object.
#     '-'  : only old_char -> removed at its old file.
#     '+'  : only new_char -> added at its new file.
#     '|'  : the engine's move ghost. Ignored: the '=' carries its own addresses.
#
# FILE IDENTITY IS PURE ARITHMETIC: file_owning(char_offset) = the file whose
# sentinel offset is the greatest one <= char_offset. We OWN every sentinel
# offset from build_blobs (we laid the blob out ourselves), so there is nothing
# to discover and nothing to search-as-fishing — it's a direct scan of a tiny
# per-file list.
#
# WHY THIS SURVIVES TWINS: identity is the block's character offset, a distinct
# integer per block. Two 95%-identical paragraphs — even the SAME paragraph at
# file A's tail and file B's head across one sentinel — sit at different offsets,
# so they can never alias. No _homes, no _sole_home, no content key, no "decline
# on ambiguity." Content is cargo: used only for display and cosmetic line
# numbers, NEVER to decide file or match sides.

import re
import uuid
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional

from .cacycle import BlockDiffEngine, DiffBlock as EngineBlock


@dataclass
class MovedBlock:
    source_file: str
    source_line: int
    target_file: str
    target_line: int
    content: str


@dataclass
class ResultBlock:
    file_path: str
    start_line: int
    content: str


# Private-use fences no real text contains, wrapping 32 random hex. Uniqueness
# forces the engine to anchor each sentinel as its own token, so its char offset
# is a clean boundary.
_FENCE, _END = "\ue000\ue001\ue002", "\ue003\ue004\ue005"
_SEP_RE = re.compile(re.escape(_FENCE) + r"([0-9a-f]{32})" + re.escape(_END))


def _new_sentinel() -> str:
    return f"{_FENCE}{uuid.uuid4().hex}{_END}"


def build_blobs(old_files: Dict[str, str], new_files: Dict[str, str]):
    """Concatenate files into two blobs. Each file is preceded by a sentinel
    identical across old and new. As we append left to right we record each
    sentinel's CHARACTER OFFSET in each blob — the ground truth file_owning uses.
    Both blobs open with a sentinel, so nothing ever precedes the first one.

    Returns: old_blob, new_blob, first_file,
             old_marks, new_marks  (each a sorted list of (char_offset, file))."""
    order = list(dict.fromkeys(list(old_files) + list(new_files)))
    old_parts, new_parts = [], []
    old_marks: List[Tuple[int, str]] = []
    new_marks: List[Tuple[int, str]] = []
    old_len = 0
    new_len = 0

    for path in order:
        sentinel = _new_sentinel()

        old_marks.append((old_len, path))           # offset where this sentinel begins
        chunk_old = f"{sentinel}\n\n{old_files.get(path, '')}\n\n"
        old_parts.append(chunk_old)
        old_len += len(chunk_old)

        new_marks.append((new_len, path))
        chunk_new = f"{sentinel}\n\n{new_files.get(path, '')}\n\n"
        new_parts.append(chunk_new)
        new_len += len(chunk_new)

    first_file = order[0] if order else None
    # Naturally sorted: we appended in increasing offset order.
    return "".join(old_parts), "".join(new_parts), first_file, old_marks, new_marks


def _file_owning(char_offset: Optional[int], marks: List[Tuple[int, str]],
                 first_file: Optional[str]) -> Optional[str]:
    """The file whose sentinel most recently opened at or before char_offset.
    None offset means the block has no address on this side (a '-' has no new,
    a '+' has no old) -> None. Direct scan of a tiny sorted list; not a search
    for something unknown, a read of positions we authored."""
    if char_offset is None or not marks:
        return None
    owner = first_file
    for offset, path in marks:
        if offset <= char_offset:
            owner = path
        else:
            break
    return owner


def _clean(text: str) -> str:
    """Strip sentinel debris for DISPLAY only. Identity never touched this."""
    return _SEP_RE.sub("", text).strip("\n")


def _line_of(content: str, fragment: str) -> int:
    """Cosmetic line number of a fragment inside its file, or -1 if absent.
    A first-match find is fine here: this is display, never identity."""
    if not fragment:
        return -1
    idx = content.find(fragment)
    if idx == -1 and fragment.strip():
        idx = content.find(fragment.strip())
    return content.count('\n', 0, idx) + 1 if idx != -1 else -1


def classify(blocks: List[EngineBlock],
             old_marks: List[Tuple[int, str]], new_marks: List[Tuple[int, str]],
             first_file: Optional[str],
             old_files: Dict[str, str], new_files: Dict[str, str]
             ) -> Tuple[List[ResultBlock], List[ResultBlock], List[MovedBlock]]:
    """One pass over the engine's ONE block list. Each block is read for its two
    character addresses; the sentinel below each names the file. No pairing, no
    second list, no content key.

        '-'          -> removed at old file
        '+'          -> added   at new file
        '=' same file -> stationary (emit nothing)
        '=' diff file -> MOVED old file -> new file (entanglement off ONE block)
    """
    removed: List[ResultBlock] = []
    added: List[ResultBlock] = []
    moved: List[MovedBlock] = []

    for b in blocks:
        if b.type == '|':
            continue  # move ghost; the '=' block carries its own addresses

        content = _clean(b.text or "")
        if not content:
            continue

        if b.type == '-':
            src = _file_owning(b.old_char, old_marks, first_file)
            if src is not None:
                removed.append(ResultBlock(
                    src, _line_of(old_files.get(src, ""), content), content))

        elif b.type == '+':
            dst = _file_owning(b.new_char, new_marks, first_file)
            if dst is not None:
                added.append(ResultBlock(
                    dst, _line_of(new_files.get(dst, ""), content), content))

        elif b.type == '=':
            src = _file_owning(b.old_char, old_marks, first_file)
            dst = _file_owning(b.new_char, new_marks, first_file)
            if src is not None and dst is not None and src != dst:
                moved.append(MovedBlock(
                    src, _line_of(old_files.get(src, ""), content),
                    dst, _line_of(new_files.get(dst, ""), content), content))
            # src == dst -> stationary -> emit nothing

    return removed, added, moved


def find_moves(old_files: Dict[str, str],
               new_files: Dict[str, str],
               engine_config: Optional[Dict] = None
               ) -> Tuple[List[ResultBlock], List[ResultBlock], List[MovedBlock]]:
    """Glue -> diff once -> classify each block by its two character addresses."""
    old_blob, new_blob, first_file, old_marks, new_marks = build_blobs(
        old_files, new_files)

    engine = BlockDiffEngine(**(engine_config or {}))
    blocks = engine.compute_diff(old_blob, new_blob)

    return classify(blocks, old_marks, new_marks, first_file, old_files, new_files)
