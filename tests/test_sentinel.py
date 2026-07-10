# tests/test_sentinel.py
#
# The one invariant everything else stands on: a sentinel goes INTO a blob and
# comes BACK OUT of the engine's diff intact, and _SEP_RE finds it. If the
# engine's tokenizer ever splits a fence across tokens, every cross-file
# attribution is silently wrong and NOTHING crashes. That is the exact failure
# class that ate 40 iterations: no error, just wrong. So we test it directly,
# below the whole pipeline, no git.
#
# CONTRACT NOTE (why this file was rewritten): the LIVE match.py speaks the
# char-offset model. build_blobs returns a 5-tuple:
#     (old_blob, new_blob, first_file, old_marks, new_marks)
# where each *_marks is a sorted list of (char_offset, file). There is NO
# desentinel, NO sep_map, NO fragment object with .kind/.fixed. Attribution is
# _file_owning(char_offset) fed into classify(). An earlier version of this file
# imported a `desentinel` that never existed in the live source — drift from a
# dead architecture. Fixed to the real contract.

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
    """Every file gets exactly one sentinel offset on each side; the union of
    marked files equals the union of inputs. first_file is the leftmost — the
    default owner for anything sitting before the first sentinel (nothing should,
    since both blobs OPEN with a sentinel, but the default stays honest)."""
    old = {"a.md": "alpha", "b.md": "beta"}
    new = {"a.md": "alpha", "c.md": "gamma"}
    old_blob, new_blob, first, old_marks, new_marks = build_blobs(old, new)

    assert {p for _o, p in old_marks} == {"a.md", "b.md", "c.md"}
    assert {p for _o, p in new_marks} == {"a.md", "b.md", "c.md"}
    assert len(old_marks) == 3, "a file got two sentinels or two share one (old)"
    assert len(new_marks) == 3, "a file got two sentinels or two share one (new)"
    assert first == "a.md"

    # marks in strictly increasing offset order (build appends left->right)
    assert [o for o, _p in old_marks] == sorted(o for o, _p in old_marks)
    assert [o for o, _p in new_marks] == sorted(o for o, _p in new_marks)

    # each recorded offset actually sits on a real sentinel in its blob
    for offset, _path in old_marks:
        assert _SEP_RE.match(old_blob[offset:]), "old mark offset isn't on a sentinel"
    for offset, _path in new_marks:
        assert _SEP_RE.match(new_blob[offset:]), "new mark offset isn't on a sentinel"


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
    and refines (identical inputs hit a trivial-trap and never split). After a
    real diff, every classified fragment must land in a real file — no orphans,
    no sentinel debris leaking into content. Proven through the LIVE path:
    build_blobs -> engine -> classify. If a fence got split across tokens, its
    char offset would drift and classify would misfile or emit debris."""
    old = {"a.md": "alpha one\nsecond line here", "b.md": "beta two\nmore text"}
    new = {"a.md": "alpha ONE\nsecond line here", "b.md": "beta two\nmore text"}

    old_blob, new_blob, first, old_marks, new_marks = build_blobs(old, new)
    blocks = BlockDiffEngine().compute_diff(old_blob, new_blob)
    removed, added, moved = classify(
        blocks, old_marks, new_marks, first, old, new)

    # Everything attributed must land in a file we actually put in.
    real_files = {"a.md", "b.md"}
    for r in removed:
        assert r.file_path in real_files, f"removed misfiled to {r.file_path!r}"
    for a in added:
        assert a.file_path in real_files, f"added misfiled to {a.file_path!r}"
    for m in moved:
        assert m.source_file in real_files and m.target_file in real_files, \
            "moved misfiled to a nonexistent file"

    # No raw fence bytes survived into any emitted content.
    for blk in list(removed) + list(added):
        assert "\ue000" not in blk.content, "sentinel debris leaked into content"
        assert "\ue003" not in blk.content, "sentinel debris leaked into content"
    for m in moved:
        assert "\ue000" not in m.content and "\ue003" not in m.content, \
            "sentinel debris leaked into moved content"

    # The actual edit (one -> ONE) must surface as a real change on a.md,
    # never swallowed, never smeared onto b.md.
    touched = ({r.file_path for r in removed}
               | {a.file_path for a in added}
               | {m.source_file for m in moved} | {m.target_file for m in moved})
    assert "a.md" in touched, "the a.md edit vanished during attribution"


def test_line_of_reports_minus_one_not_a_lie():
    """The OTHER silent liar. _line_of must return -1 for content that isn't
    present verbatim, rather than a plausible-but-wrong line number."""
    content = "line one\nline two\nline three"
    assert _line_of(content, "line two") == 2
    assert _line_of(content, "line one") == 1
    assert _line_of(content, "nonexistent fragment") == -1

def test_sentinels_are_the_fixed_spine_after_a_big_move():
    """The street-pole test. A big body moves between files. The sentinels are
    stationary BY CONSTRUCTION. After the engine runs, EVERY sentinel-bearing
    block must be fixed=True — the frame must not drift. If a sentinel comes back
    fixed=False (or absorbed/unlinked), the coordinate frame moved, which is the
    car-lurching-backward hallucination and the root of the whole-body-move bug."""
    body = ("first canonical statement of the thesis here\n"
            "third sentence with the crucial caveat that changes everything\n"
            "fifth sentence gesturing vaguely at all the future work")
    old = {"draft.md": f"# title\n\n{body}", "final.md": "# final\n\nplaceholder"}
    new = {"draft.md": "# title\n\n(moved to final)",
           "final.md": f"# final\n\nplaceholder\n\n{body}"}

    old_blob, new_blob, first, old_marks, new_marks = build_blobs(old, new)
    blocks = BlockDiffEngine().compute_diff(old_blob, new_blob)

    # Find every engine block whose text still carries a sentinel.
    sentinel_blocks = [b for b in blocks if _SEP_RE.search(b.text or "")]
    assert sentinel_blocks, "sentinels were absorbed/unlinked — frame dissolved"
    for b in sentinel_blocks:
        assert b.type == '=', f"a sentinel came back as {b.type!r}, not stationary"
        assert b.fixed is True, \
            f"sentinel drifted: fixed={b.fixed!r} — the frame moved (bus illusion)"

def test_anchor_stands_as_its_own_group():
    """Follow-up to the street-pole failure. The diagnostic showed the sentinel
    came back FUSED into a group with trailing content ('# final\\n\\nplaceholder').
    Confirm that structurally: no engine block that carries a sentinel may also
    carry non-sentinel payload. If this fails, the fix is in _get_groups (anchors
    must break the group chain). If it PASSES, the pole is standalone and the bug
    is purely in _find_max_path scoring — a different, smaller fix."""
    body = ("first canonical statement of the thesis here\n"
            "third sentence with the crucial caveat that changes everything\n"
            "fifth sentence gesturing vaguely at all the future work")
    old = {"draft.md": f"# title\n\n{body}", "final.md": "# final\n\nplaceholder"}
    new = {"draft.md": "# title\n\n(moved to final)",
           "final.md": f"# final\n\nplaceholder\n\n{body}"}

    old_blob, new_blob, first, old_marks, new_marks = build_blobs(old, new)
    blocks = BlockDiffEngine().compute_diff(old_blob, new_blob)

    for b in blocks:
        if _SEP_RE.search(b.text or ""):
            stripped = _SEP_RE.sub("", b.text).strip()
            assert stripped == "", (
                f"anchor FUSED with payload {stripped!r} — fix goes in _get_groups")
