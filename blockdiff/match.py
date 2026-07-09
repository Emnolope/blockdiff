# match.py — find content that moved between files.
#
# Git shows a cross-file move as a delete in A + insert in B — indistinguishable
# from real loss. So we don't diff files pairwise (pairwise literally cannot see
# content leaving a file). We glue all old files into one blob, all new into
# another, and diff ONCE; a cross-file move becomes an in-blob move the engine
# already finds. The surviving hard part — putting each block back in its file —
# is split into two honest stages because the seam between them is where every
# prior version hid a lie:
#
#     STAGE 1  desentinel: engine blocks -> TaggedFragments.  Facts only.
#     STAGE 2  classify:   TaggedFragments -> moved/removed/added.  Judgment.
#
# Stage 1 is a real inspectable value, not a claim in a comment, because a
# comment asserting a stage the code doesn't actually isolate is what let a
# false invariant steer a past branch into a silent mis-attribution.

import re
import uuid
from collections import Counter
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
    """One piece of the diff after sentinels are cut out: a fact, not a verdict.
    `side` records which stream it was read from ('old'/'new') because a '='
    block lives on both and its file differs per side — reconciling that is
    stage 2's job, so stage 1 refuses to."""
    file_path: str
    kind: str          # '=', '-', '+'
    side: str          # 'old' or 'new'
    fixed: Optional[bool]
    content: str       # sentinels removed, structural glue trimmed


# Private-use fences no real text can contain, wrapping 32 random hex: the
# uniqueness is what makes the engine treat each sentinel as an anchor it can
# never fold into a moved run.
_FENCE, _END = "\ue000\ue001\ue002", "\ue003\ue004\ue005"
_SEP_RE = re.compile(re.escape(_FENCE) + r"([0-9a-f]{32})" + re.escape(_END))


def _new_sentinel() -> str:
    return f"{_FENCE}{uuid.uuid4().hex}{_END}"


def build_blobs(old_files: Dict[str, str], new_files: Dict[str, str]):
    """Both blobs open with a sentinel so nothing ever precedes the first one —
    that absence is what makes stage-1 attribution a local split with no
    look-back. Same `order` drives both sides, so a file's sentinel is identical
    across old and new and the engine can anchor it."""
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
    """STAGE 1, one side. Walk the blocks this side can see, split each on its
    sentinels, and tag every surviving piece with the file named by the sentinel
    to its left. `open_file` is the whole of the state: it names the file a
    sentinel-free fragment falls into, and every sentinel overwrites it
    absolutely, so it cannot accumulate error the way a counted cursor did."""
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
    """STAGE 1 whole. Two reads because a side only sees some blocks: old sees
    '='/'-', new sees '='/'+'. Returned as (old_fragments, new_fragments) — a
    literal value you can print and assert on, which is the entire point of
    giving this stage a type instead of leaving it in spirit."""
    old_frags = _read_side(blocks, ('=', '-'), 'old', sep_to_file, first_file)
    new_frags = _read_side(blocks, ('=', '+'), 'new', sep_to_file, first_file)
    return old_frags, new_frags


def _line_of(content: str, fragment: str) -> int:
    """Post-hoc, never a running offset, so it can't drift. -1 if the engine
    split the fragment mid-token and it isn't present verbatim."""
    idx = content.find(fragment)
    if idx == -1 and fragment.strip():
        idx = content.find(fragment.strip())
    return content.count('\n', 0, idx) + 1 if idx != -1 else -1


def _sole_home(fragments: List[TaggedFragment]) -> Dict[str, str]:
    """Map content -> its file, but only for content with exactly one home.
    Ambiguous content (same text in several files) is omitted so stage 2 can
    refuse to guess where it went — the criss-cross the user feared."""
    homes: Dict[str, List[str]] = {}
    for frag in fragments:
        homes.setdefault(frag.content, []).append(frag.file_path)
    return {content: files[0] for content, files in homes.items() if len(files) == 1}


def _proven_moves(old_frags, new_frags, old_files, new_files) -> List[MovedBlock]:
    """The engine already proved these moved (fixed is False); we only recover
    FROM/TO. A move is trustworthy only when its content has one home per side
    and the homes differ — otherwise which instance went where is a guess."""
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


def _promote_twins(removed: List[ResultBlock], added: List[ResultBlock]):
    """Two near-identical paragraphs anchor nothing, so the engine honestly
    emits them as separate -/+. Upgrade a pair to a move only when its text is
    byte-identical and unique on each side; positional pairing of duplicates is
    the criss-cross bug, so 2+ on either side stays an honest add+remove."""
    rem_counts = Counter(r.content for r in removed)
    add_counts = Counter(a.content for a in added)
    first_add = {}
    for i, a in enumerate(added):
        first_add.setdefault(a.content, i)

    used_r, used_a, promoted = set(), set(), []
    for ri, r in enumerate(removed):
        if rem_counts[r.content] == 1 and add_counts.get(r.content, 0) == 1:
            ai = first_add[r.content]
            a = added[ai]
            promoted.append(MovedBlock(r.file_path, r.start_line,
                                       a.file_path, a.start_line, r.content))
            used_r.add(ri)
            used_a.add(ai)

    kept_removed = [r for i, r in enumerate(removed) if i not in used_r]
    kept_added = [a for i, a in enumerate(added) if i not in used_a]
    return kept_removed, kept_added, promoted


def classify(old_frags: List[TaggedFragment], new_frags: List[TaggedFragment],
             old_files: Dict[str, str], new_files: Dict[str, str]
             ) -> Tuple[List[ResultBlock], List[ResultBlock], List[MovedBlock]]:
    """STAGE 2. Pure judgment on stage-1 facts: no regex, no sentinels, no carry
    state — those all died in stage 1. Just verdicts."""
    moved = _proven_moves(old_frags, new_frags, old_files, new_files)

    removed = [ResultBlock(f.file_path, _line_of(old_files.get(f.file_path, ""), f.content), f.content)
               for f in old_frags if f.kind == '-']
    added = [ResultBlock(f.file_path, _line_of(new_files.get(f.file_path, ""), f.content), f.content)
             for f in new_frags if f.kind == '+']

    removed, added, promoted = _promote_twins(removed, added)
    moved.extend(promoted)
    return removed, added, moved


def find_moves(old_files: Dict[str, str],
               new_files: Dict[str, str],
               engine_config: Optional[Dict] = None
               ) -> Tuple[List[ResultBlock], List[ResultBlock], List[MovedBlock]]:
    """Orchestrator: glue -> diff once -> stage 1 facts -> stage 2 judgment.
    The thinness here is deliberate; all the danger lives in the two named
    stages, where it can be seen."""
    old_blob, new_blob, sep_to_file, first_file = build_blobs(old_files, new_files)

    engine = BlockDiffEngine(**(engine_config or {}))
    blocks = engine.compute_diff(old_blob, new_blob)

    old_frags, new_frags = desentinel(blocks, sep_to_file, first_file)
    return classify(old_frags, new_frags, old_files, new_files)
if not candidates:
            continue
        # Take the first still-unconsumed add with identical content.
        for a_idx in candidates:
            if a_idx in consumed_added:
                continue
            a = added[a_idx]
            # Only a move if it actually went somewhere different.
            if a.file_path == r.file_path and a.start_line == r.start_line:
                continue
            promoted.append(MovedBlock(
                source_file=r.file_path, source_line=r.start_line,
                target_file=a.file_path, target_line=a.start_line,
                content=r.content,
            ))
            consumed_added.add(a_idx)
            consumed_removed.add(r_idx)
            break

    removed_out = [r for i, r in enumerate(removed) if i not in consumed_removed]
    added_out = [a for i, a in enumerate(added) if i not in consumed_added]
    return removed_out, added_out, promoted


def find_moves(old_files: Dict[str, str],
               new_files: Dict[str, str],
               min_words: int = 3,
               engine_config: Optional[Dict] = None
               ) -> Tuple[List[ResultBlock], List[ResultBlock], List[MovedBlock]]:

    old_blob, new_blob, markers, old_regions, new_regions = build_blobs(old_files, new_files)

    engine = BlockDiffEngine(**(engine_config or {}))
    blocks: List[EngineBlock] = engine.compute_diff(old_blob, new_blob)

    old_text = engine.old_text
    new_text = engine.new_text

    old_offsets = _build_offset_map(old_text) if old_text is not None else {}
    new_offsets = _build_offset_map(new_text) if new_text is not None else {}

    removed: List[ResultBlock] = []
    added: List[ResultBlock] = []
    moved: List[MovedBlock] = []

    for b in blocks:
        clean = _strip_seps(b.text or "")
        if not clean.strip():
            continue

        if b.type == '=':
            # A MOVE cacycle PROVED. Never gate behind min_words.
            if b.fixed is False and b.old_number is not None and b.new_number is not None:
                src_off = old_offsets.get(b.old_number, 0)
                dst_off = new_offsets.get(b.new_number, 0)
                src_file, src_line = _file_and_line(src_off, old_blob, old_regions)
                dst_file, dst_line = _file_and_line(dst_off, new_blob, new_regions)
                if not (src_file == dst_file and src_line == dst_line):
                    moved.append(MovedBlock(
                        source_file=src_file, source_line=src_line,
                        target_file=dst_file, target_line=dst_line,
                        content=clean,
                    ))

        elif b.type == '-':
            if b.old_number is not None and _passes_gate(clean, min_words):
                off = old_offsets.get(b.old_number, 0)
                f, ln = _file_and_line(off, old_blob, old_regions)
                removed.append(ResultBlock(f, ln, clean))

        elif b.type == '+':
            if b.new_number is not None and _passes_gate(clean, min_words):
                off = new_offsets.get(b.new_number, 0)
                f, ln = _file_and_line(off, new_blob, new_regions)
                added.append(ResultBlock(f, ln, clean))

    # Post-pass: recover the twins cacycle honestly couldn't disambiguate.
    removed, added, promoted = _promote_exact_twins(removed, added)
    moved.extend(promoted)

    return removed, added, moved
