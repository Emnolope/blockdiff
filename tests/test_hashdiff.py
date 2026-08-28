import json
import os
import subprocess
import sys
import tempfile
import textwrap

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _run_blockdiff(args, cwd=REPO_ROOT):
    """Invoke the CLI via `python -m blockdiff.cli` from a given cwd."""
    return subprocess.run(
        [sys.executable, "-m", "blockdiff.cli", *args],
        cwd=cwd, capture_output=True, text=True,
    )


class TestBlobHasher:
    """Git-compatible blob hashing must match `git hash-object` byte-for-byte."""

    def test_git_blob_hash_matches_git_command_simple(self):
        from blockdiff.hashdiff import git_blob_hash
        content = "test content\n"
        # Verified against `git hash-object --stdin`
        assert git_blob_hash(content) == "d670460b4b4aece5915caf5c68d12f560a9fe3e4"

    def test_git_blob_hash_matches_git_command_longer(self):
        from blockdiff.hashdiff import git_blob_hash
        content = "what is up, doc!\n"
        assert git_blob_hash(content) == "dfd4526e983f0eba6d0283679d5d5bd03ef840ba"

    def test_git_blob_hash_empty_blob(self):
        """Git stores an empty blob at e69de29bb2d1d6434b8b29ae775ad8c2e48c5391."""
        from blockdiff.hashdiff import git_blob_hash
        assert git_blob_hash("") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


class TestPrefilter:
    """prefilter_files must drop identical content, detect pure renames, and
    preserve genuinely changed/added/removed paths for the diff engine."""

    def test_identical_content_dropped(self):
        from blockdiff.hashdiff import prefilter_files
        old = {"a.py": "print(1)\n"}
        new = {"a.py": "print(1)\n"}
        old_diff, new_diff, renamed, removed, added = prefilter_files(old, new)
        assert old_diff == {}
        assert new_diff == {}
        assert renamed == []
        assert removed == []
        assert added == []

    def test_pure_rename_detected_by_hash(self):
        from blockdiff.hashdiff import prefilter_files
        old = {"old_name.py": "print(1)\n"}
        new = {"new_name.py": "print(1)\n"}
        old_diff, new_diff, renamed, removed, added = prefilter_files(old, new)
        assert old_diff == {}
        assert new_diff == {}
        assert [(r.old_path, r.new_path, r.similarity) for r in renamed] == [
            ("old_name.py", "new_name.py", 100)
        ]
        assert removed == []
        assert added == []

    def test_changed_content_kept(self):
        from blockdiff.hashdiff import prefilter_files
        old = {"a.py": "print(1)\n"}
        new = {"a.py": "print(2)\n"}
        old_diff, new_diff, renamed, removed, added = prefilter_files(old, new)
        assert old_diff == old
        assert new_diff == new
        assert renamed == []
        assert removed == []
        assert added == []

    def test_added_and_removed_paths(self):
        from blockdiff.hashdiff import prefilter_files
        old = {"gone.py": "bye\n"}
        new = {"fresh.py": "hi\n"}
        old_diff, new_diff, renamed, removed, added = prefilter_files(old, new)
        assert old_diff == {"gone.py": "bye\n"}
        assert new_diff == {"fresh.py": "hi\n"}
        assert renamed == []
        assert removed == ["gone.py"]
        assert added == ["fresh.py"]

    def test_mixed_scenario(self):
        from blockdiff.hashdiff import prefilter_files
        old = {
            "same.py": "unchanged\n",
            "renamed.py": "shared\n",
            "modified.py": "old\n",
            "deleted.py": "gone\n",
        }
        new = {
            "same.py": "unchanged\n",
            "renamed2.py": "shared\n",
            "modified.py": "new\n",
            "added.py": "hello\n",
        }
        old_diff, new_diff, renamed, removed, added = prefilter_files(old, new)

        assert old_diff == {"modified.py": "old\n", "deleted.py": "gone\n"}
        assert new_diff == {"modified.py": "new\n", "added.py": "hello\n"}
        assert [(r.old_path, r.new_path, r.similarity) for r in renamed] == [
            ("renamed.py", "renamed2.py", 100)
        ]
        assert removed == ["deleted.py"]
        assert added == ["added.py"]


class TestFolderVsGitCLI:
    """End-to-end: a folder can be compared to a Git commit hash, using the same
    SHA-1 blob hashes Git itself uses."""

    def test_folder_vs_git_ref_reports_no_differences_for_identical_tree(self):
        with tempfile.TemporaryDirectory() as d:
            repo = os.path.join(d, "repo")
            folder = os.path.join(d, "folder")
            os.makedirs(repo)
            os.makedirs(folder)

            # Build a git repo with one file.
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            repo_file = os.path.join(repo, "hello.py")
            with open(repo_file, "w") as f:
                f.write("print('git')\n")
            subprocess.run(["git", "add", "hello.py"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "first"], cwd=repo, check=True)

            # Copy the same content to a folder.
            with open(os.path.join(folder, "hello.py"), "w") as f:
                f.write("print('git')\n")

            ref = "HEAD"
            proc = _run_blockdiff(["--repo-path", repo, "--folder-vs-git", folder, ref, "--json"])
            assert proc.returncode == 0, proc.stderr
            data = json.loads(proc.stdout)
            assert data["renamed"] == []
            assert data["removed"] == []
            assert data["added"] == []
            assert data["moved"] == []

    def test_folder_vs_git_ref_detects_content_change(self):
        with tempfile.TemporaryDirectory() as d:
            repo = os.path.join(d, "repo")
            folder = os.path.join(d, "folder")
            os.makedirs(repo)
            os.makedirs(folder)

            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            repo_file = os.path.join(repo, "hello.py")
            with open(repo_file, "w") as f:
                f.write("print('git')\n")
            subprocess.run(["git", "add", "hello.py"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "first"], cwd=repo, check=True)

            # Folder has changed content: one line modified, one new line added.
            with open(os.path.join(folder, "hello.py"), "w") as f:
                f.write("print('folder')\n")
                f.write("# extra folder line\n")

            proc = _run_blockdiff(["--repo-path", repo, "--folder-vs-git", folder, "HEAD", "--json"])
            assert proc.returncode == 0, proc.stderr
            data = json.loads(proc.stdout)
            # The prefilter drops nothing because hashes differ. The engine sees
            # the same path on both sides, so it reports an intra-file move with
            # fragments showing the changed/added lines.
            assert data["moved"], data
            fragments = data["moved"][0]["fragments"]
            assert any("extra folder line" in f["content"] for f in fragments), fragments
