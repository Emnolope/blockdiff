
# match.py — recover which file each piece of a diff belongs to.
#
# Git reports a cross-file move as a delete in one file plus an insert in
# another, which is indistinguishable from loss. To see the move, we glue all
# old files into one blob and all new files into another, then diff ONCE. A
# cross-file move is now an in-blob move the engine finds natively.
#
# The engine decides everything: what moved, what's noise, how to resolve two
# near-identical blocks. That judgment lives in cacycle's keystroke-energy
# metric. By the time blocks arrive here, every verdict is final in `fixed`.
#
# This file only does attribution: put each block back in its file. Two stages:
#     STAGE 1  desentinel: engine blocks -> TaggedFragments (facts)
#     STAGE 2  classify:   TaggedFragments -> moved / removed / added (reads verdicts)
#
# If twins seem mishandled, tune the engine's energy knobs (move_base,
# move_log_k, w_char). Never add a second decision layer here.

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


@dataclass
class TaggedFragment:
    """A piece of the diff with its sentinels stripped and its file recovered.
    `side` is 'old' or 'new'; a '=' block exists on both sides and its file can
    differ per side, so the two are kept separate until classify reconciles."""
    file_path: str
    kind: str          # '=', '-', '+'
    side: str          # 'old' or 'new'
    fixed: Optional[bool]
    content: str


# Private-use fences no real text contains, wrapping 32 random hex. The
# uniqueness makes the engine anchor each sentinel instead of folding it into a
# moved run.
_FENCE, _END = "\ue000\ue001\ue002", "\ue003\ue004\ue005"
_SEP_RE = re.compile(re.escape(_FENCE) + r"([0-9a-f]{32})" + re.escape(_END))


def _new_sentinel() -> str:
    return f"{_FENCE}{uuid.uuid4().hex}{_END}"


def build_blobs(old_files: Dict[str, str], new_files: Dict[str, str]):
    """Concatenate files into two blobs. Each file is preceded by a sentinel
    that is identical across old and new, so the engine anchors it and stage 1
    can name every fragment by the sentinel to its left. Both blobs open with a
    sentinel, so no fragment ever precedes the first one."""
    order = list(dict.fromkeys(list(old_files) + list(new_files)))
    sep_to_file: Dict[str, str] = {}
    old_parts, new_parts = [], []

    for path in order:
        sentinel = _new_sentinel()
        sep_to_file[sentinel] = path
        old_parts.append(f"{sentinel}\n\n{old_files.get(path, '')}\n\n")
        new_parts.append(f"{sentinel}\n\n{new_files.get(path, '')}\n\n")

    first_file = order[0] if order else None
    return "".join(old_parts), "".join(new_parts), sep_to_file, first_file


def _read_side(blocks: List[EngineBlock], kinds: Tuple[str, ...], side: str,
               sep_to_file: Dict[str, str], first_file: Optional[str]
               ) -> List[TaggedFragment]:
    """Walk the blocks this side can see, split each on its sentinels, and tag
    every surviving piece with the file named by the sentinel to its left.
    `open_file` names the current file; each sentinel overwrites it absolutely,
    so it never drifts."""
    fragments: List[TaggedFragment] = []
    open_file = first_file

    for block in blocks:
        if block.type not in kinds:
            continue
        text = block.text or ""

        cut = 0
        for hit in _SEP_RE.finditer(text):
            before = text[cut:hit.start()].strip("\n")
            if before and open_file is not None:
                fragments.append(TaggedFragment(open_file, block.type, side,
                                                block.fixed, before))
            open_file = sep_to_file.get(hit.group(0), open_file)
            cut = hit.end()

        tail = text[cut:].strip("\n")
        if tail and open_file is not None:
            fragments.append(TaggedFragment(open_file, block.type, side,
                                            block.fixed, tail))

    return fragments


def desentinel(blocks: List[EngineBlock], sep_to_file: Dict[str, str],
               first_file: Optional[str]
               ) -> Tuple[List[TaggedFragment], List[TaggedFragment]]:
    """Two reads: the old side sees '='/'-', the new side sees '='/'+'.
    Returns (old_fragments, new_fragments)."""
    old_frags = _read_side(blocks, ('=', '-'), 'old', sep_to_file, first_file)
    new_frags = _read_side(blocks, ('=', '+'), 'new', sep_to_file, first_file)
    return old_frags, new_frags


def _line_of(content: str, fragment: str) -> int:
    """Line number of a fragment within its file, or -1 if it isn't present
    verbatim. Computed by lookup, never by a running offset, so it can't drift."""
    idx = content.find(fragment)
    if idx == -1 and fragment.strip():
        idx = content.find(fragment.strip())
    return content.count('\n', 0, idx) + 1 if idx != -1 else -1


def _sole_home(fragments: List[TaggedFragment]) -> Dict[str, str]:
    """Map content -> file, but only for content that lives in exactly one file.
    Content appearing in several files is omitted, so a move whose source or
    target is ambiguous is left to fall through as add/remove rather than
    guessed into a wrong pairing."""
    homes: Dict[str, List[str]] = {}
    for frag in fragments:
        homes.setdefault(frag.content, []).append(frag.file_path)
    return {content: files[0] for content, files in homes.items() if len(files) == 1}


def _proven_moves(old_frags, new_frags, old_files, new_files) -> List[MovedBlock]:
    """Recover FROM/TO for blocks the engine already proved moved (fixed is
    False). A move is reported only when its content has a single home on each
    side and those homes differ."""
    old_moved = [f for f in old_frags if f.kind == '=' and f.fixed is False]
    new_moved = [f for f in new_frags if f.kind == '=' and f.fixed is False]
    old_home = _sole_home(old_moved)
    new_home = _sole_home(new_moved)

    moves = []
    for content, source in old_home.items():
        target = new_home.get(content)
        if target is not None and target != source:
            moves.append(MovedBlock(
                source, _line_of(old_files.get(source, ""), content),
                target, _line_of(new_files.get(target, ""), content), content))
    return moves


def classify(old_frags: List[TaggedFragment], new_frags: List[TaggedFragment],
             old_files: Dict[str, str], new_files: Dict[str, str]
             ) -> Tuple[List[ResultBlock], List[ResultBlock], List[MovedBlock]]:
    """Read the engine's verdicts: proven moves become MovedBlocks with
    recovered FROM/TO; every '-' is removed; every '+' is added. No re-deciding
    — a block the engine declined to anchor is honestly an add and a remove."""
    moved = _proven_moves(old_frags, new_frags, old_files, new_files)

    removed = [ResultBlock(f.file_path, _line_of(old_files.get(f.file_path, ""), f.content), f.content)
               for f in old_frags if f.kind == '-']
    added = [ResultBlock(f.file_path, _line_of(new_files.get(f.file_path, ""), f.content), f.content)
             for f in new_frags if f.kind == '+']

    return removed, added, moved


def find_moves(old_files: Dict[str, str],
               new_files: Dict[str, str],
               engine_config: Optional[Dict] = None
               ) -> Tuple[List[ResultBlock], List[ResultBlock], List[MovedBlock]]:
    """Glue -> diff once -> recover fragments -> read verdicts."""
    old_blob, new_blob, sep_to_file, first_file = build_blobs(old_files, new_files)

    engine = BlockDiffEngine(**(engine_config or {}))
    blocks = engine.compute_diff(old_blob, new_blob)

    old_frags, new_frags = desentinel(blocks, sep_to_file, first_file)
    return classify(old_frags, new_frags, old_files, new_files)
