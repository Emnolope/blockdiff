"""
hashdiff.py — Git-compatible hash prefilter.

Git hashes blobs as SHA-1 over "blob <byte-size>\\0<bytes>". We use the same
format here so that folder-mode content hashes are directly comparable to
`git ls-tree` output.

This keeps the diff engine from drowning in identical content:

    old                     new                     action
    --------------------------------------------------------------
    same path, same hash    ->      silently dropped
    diff path, same hash    ->      reported as RenamedFile(100), dropped
    same path, diff hash    ->      kept for diff engine
    path only in old        ->      reported as removed, kept for engine
    path only in new        ->      reported as added,   kept for engine

Input is abstract: two ``{path: content}`` mappings. Works for git mode,
folder mode, worktree mode, or any other source you feed it.
"""

import hashlib
from collections import defaultdict
from typing import Dict, Iterable, List, Set, Tuple

from .parse import RenamedFile


def git_blob_hash(content: str, encoding: str = "utf-8") -> str:
    """Compute the exact SHA-1 hash Git would use for this content as a blob.

    Git object format: "blob <byte-size>\\0<bytes>".
    """
    data = content.encode(encoding, errors="replace")
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _content_hash(content: str) -> str:
    """Default content hash: Git-style SHA-1 blob hash."""
    return git_blob_hash(content)


def prefilter_files(
    old_files: Dict[str, str],
    new_files: Dict[str, str],
) -> Tuple[Dict[str, str], Dict[str, str], List[RenamedFile], List[str], List[str]]:
    """
    Compare two path->content mappings and strip out byte-identical noise.

    Returns:
        (old_diff_files, new_diff_files, renamed, removed_paths, added_paths)
    """
    old_hashes = {path: _content_hash(content) for path, content in old_files.items()}
    new_hashes = {path: _content_hash(content) for path, content in new_files.items()}

    old_paths = set(old_files)
    new_paths = set(new_files)

    # 1. Same path, same hash -> identical, drop from both.
    identical_same_path = {
        path for path in old_paths & new_paths if old_hashes[path] == new_hashes[path]
    }

    # 2. Pure rename reconstruction across paths by hash.
    old_by_hash: Dict[str, List[str]] = defaultdict(list)
    for path in old_paths:
        if path in identical_same_path:
            continue
        old_by_hash[old_hashes[path]].append(path)

    new_by_hash: Dict[str, List[str]] = defaultdict(list)
    for path in new_paths:
        if path in identical_same_path:
            continue
        new_by_hash[new_hashes[path]].append(path)

    renamed: List[RenamedFile] = []
    consumed_old: Set[str] = set()
    consumed_new: Set[str] = set()

    for blob_hash, old_names in old_by_hash.items():
        new_names = new_by_hash.get(blob_hash)
        if not new_names:
            continue
        for old_name, new_name in zip(sorted(old_names), sorted(new_names)):
            renamed.append(RenamedFile(old_name, new_name, 100))
            consumed_old.add(old_name)
            consumed_new.add(new_name)

    old_diff_files: Dict[str, str] = {}
    new_diff_files: Dict[str, str] = {}

    for path in old_paths:
        if path in identical_same_path or path in consumed_old:
            continue
        old_diff_files[path] = old_files[path]

    for path in new_paths:
        if path in identical_same_path or path in consumed_new:
            continue
        new_diff_files[path] = new_files[path]

    removed = sorted(old_paths - new_paths - identical_same_path - consumed_old)
    added = sorted(new_paths - old_paths - identical_same_path - consumed_new)

    return old_diff_files, new_diff_files, renamed, removed, added


def read_directory(path: str, skip_binary: bool = False) -> Dict[str, str]:
    """
    Recursively read a directory and return {relative_path: text_content}.

    Walks all non-hidden files. Uses forward slashes as separators regardless
    of host OS. Content is read as UTF-8 with replacement of invalid bytes.
    """
    from pathlib import Path

    root = Path(path)
    files: Dict[str, str] = {}

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        # Skip hidden files and files inside hidden directories.
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue

        if skip_binary:
            try:
                data = p.read_bytes()
                # Crude binary sniff: contains a null byte.
                if b"\x00" in data:
                    continue
                text = data.decode("utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                continue
        else:
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                continue

        key = str(p.relative_to(root)).replace("\\", "/")
        files[key] = text

    return files
