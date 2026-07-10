# tests/test_spec.py
#
# The spec IS the microscope, and it's stateless. No artifact, no doc, no
# conftest. Each test PRINTS the engine's real behavior with plain print(), and
# the `-rA` flag in pyproject.toml surfaces that captured output in the pytest
# report — for passes AND failures — so the next AI runs bare `pytest` and reads
# the whole reality off the terminal. Nothing is written to disk. The proof
# regenerates from the raw repo every run and vanishes when the code changes.
#
# THE BUG the prints will show you: a cross-file move is TWO-ended. The engine
# emits the moved CONTENT as a '=' block with fixed=TRUE at the destination,
# plus a '|' marker at the origin. _proven_moves keeps only fixed=FALSE '='
# blocks, so it drops the move -> moved/removed/added all empty. The fix:
# _proven_moves must WALK THE '|' MARKERS, not read the `fixed` flag.

from blockdiff.match import build_blobs, desentinel, _SEP_RE, find_moves
from blockdiff.cacycle import BlockDiffEngine


def _dump(old_files, new_files):
    """Print the engine's live guts: every block with its fixed flag and marker
    linkage, the group table where the move verdict lives, and what desentinel
    hands classify. Plain prints — `-rA` decides whether they surface. Writes
    nothing, stores nothing, regenerated fresh each call from the inputs."""
    old_blob, new_blob, sep_map, first = build_blobs(old_files, new_files)
    engine = BlockDiffEngine()
    blocks = engine.compute_diff(old_blob, new_blob)

    print("\n--- ENGINE BLOCKS (fixed flag + marker linkage) ---")
    for i, b in enumerate(blocks):
        clean = _SEP_RE.sub("[S]", b.text or "").replace("\n", "\\n")
        if len(clean) > 50:
            clean = clean[:50] + "..."
        print(f"[{i:2}] type={b.type!r:4} fixed={str(b.fixed):5} "
              f"old#={str(b.old_number):>4} new#={str(b.new_number):>4} "
              f"grp={str(b.group):>3} mv_to_grp={str(b.moved_to_group):>4} "
              f"text={clean!r}")

    print("--- GROUPS (the move verdict lives here) ---")
    for gi, g in enumerate(engine.groups):
        print(f"grp[{gi}] fixed={g.fixed} color_id={g.color_id} "
              f"moved_from_group={g.moved_from_group} "
              f"blocks={g.block_start}..{g.block_end}")

    print("--- WHAT classify() RECEIVES ---")
    old_f, new_f = desentinel(blocks, sep_map, first)
    for label, frags in [("OLD", old_f), ("NEW", new_f)]:
        for f in frags:
            print(f"{label} file={f.file_path:8} kind={f.kind!r} "
                  f"fixed={str(f.fixed):5} content={f.content[:40]!r}")

    print("--- THE BUG: moved content is fixed=True; _proven_moves keeps only")
    print("    fixed=False, so it drops it. Fix: walk the '|' markers. ---")


def test_single_cross_file_move_is_detected():
    """One distinctive paragraph, a.md -> b.md, full pipeline."""
    para = ("the quorum sensing threshold in bioluminescent vibrio\n"
            "collapses once autoinducer saturates the periplasm\n"
            "and the lux operon derepresses in a hard switch")
    old_files = {"a.md": f"alpha heading\n\n{para}\n\ntail of a",
                 "b.md": "beta heading\n\nunrelated body of b"}
    new_files = {"a.md": "alpha heading\n\ntail of a",
                 "b.md": f"beta heading\n\nunrelated body of b\n\n{para}"}

    _dump(old_files, new_files)
    removed, added, moved = find_moves(old_files, new_files)
    print(f"RESULT moved={[(m.source_file, m.target_file) for m in moved]} "
          f"removed={[r.file_path for r in removed]} "
          f"added={[a.file_path for a in added]}")

    assert any(m.source_file == "a.md" and m.target_file == "b.md"
               and "quorum sensing threshold" in m.content for m in moved), \
        "cross-file move NOT detected (see printed ENGINE BLOCKS above)"
    assert not any("quorum sensing threshold" in r.content for r in removed), \
        "moved content double-counted into removed"
    assert not any("quorum sensing threshold" in a.content for a in added), \
        "moved content double-counted into added"


def test_twins_move_without_crossing_wires():
    """Two 95%-identical paragraphs move to different files. The printed dump
    shows whether the engine gives each twin its own marker or collapses the
    shared prefix into one ambiguous group — the thing that decides trackability."""
    twin_a = ("the orchard on the north ridge yielded late that season\n"
              "every branch bent low with fruit no hand would pick\n"
              "before the frost took hold")
    twin_b = ("the orchard on the north ridge yielded late that season\n"
              "every branch bent low with fruit no hand would pick\n"
              "before the frost took everything")
    old_files = {"a.md": f"# one\n\n{twin_a}\n\nend one",
                 "b.md": f"# two\n\n{twin_b}\n\nend two",
                 "c.md": "# three\n\nempty", "d.md": "# four\n\nempty"}
    new_files = {"a.md": "# one\n\nend one", "b.md": "# two\n\nend two",
                 "c.md": f"# three\n\nempty\n\n{twin_a}",
                 "d.md": f"# four\n\nempty\n\n{twin_b}"}

    _dump(old_files, new_files)
    removed, added, moved = find_moves(old_files, new_files)
    print(f"RESULT moved={[(m.source_file, m.target_file, m.content[:25]) for m in moved]}")

    for tag in ["frost took hold", "frost took everything"]:
        seen = (any(tag in m.content for m in moved)
                or any(tag in r.content for r in removed)
                or any(tag in a.content for a in added))
        assert seen, f"twin {tag!r} vanished entirely (see dump above)"
    for m in [m for m in moved if "frost took hold" in m.content]:
        assert not (m.source_file == "b.md" or m.target_file == "d.md"), \
            "twin_a cross-wired into twin_b's route (see dump above)"
    for m in [m for m in moved if "frost took everything" in m.content]:
        assert not (m.source_file == "a.md" or m.target_file == "c.md"), \
            "twin_b cross-wired into twin_a's route (see dump above)"


def test_move_does_not_absorb_a_real_deletion():
    """A move (a->c) and a genuine deletion (from b) share one blob. The delete
    must land in removed, not get swallowed by the move."""
    mover = ("the cartographer refused to draw the eastern coast\n"
             "so the map simply ended in blank vellum")
    doomed = ("this paragraph is deleted outright with no destination\n"
              "it belongs in removed and nowhere else")
    old_files = {"a.md": f"# a\n\n{mover}\n\na tail",
                 "b.md": f"# b\n\n{doomed}\n\nb tail", "c.md": "# c\n\nc body"}
    new_files = {"a.md": "# a\n\na tail", "b.md": "# b\n\nb tail",
                 "c.md": f"# c\n\nc body\n\n{mover}"}

    _dump(old_files, new_files)
    removed, added, moved = find_moves(old_files, new_files)
    print(f"RESULT moved={[(m.source_file, m.target_file) for m in moved]} "
          f"removed={[r.file_path for r in removed]}")

    assert any("cartographer refused" in m.content and m.source_file == "a.md"
               and m.target_file == "c.md" for m in moved), \
        "mover not detected as a move (see dump above)"
    assert any("deleted outright" in r.content and r.file_path == "b.md"
               for r in removed), "genuine deletion swallowed (see dump above)"
    assert not any("deleted outright" in m.content for m in moved), \
        "deletion masqueraded as a move (see dump above)"


def test_whole_body_relocation_when_source_file_survives():
    """A file's whole body moves out while the file survives emptied. Rename
    detection can't fire; only a content-level move catches it."""
    body = ("first canonical statement of the thesis\n"
            "third sentence with the crucial caveat that changes everything\n"
            "fifth sentence gesturing at future work")
    old_files = {"draft.md": f"# title\n\n{body}", "final.md": "# final\n\nplaceholder"}
    new_files = {"draft.md": "# title\n\n(moved to final)",
                 "final.md": f"# final\n\nplaceholder\n\n{body}"}

    _dump(old_files, new_files)
    removed, added, moved = find_moves(old_files, new_files)
    print(f"RESULT moved={[(m.source_file, m.target_file) for m in moved]}")

    assert any("crucial caveat" in m.content and m.source_file == "draft.md"
               and m.target_file == "final.md" for m in moved), \
        "whole-body relocation missed (see dump above)"
