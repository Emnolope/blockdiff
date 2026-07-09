# tests/test_move_e2e.py
#
# The test everything else was avoiding. Not "does classify recover a move from
# a hand-fed fixed=False fragment" — that's already green. This one asks the
# ONLY question that matters: when a real paragraph jumps from file A to file B,
# and we blob+sentinel+diff it for real through the engine, does it come out the
# OTHER end as a move? If this fails, every green test above is paint on a car
# with no engine.

from blockdiff.match import find_moves


def test_paragraph_moved_between_files_is_detected_end_to_end():
    """A distinctive multi-line paragraph lives in a.md in the OLD state and in
    b.md in the NEW state. Nothing hand-fed. Full pipeline: build_blobs ->
    engine.compute_diff -> desentinel -> classify. It MUST surface as a move."""
    para = ("the quorum sensing threshold in bioluminescent vibrio\n"
            "collapses once autoinducer saturates the periplasm\n"
            "and the lux operon derepresses in a hard switch")

    old_files = {
        "a.md": f"alpha heading\n\n{para}\n\ntail of a",
        "b.md": "beta heading\n\nunrelated body of b",
    }
    new_files = {
        "a.md": "alpha heading\n\ntail of a",
        "b.md": f"beta heading\n\nunrelated body of b\n\n{para}",
    }

    removed, added, moved = find_moves(old_files, new_files)

    # The paragraph must be reported as ONE move, a.md -> b.md.
    assert any(m.source_file == "a.md" and m.target_file == "b.md"
               and "quorum sensing threshold" in m.content
               for m in moved), (
        f"cross-file move NOT detected end-to-end. "
        f"moved={[(m.source_file, m.target_file) for m in moved]} "
        f"removed={[r.file_path for r in removed]} "
        f"added={[a.file_path for a in added]}")

    # And it must NOT also appear as a phantom delete+add.
    assert not any("quorum sensing threshold" in r.content for r in removed), \
        "moved paragraph ALSO leaked into removed — double-counted"
    assert not any("quorum sensing threshold" in a.content for a in added), \
        "moved paragraph ALSO leaked into added — double-counted"


def test_sentinel_adjacent_to_edit_does_not_leak():
    """#2 from the audit, as a test. Put an edit RIGHT against a file boundary
    so the engine is forced to tokenize and refine across the sentinel fence.
    If a private-use fence char survives into reported content, the 'one token'
    claim is false and attribution is corrupting output."""
    old_files = {"a.md": "first line edited here", "b.md": "second file body"}
    new_files = {"a.md": "first line changed there", "b.md": "second file body"}

    removed, added, moved = find_moves(old_files, new_files)

    for block in removed + added:
        assert "\ue000" not in block.content
        assert "\ue001" not in block.content
        assert "\ue002" not in block.content
        assert "\ue003" not in block.content
        assert "\ue004" not in block.content
        assert "\ue005" not in block.content
    for m in moved:
        assert "\ue000" not in m.content
        assert "\ue003" not in m.content
