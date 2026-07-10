# match.py — ATTRIBUTION ONLY. This file is STUPID ON PURPOSE.
#
# ┌─────────────────────────────────────────────────────────────────────────┐
# │ READ THIS BEFORE YOU CHANGE ANYTHING. TO THE NEXT AI ESPECIALLY.         │
# │                                                                          │
# │ The engine (cacycle.py) is the intelligent one. It owns EVERY heuristic, │
# │ EVERY decision, and it does the ACTUAL MOVING. By the time blocks reach  │
# │ this file, the engine has ALREADY decided what is a move, what is        │
# │ stationary, what was added, what was removed. It stamped that verdict on │
# │ each block as (b.type + b.fixed).                                        │
# │                                                                          │
# │ THIS FILE'S ONLY JOB: read that verdict and answer ONE arithmetic        │
# │ question — "which file does this character offset fall in?" — then slap  │
# │ that file label onto the engine's verdict. That is attribution. It is    │
# │ NOT classification. It is NOT judgment. It is NOT deciding move-vs-not.  │
# │                                                                          │
# │ If you ever find yourself writing `if src != dst:` to DECIDE whether     │
# │ something moved — STOP. That is the exact bug this rewrite killed. The   │
# │ engine already knows. See the tombstone in the '=' branch below.         │
# │                                                                          │
# │ If you ever want to add a size gate, a "worth it" check, a min-words, a  │
# │ noise floor, an energy metric — STOP. That lives in the engine           │
# │ (block_min_length + _unlink_blocks). Adding it here re-grows the         │
# │ intelligence we deliberately amputated. The whole point of the blob      │
# │ architecture is that the engine is smart so this file can be dumb.       │
# └─────────────────────────────────────────────────────────────────────────┘
#
# WHY A BLOB AT ALL: git reports a cross-file move as a delete in file A plus an
# insert in file B — indistinguishable from loss. To let the engine SEE the
# move, we glue all old files into one blob and all new files into another,
# separated by runtime-random sentinels, and diff ONCE. A cross-file move is now
# an ordinary in-blob move the engine detects natively. After the diff, we look
# at which sentinel each block sits behind to recover its file. That recovery is
# ALL this file does.
#
# THE COORDINATE SYSTEM: characters. The engine stamps old_char / new_char on
# every block (its position in each blob). File attribution is pure arithmetic
# on those offsets against the sentinel offsets we ourselves authored in
# build_blobs. We never tokenize, never search content, never key on text.
#
# WHY THIS SURVIVES TWINS / STRADDLES: identity is the block's character offset,
# a distinct integer per block. Two near-identical paragraphs — even the SAME
# paragraph at file A's tail and file B's head across one sentinel — sit at
# different offsets and can never alias. Content is CARGO: used only for display
# and cosmetic line numbers, NEVER to decide a file or a match.

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
# is a clean boundary that never fuses with surrounding content.
_FENCE, _END = "\ue000\ue001\ue002", "\ue003\ue004\ue005"
_SEP_RE = re.compile(re.escape(_FENCE) + r"([0-9a-f]{32})" + re.escape(_END))


def _new_sentinel() -> str:
    return f"{_FENCE}{uuid.uuid4().hex}{_END}"

def build_blobs(old_files: Dict[str, str], new_files: Dict[str, str]):
    """Concatenate files into two blobs, each file preceded by a sentinel
    identical across old and new. Records, per side, each sentinel's CHARACTER
    OFFSET (for attribution) AND its (start,end) span (for the engine's
    stationary prelinks — the poles).

    Returns:
        old_blob, new_blob, first_file,
        old_marks, new_marks,        # each sorted list of (char_offset, file)
        prelinks                     # list of (old_span, new_span, "stationary")
                                     # one per file, feeding compute_diff.
    """
    order = list(dict.fromkeys(list(old_files) + list(new_files)))
    old_parts, new_parts = [], []
    old_marks: List[Tuple[int, str]] = []
    new_marks: List[Tuple[int, str]] = []
    prelinks: List[Tuple[Tuple[int, int], Tuple[int, int], str]] = []
    old_len = 0
    new_len = 0

    for path in order:
        sentinel = _new_sentinel()
        slen = len(sentinel)

        old_marks.append((old_len, path))
        new_marks.append((new_len, path))

        # Each sentinel is a stationary pole: same content, same logical place,
        # pinned as the ground frame on both sides.
        prelinks.append(((old_len, old_len + slen),
                         (new_len, new_len + slen),
                         "stationary"))

        chunk_old = f"{sentinel}\n\n{old_files.get(path, '')}\n\n"
        old_parts.append(chunk_old)
        old_len += len(chunk_old)

        chunk_new = f"{sentinel}\n\n{new_files.get(path, '')}\n\n"
        new_parts.append(chunk_new)
        new_len += len(chunk_new)

    first_file = order[0] if order else None
    return ("".join(old_parts), "".join(new_parts), first_file,
            old_marks, new_marks, prelinks)

def _file_owning(char_offset: Optional[int], marks: List[Tuple[int, str]],
                 first_file: Optional[str]) -> Optional[str]:
    """THE ONLY LEGAL CLEVERNESS IN THIS FILE, and it is not even clever — it is
    arithmetic. Return the file whose sentinel most recently opened at or before
    char_offset. This is a READ of positions we authored in build_blobs, not a
    search for something unknown.

    None offset means the block has no address on this side (a '-' has no new
    address, a '+' has no old) -> None owner. That is correct and expected."""
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
    A first-match find is fine: this is display, never identity. Returns -1
    honestly rather than lying with a plausible-but-wrong number."""
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
    """Read the engine's verdict off each block; attach a file label. NO
    DECISIONS. The engine already decided (b.type + b.fixed); we translate its
    verdict into per-file rows.

    Engine verdict -> what we do (attribution only):
        '-'                 -> removed, filed at its old-side sentinel
        '+'                 -> added,   filed at its new-side sentinel
        '=' with fixed=True -> stationary spine: the engine decided it did NOT
                               move. We emit NOTHING. Not our call to overrule.
        '=' with fixed=False-> the engine decided this run is a MOVED group.
                               We emit a move and LABEL both ends by sentinel.
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
            # Engine verdict: removed. Attribute to its old-side file.
            src = _file_owning(b.old_char, old_marks, first_file)
            if src is not None:
                removed.append(ResultBlock(
                    src, _line_of(old_files.get(src, ""), content), content))

        elif b.type == '+':
            # Engine verdict: added. Attribute to its new-side file.
            dst = _file_owning(b.new_char, new_marks, first_file)
            if dst is not None:
                added.append(ResultBlock(
                    dst, _line_of(new_files.get(dst, ""), content), content))

        elif b.type == '=':
            # ───────────────────────── TOMBSTONE ─────────────────────────
            # The OLD code did this here:
            #
            #     src = _file_owning(b.old_char, ...)
            #     dst = _file_owning(b.new_char, ...)
            #     if src is not None and dst is not None and src != dst:
            #         moved.append(...)
            #     # src == dst -> emit nothing
            #
            # That `src != dst` was match.py DECIDING what moved — a judgment
            # that belongs to the engine, re-derived here from the sentinel
            # layout. It was WRONG two ways:
            #   1. It took a hard dependency on the blob/sentinel trick. In
            #      --files mode (one file pair, effectively one blob-pair with
            #      one sentinel each side) src can never != dst, so real
            #      within-blob moves the engine found were silently dropped.
            #   2. It ignored the verdict the engine ALREADY stamped (b.fixed),
            #      reinventing move-detection out of file comparison instead of
            #      reading the answer sitting on the block.
            #
            # THE FIX: read b.fixed. The engine's _set_fixed / _insert_marks
            # machinery already decided whether this '=' run is stationary spine
            # (fixed=True) or a relocated group (fixed=False). We obey it. We do
            # NOT compare src and dst to decide anything. We compare nothing.
            # DO NOT RESURRECT `src != dst` AS A DECISION. Ever.
            # ──────────────────────────────────────────────────────────────
            if b.fixed:
                continue  # engine says stationary spine -> not a move -> emit nothing

            # engine says fixed=False -> this run MOVED. We only LABEL its ends.
            # No size gate, no "worth it" check, no straddle special-casing.
            # If a moved group straddles a sentinel and one end is a single
            # word, we DO NOT CARE — that is an edge case and the engine's
            # noise floor (block_min_length + _unlink_blocks) already governs
            # what counts as a real run. Adding a threshold here re-grows the
            # intelligence we amputated. Don't.
            src = _file_owning(b.old_char, old_marks, first_file)
            dst = _file_owning(b.new_char, new_marks, first_file)
            if src is not None and dst is not None:
                moved.append(MovedBlock(
                    src, _line_of(old_files.get(src, ""), content),
                    dst, _line_of(new_files.get(dst, ""), content), content))

    return removed, added, moved

def find_moves(old_files: Dict[str, str],
               new_files: Dict[str, str],
               engine_config: Optional[Dict] = None
               ) -> Tuple[List[ResultBlock], List[ResultBlock], List[MovedBlock]]:
    """Glue -> diff ONCE (with the file sentinels pinned as stationary poles)
    -> attribute each block by the engine's verdict. The engine does the
    thinking; the sentinels nail the coordinate frame so a whole-body move can
    no longer crown itself the ground and vanish."""
    (old_blob, new_blob, first_file, old_marks, new_marks,
     prelinks) = build_blobs(old_files, new_files)

    engine = BlockDiffEngine(**(engine_config or {}))
    blocks = engine.compute_diff(old_blob, new_blob, prelinks=prelinks)

    return classify(blocks, old_marks, new_marks, first_file, old_files, new_files)
