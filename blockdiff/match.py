# blockdiff/match.py
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
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional

from .cacycle import BlockDiffEngine, DiffBlock as EngineBlock


@dataclass
class MoveFragment:
    kind: str
    content: str

@dataclass
class MovedBlock:
    source_file: str
    source_line: int
    target_file: str
    target_line: int
    content: str
    fragments: List[MoveFragment] = field(default_factory=list)
    color_id: Optional[int] = None

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
    order = sorted(dict.fromkeys(list(old_files) + list(new_files)))
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
                 first_file: Optional[str]) -> Tuple[Optional[str], Optional[int]]:
    """Returns (owning_file, that_file's_sentinel_start_offset). None offset ->
    (None, None): the block has no address on this side."""
    if char_offset is None or not marks:
        return None, None
    owner, owner_offset = first_file, marks[0][0] if marks else None
    for offset, path in marks:
        if offset <= char_offset:
            owner, owner_offset = path, offset
        else:
            break
    return owner, owner_offset


_SEP_WITH_PADDING_RE = re.compile(
    r"\n\n" + re.escape(_FENCE) + r"[0-9a-f]{32}" + re.escape(_END) + r"\n\n")

def _clean(text: str) -> str:
    """Strip sentinel + its injected \\n\\n padding for DISPLAY only. Bare
    .strip('\\n') would also eat genuine user blank lines at block edges
    (PEP8 spacing, intentional paragraph breaks) — this only removes the
    exact bytes build_blobs put there."""
    text = _SEP_WITH_PADDING_RE.sub("", text)
    return _SEP_RE.sub("", text)  # any sentinel not caught by the padded form

_SENTINEL_LEN = len(_FENCE) + 32 + len(_END)  # module-level constant

def _line_of(char_offset: Optional[int], file_start_offset: Optional[int],
             file_text: str) -> int:
    """Exact line number of char_offset relative to its file's own text,
    computed from authored positions, never by searching file_text for a
    string. -1 means "no real address here" (e.g. a '+' has no old_char, a
    pure-rewrite move has no shared '=' anchor) — an honest absence, not a
    guess."""
    if char_offset is None or file_start_offset is None:
        return -1
    rel = char_offset - file_start_offset - _SENTINEL_LEN - 2  # -2 for "\n\n"
    if rel < 0 or rel > len(file_text):
        return -1
    return file_text.count('\n', 0, rel) + 1


def classify(blocks: List[EngineBlock],
             old_marks: List[Tuple[int, str]], new_marks: List[Tuple[int, str]],
             first_file: Optional[str],
             old_files: Dict[str, str], new_files: Dict[str, str]
             ) -> Tuple[List[ResultBlock], List[ResultBlock], List[MovedBlock]]:
    removed: List[ResultBlock] = []
    added: List[ResultBlock] = []
    moved: List[MovedBlock] = []

    groups_dict = {}
    for b in blocks:
        if b.type == '|':
            continue
        if b.group is not None:
            groups_dict.setdefault(b.group, []).append(b)

    for group_id, group_blocks in groups_dict.items():
        fragments = []
        for b in group_blocks:
            content = _clean(b.text or "")
            if content:
                fragments.append((b, content))
        if not fragments:
            continue

        src = dst = None
        src_off = dst_off = None
        has_plus = any(b.type == '+' for b, _ in fragments)
        for b, content in fragments:
            if b.type == '=':
                src, src_off = _file_owning(b.old_char, old_marks, first_file)
                dst, dst_off = _file_owning(b.new_char, new_marks, first_file)
                break

        # A group is a MOVE — cross-file OR same-file threaded edit — only if
        # it actually relocates/inserts content (has a '+' somewhere, or its
        # anchor genuinely crosses files). A group that is JUST a stationary
        # anchor plus a '-' with nothing added anywhere is a plain deletion:
        # nothing moved, nothing was inserted, it just left. That must stay
        # in `removed`, not get wrapped in a same-file "move" that reports
        # nothing on the target side.
        is_real_move = src is not None and dst is not None and (src != dst or has_plus)

        if is_real_move:
            move_fragments = [MoveFragment(b.type, c) for b, c in fragments]
            joined_content = "".join(c for b, c in fragments if b.type in ('=', '+'))
            first_eq = next(((b, c) for b, c in fragments if b.type == '='), None)
            source_line = _line_of(first_eq[0].old_char, src_off, old_files.get(src, "")) if first_eq else -1
            target_line = _line_of(first_eq[0].new_char, dst_off, new_files.get(dst, "")) if first_eq else -1
            
            # Pull color_id off any fragment block in this group. 
            # If it's a fixed=True move (the DP stationary spine), this gracefully stays None.
            color_id = next((b.color_id for b, _c in fragments if getattr(b, 'color_id', None) is not None), None)

            moved.append(MovedBlock(
                source_file=src, source_line=source_line,
                target_file=dst, target_line=target_line,
                content=joined_content, fragments=move_fragments,
                color_id=color_id))
        else:
            for b, content in fragments:
                if b.type == '-':
                    b_src, b_off = _file_owning(b.old_char, old_marks, first_file)
                    if b_src is not None:
                        removed.append(ResultBlock(
                            b_src, _line_of(b.old_char, b_off, old_files.get(b_src, "")), content))
                elif b.type == '+':
                    b_dst, b_off = _file_owning(b.new_char, new_marks, first_file)
                    if b_dst is not None:
                        added.append(ResultBlock(
                            b_dst, _line_of(b.new_char, b_off, new_files.get(b_dst, "")), content))

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
