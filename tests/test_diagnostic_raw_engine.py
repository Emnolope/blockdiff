# tests/test_diagnostic_raw_engine.py
#
# Not a pass/fail test. A MICROSCOPE. We stop trusting classify and look at
# what the engine ACTUALLY emits for the simplest possible cross-file move.
# Print every block's type, fixed flag, and text. This tells us whether the
# failure is (a) engine never marks the move fixed=False, or (b) engine marks
# it right but desentinel/classify drops it.

from blockdiff.match import build_blobs, desentinel, _SEP_RE
from blockdiff.cacycle import BlockDiffEngine


def test_dump_raw_engine_blocks_for_a_move(capsys):
    para = ("the quorum sensing threshold in bioluminescent vibrio\n"
            "collapses once autoinducer saturates the periplasm\n"
            "and the lux operon derepresses in a hard switch")
    old_files = {"a.md": f"alpha heading\n\n{para}\n\ntail of a",
                 "b.md": "beta heading\n\nunrelated body of b"}
    new_files = {"a.md": "alpha heading\n\ntail of a",
                 "b.md": f"beta heading\n\nunrelated body of b\n\n{para}"}

    old_blob, new_blob, sep_map, first = build_blobs(old_files, new_files)
    blocks = BlockDiffEngine().compute_diff(old_blob, new_blob)

    print("\n===== RAW ENGINE BLOCKS =====")
    for i, b in enumerate(blocks):
        # strip sentinels from the printed text so it's readable
        clean = _SEP_RE.sub("[SENTINEL]", b.text or "")
        clean = clean.replace("\n", "\\n")
        if len(clean) > 70:
            clean = clean[:70] + "..."
        print(f"[{i:2}] type={b.type!r} fixed={b.fixed!r} "
              f"old#={b.old_number} new#={b.new_number} group={b.group} "
              f"text={clean!r}")

    print("\n===== AFTER DESENTINEL =====")
    old_f, new_f = desentinel(blocks, sep_map, first)
    print("OLD fragments:")
    for f in old_f:
        print(f"  file={f.file_path} kind={f.kind!r} fixed={f.fixed!r} "
              f"content={f.content[:50]!r}")
    print("NEW fragments:")
    for f in new_f:
        print(f"  file={f.file_path} kind={f.kind!r} fixed={f.fixed!r} "
              f"content={f.content[:50]!r}")

    captured = capsys.readouterr()
    print(captured.out)  # force it into the -s output
    assert True
