# tests/test_nightmare_e2e.py
#
# The happy-path e2e test proves the pipeline is wired. This file proves the
# pipeline is CORRECT under the exact conditions that ate 40 iterations. Every
# test here is a trap the naive version fell into. Full pipeline, no hand-fed
# fragments, no touching the engine internals. find_moves() in, verdict out.
#
# The design principle: a move is only trustworthy if the algorithm can tell
# TWO nearly-identical things apart while they BOTH fly across files. Anybody
# can track one unique paragraph. The test is tracking twins without swapping
# their identities.

from blockdiff.match import find_moves


def test_twin_paragraphs_cross_files_without_crossing_wires():
    """THE original sin. Two paragraphs that are 95% identical — differing by a
    single clause — both move to different files. The naive algorithm pairs the
    wrong source to the wrong target (criss-cross), producing phantom add+remove.
    The engine must keep each twin's identity intact across the move.

    twin_A ends '...before the frost took hold.'
    twin_B ends '...before the frost took everything.'
    A goes a.md -> c.md. B goes b.md -> d.md. They must NOT swap."""
    twin_a = ("the orchard on the north ridge yielded late that season\n"
              "every branch bent low with fruit no hand would pick\n"
              "and the whole slope went gold then brown\n"
              "before the frost took hold")
    twin_b = ("the orchard on the north ridge yielded late that season\n"
              "every branch bent low with fruit no hand would pick\n"
              "and the whole slope went gold then brown\n"
              "before the frost took everything")

    old_files = {
        "a.md": f"# journal one\n\n{twin_a}\n\nend of one",
        "b.md": f"# journal two\n\n{twin_b}\n\nend of two",
        "c.md": "# archive three\n\nempty for now",
        "d.md": "# archive four\n\nempty for now",
    }
    new_files = {
        "a.md": "# journal one\n\nend of one",
        "b.md": "# journal two\n\nend of two",
        "c.md": f"# archive three\n\nempty for now\n\n{twin_a}",
        "d.md": f"# archive four\n\nempty for now\n\n{twin_b}",
    }

    removed, added, moved = find_moves(old_files, new_files)

    # Find where each twin ended up. The tell is the last clause.
    a_move = [m for m in moved if "frost took hold" in m.content]
    b_move = [m for m in moved if "frost took everything" in m.content]

    # Each twin must be tracked, and to the RIGHT destination — no wire cross.
    assert len(a_move) >= 1, f"twin_A lost. moved={[(m.source_file, m.target_file) for m in moved]}"
    assert len(b_move) >= 1, f"twin_B lost. moved={[(m.source_file, m.target_file) for m in moved]}"
    assert a_move[0].source_file == "a.md" and a_move[0].target_file == "c.md", \
        f"twin_A criss-crossed: {a_move[0].source_file}->{a_move[0].target_file}"
    assert b_move[0].source_file == "b.md" and b_move[0].target_file == "d.md", \
        f"twin_B criss-crossed: {b_move[0].source_file}->{b_move[0].target_file}"


def test_triplet_where_one_stays_and_two_scatter():
    """Three near-identical blocks. One does NOT move (stays in its file). Two
    move to different files. The stationary one must NOT be reported as a move,
    and the two movers must not steal its identity or each other's.

    This is the ambiguity gauntlet: when content is a triplet, _sole_home
    refuses to pair the ambiguous ones. So the HONEST outcome is that the ones
    it can't disambiguate fall through to add/remove rather than being guessed.
    We assert the tool does NOT lie — it either tracks them correctly or admits
    defeat as add/remove. What it must NEVER do is invent a confident wrong move."""
    base = ("the signal repeats on a seven second cycle\n"
            "each pulse louder than the last until it clips")
    trip_1 = base + "\nvariant one marker alpha"
    trip_2 = base + "\nvariant two marker beta"
    trip_3 = base + "\nvariant three marker gamma"

    old_files = {
        "src1.md": f"header\n\n{trip_1}\n\nfooter",
        "src2.md": f"header\n\n{trip_2}\n\nfooter",
        "src3.md": f"header\n\n{trip_3}\n\nfooter",
    }
    new_files = {
        "src1.md": f"header\n\n{trip_1}\n\nfooter",          # trip_1 STAYS
        "src2.md": "header\n\nfooter",                        # trip_2 left
        "src3.md": "header\n\nfooter",                        # trip_3 left
        "dst_x.md": f"landing\n\n{trip_2}",                   # trip_2 arrives
        "dst_y.md": f"landing\n\n{trip_3}",                   # trip_3 arrives
    }

    removed, added, moved = find_moves(old_files, new_files)

    # trip_1 stayed put: it must appear in NEITHER moved, removed, nor added.
    assert not any("variant one marker alpha" in m.content for m in moved), \
        "stationary triplet member was reported as a move"
    assert not any("variant one marker alpha" in r.content for r in removed), \
        "stationary triplet member was reported as removed"
    assert not any("variant one marker alpha" in a.content for a in added), \
        "stationary triplet member was reported as added"

    # trip_2 and trip_3 moved. The unique marker lines make them disambiguable,
    # so an HONEST tool tracks them to the right place. If it can't, they must
    # fall through as add+remove — never as a confidently WRONG move.
    for marker, src, dst in [("variant two marker beta", "src2.md", "dst_x.md"),
                             ("variant three marker gamma", "src3.md", "dst_y.md")]:
        as_move = [m for m in moved if marker in m.content]
        if as_move:
            assert as_move[0].source_file == src and as_move[0].target_file == dst, \
                f"{marker!r} moved to WRONG place: {as_move[0].source_file}->{as_move[0].target_file}"
        else:
            # Fell through honestly. Must be BOTH a remove (from src) and add (to dst).
            assert any(marker in r.content and r.file_path == src for r in removed), \
                f"{marker!r} vanished — not a move AND not removed from {src}"
            assert any(marker in a.content and a.file_path == dst for a in added), \
                f"{marker!r} vanished — not a move AND not added to {dst}"


def test_move_with_simultaneous_edit_and_genuine_deletion_in_same_blob():
    """The realistic churn case. In one commit: a paragraph MOVES a->c, a
    DIFFERENT paragraph is genuinely DELETED from b (gone, no home), a NEW
    paragraph is genuinely ADDED to c, AND a paragraph is EDITED in place in d.
    All four events share one blob. The move must not absorb the delete or the
    add, and the in-place edit must not masquerade as a move.

    This is where a naive matcher smears: the deleted content and the moved
    content are both '-' on the old side; the added and the moved are both '+'
    on the new side. Only the engine's fixed=False verdict separates them."""
    mover = ("the cartographer refused to draw the eastern coast\n"
             "claiming no ship had returned to confirm its shape\n"
             "so the map simply ended in blank vellum")
    doomed = ("this paragraph is deleted outright and has no destination\n"
              "it should appear in removed and nowhere else")
    newborn = ("this paragraph is born in this commit with no prior existence\n"
               "it should appear in added and nowhere else")

    old_files = {
        "a.md": f"# alpha\n\n{mover}\n\nalpha tail",
        "b.md": f"# beta\n\n{doomed}\n\nbeta tail",
        "c.md": "# gamma\n\ngamma body",
        "d.md": "# delta\n\nthe value was seventeen at last count",
    }
    new_files = {
        "a.md": "# alpha\n\nalpha tail",                       # mover left
        "b.md": "# beta\n\nbeta tail",                         # doomed deleted
        "c.md": f"# gamma\n\ngamma body\n\n{mover}\n\n{newborn}",  # mover arrives + newborn
        "d.md": "# delta\n\nthe value was ninety-nine at last count",  # in-place edit
    }

    removed, added, moved = find_moves(old_files, new_files)

    # The mover: exactly one move a.md -> c.md.
    mover_moves = [m for m in moved if "cartographer refused" in m.content]
    assert len(mover_moves) >= 1, "mover not detected as a move"
    assert mover_moves[0].source_file == "a.md" and mover_moves[0].target_file == "c.md", \
        f"mover went wrong way: {mover_moves[0].source_file}->{mover_moves[0].target_file}"
    # And the mover did NOT double-count into removed/added.
    assert not any("cartographer refused" in r.content for r in removed), "mover leaked into removed"
    assert not any("cartographer refused" in a.content for a in added), "mover leaked into added"

    # The doomed paragraph: removed from b.md, never a move, never added.
    assert any("deleted outright" in r.content and r.file_path == "b.md" for r in removed), \
        "genuine deletion was not reported as removed from b.md"
    assert not any("deleted outright" in m.content for m in moved), "deletion masqueraded as a move"
    assert not any("deleted outright" in a.content for a in added), "deletion leaked into added"

    # The newborn: added to c.md, never a move, never removed.
    assert any("born in this commit" in a.content and a.file_path == "c.md" for a in added), \
        "genuine addition was not reported as added to c.md"
    assert not any("born in this commit" in m.content for m in moved), "addition masqueraded as a move"
    assert not any("born in this commit" in r.content for r in removed), "addition leaked into removed"

    # The in-place edit in d.md must NOT be a cross-file move. Whatever the
    # engine does with 'seventeen'->'ninety-nine', it stays in d.md.
    assert not any(m.source_file == "d.md" or m.target_file == "d.md" for m in moved), \
        "in-place edit was reported as a cross-file move involving d.md"


def test_whole_file_content_relocated_and_original_emptied():
    """A file is gutted and its ENTIRE body reappears in another file, while the
    original file keeps existing as a near-empty husk. This tests that 'move'
    survives even when the source file doesn't vanish (so parse.py's rename
    detection can't fire — the file still exists, just emptied). The content-
    level move is the only thing that can catch this."""
    body = ("first canonical statement of the thesis\n"
            "second sentence developing the thesis\n"
            "third sentence with the crucial caveat that changes everything\n"
            "fourth sentence resolving the tension\n"
            "fifth sentence gesturing at future work")

    old_files = {
        "draft.md": f"# working title\n\n{body}",
        "final.md": "# final\n\nplaceholder",
    }
    new_files = {
        "draft.md": "# working title\n\n(moved to final)",
        "final.md": f"# final\n\nplaceholder\n\n{body}",
    }

    removed, added, moved = find_moves(old_files, new_files)

    moved_body = [m for m in moved if "crucial caveat" in m.content]
    assert len(moved_body) >= 1, (
        f"whole-body relocation not detected. "
        f"moved={[(m.source_file, m.target_file) for m in moved]}")
    assert moved_body[0].source_file == "draft.md" and moved_body[0].target_file == "final.md", \
        f"body relocation wrong direction: {moved_body[0].source_file}->{moved_body[0].target_file}"


def test_reordered_blocks_within_and_across_files_do_not_all_scream_move():
    """Four distinct paragraphs. In the new state they are REORDERED (P3, P1,
    P4, P2) and P2 additionally crosses into another file. Reordering within a
    file is the engine's home turf — it should recognize the reorder without
    reporting every paragraph as a cross-file move. Only P2's file-crossing is
    a real cross-file move. This guards against the tool being trigger-happy:
    a shuffle is not a diaspora."""
    p1 = "paragraph one about the tides and their lunar dependence stated plainly"
    p2 = "paragraph two about sediment transport along the barrier islands"
    p3 = "paragraph three about the salt marsh as a carbon sink over centuries"
    p4 = "paragraph four about storm surge return intervals and their variance"

    old_files = {
        "notes.md": f"{p1}\n\n{p2}\n\n{p3}\n\n{p4}",
        "sink.md": "# sink\n\nnothing here yet",
    }
    new_files = {
        "notes.md": f"{p3}\n\n{p1}\n\n{p4}",           # reordered, p2 gone
        "sink.md": f"# sink\n\nnothing here yet\n\n{p2}",  # p2 landed here
    }

    removed, added, moved = find_moves(old_files, new_files)

    # P2 crossed files: it's the ONLY legitimate cross-file move here.
    p2_moves = [m for m in moved if "sediment transport" in m.content]
    assert len(p2_moves) >= 1, "p2 cross-file move not detected"
    assert p2_moves[0].source_file == "notes.md" and p2_moves[0].target_file == "sink.md", \
        f"p2 wrong: {p2_moves[0].source_file}->{p2_moves[0].target_file}"

    # P1, P3, P4 stayed in notes.md (just reordered). They must NOT be reported
    # as CROSS-FILE moves — a within-file shuffle has source==target, which
    # _proven_moves already refuses. So none of them cross into sink.md.
    for marker in ["tides and their lunar", "salt marsh as a carbon",
                   "storm surge return"]:
        cross = [m for m in moved if marker in m.content
                 and m.source_file != m.target_file]
        assert not cross, \
            f"within-file reorder {marker!r} was reported as a cross-file move"
