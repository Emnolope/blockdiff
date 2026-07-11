# tests/test_classify.py
#
# classify() does attribution, not judgment. It reads each engine block's TWO
# CHARACTER addresses (old_char, new_char), asks which sentinel sits below each,
# and turns that into moved/removed/added. Identity is the block's character
# offset — a distinct integer per block — so byte-identical content in different
# places stays distinct BY CONSTRUCTION.
#
# History this file must never repeat: a prior version mocked pre-tagged
# fragments and pinned a FALSE contract (fixed=False => move). Wrong twice — the
# engine files moved content as fixed=True, and the real signal is "old-address
# file != new-address file", never a flag. So we drive the REAL engine through
# tiny blobs; attribution can no longer drift from engine reality.

from blockdiff.match import find_moves


def test_cross_file_move_is_recovered_and_not_double_counted():
    """A unique line leaves a.md and appears in b.md. Its '=' block's old_char
    sits behind a.md's sentinel and its new_char behind b.md's -> one move, in
    neither removed nor added."""
    line = "the singular quorum sensing anchor line stands entirely alone here"
    old = {"a.md": f"alpha head\n\n{line}\n\nalpha tail",
           "b.md": "beta head\n\nbeta body"}
    new = {"a.md": "alpha head\n\nalpha tail",
           "b.md": f"beta head\n\nbeta body\n\n{line}"}

    removed, added, moved = find_moves(old, new)

    assert any(m.source_file == "a.md" and m.target_file == "b.md"
               and "quorum sensing anchor" in m.content for m in moved), \
        "cross-file move not detected"
    assert not any("quorum sensing anchor" in r.content for r in removed), \
        "moved content double-counted into removed"
    assert not any("quorum sensing anchor" in a.content for a in added), \
        "moved content double-counted into added"


def test_stationary_content_is_reported_in_nothing():
    """Content whose two addresses sit behind the SAME sentinel never moved."""
    old = {"a.md": "stable head\n\nstable body stays right here\n\nstable tail"}
    new = {"a.md": "stable head\n\nstable body stays right here\n\nstable tail"}

    removed, added, moved = find_moves(old, new)

    assert moved == []
    assert removed == []
    assert added == []


def test_plain_delete_is_removed_at_its_old_file():
    """Content with only an old address is a delete, filed at its old file."""
    old = {"doc.md": "keep this line\n\nthis whole paragraph is deleted outright now"}
    new = {"doc.md": "keep this line"}

    removed, added, moved = find_moves(old, new)

    assert any("deleted outright" in r.content and r.file_path == "doc.md"
               for r in removed), "genuine deletion not reported as removed"
    assert not any("deleted outright" in m.content for m in moved), \
        "deletion masqueraded as a move"


def test_plain_add_is_added_at_its_new_file():
    """Content with only a new address is an add, filed at its new file."""
    old = {"doc.md": "existing line"}
    new = {"doc.md": "existing line\n\nthis paragraph is entirely brand new content"}

    removed, added, moved = find_moves(old, new)

    assert any("brand new content" in a.content and a.file_path == "doc.md"
               for a in added), "genuine addition not reported as added"
    assert not any("brand new content" in m.content for m in moved), \
        "addition masqueraded as a move"


def test_twins_to_different_files_do_not_cross_wire():
    """Two near-identical paragraphs leave a.md and b.md for c.md and d.md. Each
    is a DISTINCT block at a DISTINCT offset, so identity can't alias though the
    fillings taste the same. Each twin accounted for, none on the wrong route."""
    twin_a = ("the orchard on the north ridge yielded late that season\n"
              "every branch bent low before the frost took hold")
    twin_b = ("the orchard on the north ridge yielded late that season\n"
              "every branch bent low before the frost took everything")
    old = {"a.md": f"# one\n\n{twin_a}\n\nend one",
           "b.md": f"# two\n\n{twin_b}\n\nend two",
           "c.md": "# three\n\nempty", "d.md": "# four\n\nempty"}
    new = {"a.md": "# one\n\nend one", "b.md": "# two\n\nend two",
           "c.md": f"# three\n\nempty\n\n{twin_a}",
           "d.md": f"# four\n\nempty\n\n{twin_b}"}

    removed, added, moved = find_moves(old, new)

    for tag in ["frost took hold", "frost took everything"]:
        seen = (any(tag in m.content for m in moved)
                or any(tag in r.content for r in removed)
                or any(tag in a.content for a in added))
        assert seen, f"twin {tag!r} vanished entirely"
    for m in moved:
        if "frost took hold" in m.content:
            assert not (m.source_file == "b.md" or m.target_file == "d.md"), \
                "twin_a cross-wired into twin_b's route"
        if "frost took everything" in m.content:
            assert not (m.source_file == "a.md" or m.target_file == "c.md"), \
                "twin_b cross-wired into twin_a's route"


def test_twin_straddling_one_sentinel_attributes_to_two_files():
    """THE canary — the exact case that killed content-identity. The SAME
    paragraph ends file A and begins file B, so in a naive read the two copies
    look identical and merge. Here P sits at a.md's tail in old and b.md's head
    in new-adjacent files. Character offsets place each copy on its own side of
    the sentinel, so P must be attributed to the correct distinct files, never
    aliased into one."""
    p = "this exact paragraph appears at a boundary and must not be aliased"
    old = {"a.md": f"alpha intro\n\n{p}", "b.md": "beta intro only"}
    new = {"a.md": "alpha intro only", "b.md": f"{p}\n\nbeta intro only"}

    removed, added, moved = find_moves(old, new)

    # P left a.md and entered b.md: one clean move a -> b, no alias, no phantom.
    assert any("must not be aliased" in m.content and m.source_file == "a.md"
               and m.target_file == "b.md" for m in moved), \
        "straddling twin was not attributed to two distinct files"
    assert not any("must not be aliased" in r.content for r in removed)
    assert not any("must not be aliased" in a.content for a in added)


def test_move_and_genuine_deletion_in_one_commit_do_not_smear():
    """A move (a->c) and a real deletion (from b) share one blob. The delete has
    only an old address; the mover has two addresses behind different sentinels.
    Neither absorbs the other."""
    mover = "the cartographer refused to draw the entire eastern coastline at all"
    doomed = "this paragraph is deleted outright and has no destination anywhere here"
    old = {"a.md": f"# a\n\n{mover}\n\na tail",
           "b.md": f"# b\n\n{doomed}\n\nb tail", "c.md": "# c\n\nc body"}
    new = {"a.md": "# a\n\na tail", "b.md": "# b\n\nb tail",
           "c.md": f"# c\n\nc body\n\n{mover}"}

    removed, added, moved = find_moves(old, new)

    assert any("cartographer refused" in m.content and m.source_file == "a.md"
               and m.target_file == "c.md" for m in moved), "mover not a move"
    assert any("deleted outright" in r.content and r.file_path == "b.md"
               for r in removed), "genuine deletion swallowed"
    assert not any("deleted outright" in m.content for m in moved), \
        "deletion masqueraded as a move"


def test_empty_input_is_empty_output():
    removed, added, moved = find_moves({}, {})
    assert removed == [] and added == [] and moved == []

def test_whole_body_relocation_when_source_file_survives():
    """A file's whole body moves out while the file survives (emptied to a
    stub). Rename detection can't fire — draft.md still exists — so only a
    content-level move catches it. Ported from the retired test_spec.py; the
    one intent that file had which nothing else covered."""
    body = ("first canonical statement of the thesis here\n"
            "third sentence with the crucial caveat that changes everything\n"
            "fifth sentence gesturing vaguely at all the future work")
    old = {"draft.md": f"# title\n\n{body}",
           "final.md": "# final\n\nplaceholder"}
    new = {"draft.md": "# title\n\n(moved to final)",
           "final.md": f"# final\n\nplaceholder\n\n{body}"}

    removed, added, moved = find_moves(old, new)

    assert any("crucial caveat" in m.content and m.source_file == "draft.md"
               and m.target_file == "final.md" for m in moved), \
        "whole-body relocation missed"
    assert not any("crucial caveat" in r.content for r in removed), \
        "relocated body double-counted into removed"

def test_cross_file_move_reported_even_when_engine_marks_it_fixed():
    """REGRESSION LOCK — the tombstoned bug, nailed shut on purpose.

    The engine's `fixed` flag marks the stationary ENERGY FRAME (the
    max-keystroke-saving spine), NOT file-stationarity. A block can sit ON that
    spine (fixed=True) and STILL have its two ends behind different sentinels —
    i.e. it changed files. The witness scaffold MEASURED exactly this: a mover
    with fixed=True, old end in a.md, new end in b.md.

    A prior classify() keyed the '=' branch on b.fixed and dropped every such
    move into the void — not moved, not removed, not added. Content vanished
    with no error. This test drives the real engine, asserts the move IS
    reported, AND asserts the premise (the mover really does come back fixed=True
    at engine level) so that if some future change makes the engine flip it to
    fixed=False, this test's premise-check fires and tells us the world changed
    underneath us rather than silently passing for the wrong reason.

    If this ever fails, someone re-added a `if b.fixed: continue` gate to the
    '=' branch of classify(). Do not. The sentinel crossing is the move signal.
    """
    from blockdiff.match import build_blobs, _file_owning, classify
    from blockdiff.cacycle import BlockDiffEngine

    line = "the singular quorum sensing anchor line stands entirely alone here"
    old = {"a.md": f"alpha head\n\n{line}\n\nalpha tail",
           "b.md": "beta head\n\nbeta body"}
    new = {"a.md": "alpha head\n\nalpha tail",
           "b.md": f"beta head\n\nbeta body\n\n{line}"}

    # --- premise check: the engine really does crown this mover fixed=True ---
    old_blob, new_blob, first, old_marks, new_marks, prelinks = build_blobs(old, new)
    blocks = BlockDiffEngine().compute_diff(old_blob, new_blob, prelinks=prelinks)
    mover = next((b for b in blocks
                  if b.type == '=' and "quorum sensing" in (b.text or "")), None)
    assert mover is not None, \
        "premise gone: no single '=' block carries the moved line anymore"
    src = _file_owning(mover.old_char, old_marks, first)
    dst = _file_owning(mover.new_char, new_marks, first)
    assert src == "a.md" and dst == "b.md", \
        f"premise gone: mover no longer crosses a.md->b.md (src={src} dst={dst})"
    assert mover.fixed is True, (
        "PREMISE CHANGED: the engine no longer marks this mover fixed=True. "
        "The regression this test guards may now be unreachable via this fixture "
        "— re-derive a fixture that reproduces a fixed=True file-crosser, or the "
        "guard has gone slack.")

    # --- the actual guarantee: fixed=True notwithstanding, it IS a move ---
    removed, added, moved = classify(
        blocks, old_marks, new_marks, first, old, new)

    assert any("quorum sensing" in m.content
               and m.source_file == "a.md" and m.target_file == "b.md"
               for m in moved), \
        "fixed=True mover was dropped — someone re-added a b.fixed gate to classify"
    assert not any("quorum sensing" in r.content for r in removed), \
        "fixed=True mover leaked into removed (double-count)"
    assert not any("quorum sensing" in a.content for a in added), \
        "fixed=True mover leaked into added (double-count)"
