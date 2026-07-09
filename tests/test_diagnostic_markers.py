# tests/test_diagnostic_markers.py
#
# The engine emits '|' move-markers and stamps color_id/moved_from_group on
# moved GROUPS. classify ignores all of it. Before we rewrite classify to READ
# the engine's real move verdict, dump the full group + marker structure so we
# build the fix on facts, not on my guess about cacycle's contract.

from blockdiff.match import build_blobs, _SEP_RE
from blockdiff.cacycle import BlockDiffEngine


def test_dump_groups_and_markers(capsys):
    para = ("the quorum sensing threshold in bioluminescent vibrio\n"
            "collapses once autoinducer saturates the periplasm\n"
            "and the lux operon derepresses in a hard switch")
    old_files = {"a.md": f"alpha heading\n\n{para}\n\ntail of a",
                 "b.md": "beta heading\n\nunrelated body of b"}
    new_files = {"a.md": "alpha heading\n\ntail of a",
                 "b.md": f"beta heading\n\nunrelated body of b\n\n{para}"}

    old_blob, new_blob, sep_map, first = build_blobs(old_files, new_files)
    engine = BlockDiffEngine()
    blocks = engine.compute_diff(old_blob, new_blob)

    print("\n===== BLOCKS (with group + marker fields) =====")
    for i, b in enumerate(blocks):
        clean = _SEP_RE.sub("[S]", b.text or "").replace("\n", "\\n")
        if len(clean) > 45:
            clean = clean[:45] + "..."
        print(f"[{i:2}] type={b.type!r} fixed={b.fixed!r} "
              f"old#={b.old_number} new#={b.new_number} "
              f"group={b.group} moved_to_group={b.moved_to_group} "
              f"text={clean!r}")

    print("\n===== GROUPS (the move verdict lives here) =====")
    for gi, g in enumerate(engine.groups):
        print(f"grp[{gi:2}] fixed={g.fixed!r} old#={g.old_number} "
              f"blocks={g.block_start}..{g.block_end} "
              f"color_id={g.color_id} moved_from_group={g.moved_from_group}")

    print(capsys.readouterr().out)
    assert True
