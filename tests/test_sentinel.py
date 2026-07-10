# tests/test_sentinel.py
#
# The one invariant everything else stands on: a sentinel goes INTO a blob and
# comes BACK OUT of the engine's diff intact, its char offset attributes it to a
# file, AND it is held STATIONARY as the ground frame. If any of those breaks,
# cross-file attribution is silently wrong and nothing crashes — the exact
# failure class that ate 40 iterations: no error, just wrong.
#
# LIVE CONTRACT (this is what the current source speaks):
#   build_blobs -> 6-tuple:
#       (old_blob, new_blob, first_file, old_marks, new_marks, prelinks)
#     old_marks/new_marks: sorted [(char_offset, file)] for attribution.
#     prelinks: [(old_span, new_span, "stationary")] one per file — the poles.
#   compute_diff(old, new, prelinks=None): prelinks pin caller correspondences.
#     kind="stationary" -> ground frame (sentinels). kind="moved" -> warm-start
#     door (a prior engine's verdict, believed not re-litigated).
#   Attribution is _file_owning(char_offset) fed into classify().

from blockdiff.match import (
    _new_sentinel, _SEP_RE, build_blobs, _file_owning, _line_of, classify,
)
from blockdiff.cacycle import BlockDiffEngine


def test_sentinel_is_findable():
    """Floor of the floor: the regex matches the thing we generate, whole."""
    s = _new_sentinel()
    m = _SEP_RE.search(s)
    assert m is not None, "regex can't even find a freshly minted sentinel"
    assert m.group(0) == s, "regex matched a SUBSET of the sentinel"


def test_sentinels_are_unique_per_call():
    """Attribution maps offset->file by sentinel. Collisions = cross-wiring."""
    seen = {_new_sentinel() for _ in range(1000)}
    assert len(seen) == 1000, "sentinel collision — runtime uniqueness is a lie"


def test_build_blobs_maps_every_file():
    """Every file gets one sentinel offset per side; the marked-file set equals
    the input-file set; and there's exactly one stationary prelink per file."""
    old = {"a.md": "alpha", "b.md": "beta"}
    new = {"a.md": "alpha", "c.md": "gamma"}
    old_blob, new_blob, first, old_marks, new_marks, prelinks = build_blobs(old, new)

    assert {p for _o, p in old_marks} == {"a.md", "b.md", "c.md"}
    assert {p for _o, p in new_marks} == {"a.md", "b.md", "c.md"}
    assert len(old_marks) == 3, "a file got two sentinels or two share one (old)"
    assert len(new_marks) == 3, "a file got two sentinels or two share one (new)"
    assert first == "a.md"

    # one stationary pole per file
    assert len(prelinks) == 3, "expected exactly one prelink per file"
    assert all(kind == "stationary" for _o, _n, kind in prelinks), \
        "every file-sentinel prelink must be stationary"

    # marks in strictly increasing offset order (build appends left->right)
    assert [o for o, _p in old_marks] == sorted(o for o, _p in old_marks)
    assert [o for o, _p in new_marks] == sorted(o for o, _p in new_marks)

    # each recorded offset actually sits on a real sentinel in its blob
    for offset, _path in old_marks:
        assert _SEP_RE.match(old_blob[offset:]), "old mark offset isn't on a sentinel"
    for offset, _path in new_marks:
        assert _SEP_RE.match(new_blob[offset:]), "new mark offset isn't on a sentinel"

    # each prelink span actually brackets a sentinel on each side
    for (o_s, o_e), (n_s, n_e), _kind in prelinks:
        assert _SEP_RE.match(old_blob[o_s:o_e]), "old prelink span isn't a sentinel"
        assert _SEP_RE.match(new_blob[n_s:n_e]), "new prelink span isn't a sentinel"


def test_file_owning_is_pure_arithmetic():
    """_file_owning reads authored positions, it does not search. The file is
    whichever sentinel offset is the greatest one <= the queried offset. None in
    -> None out (a '-' has no new address, a '+' has no old)."""
    marks = [(0, "a.md"), (100, "b.md"), (250, "c.md")]
    assert _file_owning(0, marks, "a.md") == "a.md"
    assert _file_owning(50, marks, "a.md") == "a.md"
    assert _file_owning(100, marks, "a.md") == "b.md"    # boundary belongs to b
    assert _file_owning(101, marks, "a.md") == "b.md"
    assert _file_owning(249, marks, "a.md") == "b.md"
    assert _file_owning(250, marks, "a.md") == "c.md"
    assert _file_owning(9999, marks, "a.md") == "c.md"
    assert _file_owning(None, marks, "a.md") is None     # no address on this side
    assert _file_owning(5, [], "a.md") is None           # no marks -> no owner


def test_sentinel_survives_the_engine():
    """THE load-bearing claim. Inputs DIFFER so the engine actually tokenizes
    and refines. After a real diff through the LIVE prelink path, every
    classified fragment lands in a real file — no orphans, no sentinel debris."""
    old = {"a.md": "alpha one\nsecond line here", "b.md": "beta two\nmore text"}
    new = {"a.md": "alpha ONE\nsecond line here", "b.md": "beta two\nmore text"}

    old_blob, new_blob, first, old_marks, new_marks, prelinks = build_blobs(old, new)
    blocks = BlockDiffEngine().compute_diff(old_blob, new_blob, prelinks=prelinks)
    removed, added, moved = classify(
        blocks, old_marks, new_marks, first, old, new)

    real_files = {"a.md", "b.md"}
    for r in removed:
        assert r.file_path in real_files, f"removed misfiled to {r.file_path!r}"
    for a in added:
        assert a.file_path in real_files, f"added misfiled to {a.file_path!r}"
    for m in moved:
        assert m.source_file in real_files and m.target_file in real_files, \
            "moved misfiled to a nonexistent file"

    for blk in list(removed) + list(added):
        assert "\ue000" not in blk.content, "sentinel debris leaked into content"
        assert "\ue003" not in blk.content, "sentinel debris leaked into content"
    for m in moved:
        assert "\ue000" not in m.content and "\ue003" not in m.content, \
            "sentinel debris leaked into moved content"

    touched = ({r.file_path for r in removed}
               | {a.file_path for a in added}
               | {m.source_file for m in moved} | {m.target_file for m in moved})
    assert "a.md" in touched, "the a.md edit vanished during attribution"


def test_line_of_reports_minus_one_not_a_lie():
    """_line_of must return -1 for content that isn't present verbatim, rather
    than a plausible-but-wrong line number."""
    content = "line one\nline two\nline three"
    assert _line_of(content, "line two") == 2
    assert _line_of(content, "line one") == 1
    assert _line_of(content, "nonexistent fragment") == -1


def test_sentinels_are_the_fixed_spine_after_a_big_move():
    """THE STREET-POLE TEST, now through the LIVE prelink path. A big body moves
    between files; the sentinels are stationary BY CONSTRUCTION. Every
    sentinel-bearing block must come back fixed=True — the frame must NOT drift.
    A sentinel returning fixed=False is the car-lurching-backward hallucination
    and the root of the whole-body-move-vanishes bug."""
    body = ("first canonical statement of the thesis here\n"
            "third sentence with the crucial caveat that changes everything\n"
            "fifth sentence gesturing vaguely at all the future work")
    old = {"draft.md": f"# title\n\n{body}", "final.md": "# final\n\nplaceholder"}
    new = {"draft.md": "# title\n\n(moved to final)",
           "final.md": f"# final\n\nplaceholder\n\n{body}"}

    old_blob, new_blob, first, old_marks, new_marks, prelinks = build_blobs(old, new)
    blocks = BlockDiffEngine().compute_diff(old_blob, new_blob, prelinks=prelinks)

    sentinel_blocks = [b for b in blocks if _SEP_RE.search(b.text or "")]
    assert sentinel_blocks, "sentinels were absorbed/unlinked — frame dissolved"
    for b in sentinel_blocks:
        assert b.type == '=', f"a sentinel came back as {b.type!r}, not stationary"
        assert b.fixed is True, \
            f"sentinel drifted: fixed={b.fixed!r} — the frame moved (bus illusion)"


def test_anchor_stands_as_its_own_group():
    """The fusion that hid whole-body moves is dead: no sentinel-bearing block
    may also carry non-sentinel payload. If this fails, the fix regressed in
    _get_same_blocks (the run must STOP when anchor-ness flips)."""
    body = ("first canonical statement of the thesis here\n"
            "third sentence with the crucial caveat that changes everything\n"
            "fifth sentence gesturing vaguely at all the future work")
    old = {"draft.md": f"# title\n\n{body}", "final.md": "# final\n\nplaceholder"}
    new = {"draft.md": "# title\n\n(moved to final)",
           "final.md": f"# final\n\nplaceholder\n\n{body}"}

    old_blob, new_blob, first, old_marks, new_marks, prelinks = build_blobs(old, new)
    blocks = BlockDiffEngine().compute_diff(old_blob, new_blob, prelinks=prelinks)

    for b in blocks:
        if _SEP_RE.search(b.text or ""):
            stripped = _SEP_RE.sub("", b.text).strip()
            assert stripped == "", \
                f"anchor FUSED with payload {stripped!r} — fix regressed in _get_same_blocks"


def test_prelink_moved_is_believed_not_relitigated():
    """THE DOOR — warm-start / engine-chaining hinge. A caller asserts, via
    kind='moved', that a run is the SAME content in a NEW position (as if a prior
    engine found it). The engine must force-link and BELIEVE it, not tear it
    apart. We prove the content survives as a run flagged is_prelink_moved.

    HONEST SCOPE: this proves the pin is RESPECTED, NOT that chaining two real
    engines is optimal. It's the hinge, not the whole gate — unproven under a
    real second engine, by design, until one exists to test it."""
    shared = "this exact run is asserted moved by an upstream pass do not touch it"
    old = shared + "\n\ntail that stays"
    new = "head that stays\n\n" + shared

    o_start = old.index(shared)
    n_start = new.index(shared)
    prelinks = [((o_start, o_start + len(shared)),
                 (n_start, n_start + len(shared)), "moved")]

    blocks = BlockDiffEngine().compute_diff(old, new, prelinks=prelinks)

    moved_runs = [b for b in blocks if b.is_prelink_moved]
    assert moved_runs, "prelink 'moved' was ignored — the door didn't open"
    joined = "".join(b.text for b in moved_runs)
    assert "asserted moved by an upstream pass" in joined, \
        "caller-asserted moved content was torn apart instead of believed"
