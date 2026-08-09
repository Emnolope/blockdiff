# tests/test_cli_files.py
#
# The --files flag was historically untested. Two distinct paths were passed
# straight through _collect, which then dropped them into build_blobs with
# DIFFERENT keys on the old vs new side. build_blobs assumes every path
# appears in BOTH dicts under the SAME key; violating that produced phantom
# sentinel slots, garbage attribution, and bogus "cross-file moves" of
# stationary text. This file pins the contract: --files diffs ONE logical
# file, not two; the resulting labels must be coherent.

import os
import subprocess
import sys
import tempfile
import textwrap

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _run_blockdiff(args, cwd):
    """Invoke the installed `blockdiff` console script with the given args,
    using cwd as CWD. Returns CompletedProcess."""
    return subprocess.run(
        [sys.executable, "-m", "blockdiff.cli", *args],
        cwd=cwd, capture_output=True, text=True,
    )


def test_files_two_distinct_paths_diff_as_one_logical_file():
    """--files OLD NEW with distinct paths must produce a single coherent
    file label (the OLD path), no phantom cross-file moves, and real
    removed/added content filed at sensible lines."""
    with tempfile.TemporaryDirectory() as d:
        old = os.path.join(d, "before.md")
        new = os.path.join(d, "after.md")
        with open(old, "w") as f:
            f.write(textwrap.dedent("""\
                # Title

                This is the intro paragraph that stays.

                AAAA old line one
                AAAA old line two
                AAAA old line three

                Common middle paragraph.

                Common ending paragraph.
                """))
        with open(new, "w") as f:
            f.write(textwrap.dedent("""\
                # Title

                This is the intro paragraph that stays.

                Common middle paragraph.

                Common ending paragraph.

                AAAA new line one
                AAAA new line two
                AAAA new line three
                """))

        proc = _run_blockdiff(["--files", old, new, "--json"], cwd=REPO_ROOT)
        assert proc.returncode == 0, proc.stderr

        import json
        data = json.loads(proc.stdout)

        # Every entry's file/from_file/to_file must be the OLD path. The new
        # path is just where we read the second version from; the engine must
        # not promote it to a co-equal peer (that was the old bug).
        for kind, key in [("removed", "file"),
                          ("added", "file"),
                          ("moved", "from_file"),
                          ("moved", "to_file")]:
            for entry in data[kind]:
                assert entry[key] == old, (
                    f"{kind}[{key}] = {entry[key]!r} but must be {old!r} "
                    f"(the --files OLD path); got: {entry}"
                )

        # The "AAAA old" content really was removed. It should appear in
        # `removed`, not in `moved` (which would mean the engine thought
        # it relocated within the same file).
        assert any("AAAA old" in r["content"] for r in data["removed"]), \
            f"AAAA old line(s) should be reported as removed; got: {data['removed']}"

        # No phantom +'s: --files shouldn't produce "added" entries for
        # content that didn't actually appear in the new file.
        for a in data["added"]:
            assert a["line_start"] != -1, (
                f"added entry has line_start=-1 (phantom slot from build_blobs "
                f"mislabeling): {a}"
            )


def test_files_identical_paths_report_no_differences():
    """Passing the same path twice is the degenerate --files case. Should
    produce a clean "no differences" — no removed/added/moved, no errors."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "same.md")
        with open(p, "w") as f:
            f.write("# Title\n\nunchanged content\n")
        proc = _run_blockdiff(["--files", p, p, "--json"], cwd=REPO_ROOT)
        assert proc.returncode == 0, proc.stderr
        import json
        data = json.loads(proc.stdout)
        assert data["removed"] == []
        assert data["added"] == []
        assert data["moved"] == []
        assert data["renamed"] == []


def test_files_plain_deletion_is_removed_not_moved():
    """--files BUGFIX: previously a plain AAAA-old->empty diff would
    produce a 'moved' block with line_start=-1 on both sides because the
    new content was attributed to a phantom slot. After the fix it must
    come out as a normal removed entry."""
    with tempfile.TemporaryDirectory() as d:
        old = os.path.join(d, "v1.md")
        new = os.path.join(d, "v2.md")
        with open(old, "w") as f:
            f.write("keep this line\n\nthis whole paragraph is deleted outright now\n")
        with open(new, "w") as f:
            f.write("keep this line\n")
        proc = _run_blockdiff(["--files", old, new, "--json"], cwd=REPO_ROOT)
        assert proc.returncode == 0, proc.stderr
        import json
        data = json.loads(proc.stdout)
        assert any("deleted outright" in r["content"] for r in data["removed"]), \
            f"expected plain-deletion content in removed; got: {data['removed']}"
        # No phantom line_start=-1 entries.
        for r in data["removed"]:
            assert r["line_start"] != -1, f"phantom removed entry: {r}"
        for a in data["added"]:
            assert a["line_start"] != -1, f"phantom added entry: {a}"
