from dataclasses import dataclass
from typing import Dict, List, Tuple
import subprocess


@dataclass
class RenamedFile:
    old_path: str
    new_path: str
    similarity: int  # always 100 now — these are byte-identical, not guesses


def _ls_tree(repo_path: str, ref: str) -> Dict[str, str]:
    """Ask git for the raw truth: every path and the blob hash it points to.
    No diff, no rename detector, no similarity nose. Just the object store."""
    result = subprocess.run(
        ["git", "ls-tree", "-r", ref],
        capture_output=True, text=True, cwd=repo_path
    )
    tree: Dict[str, str] = {}
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        # format: "<mode> <type> <hash>\t<path>"
        meta, _, path = line.partition('\t')
        if not path:
            continue
        parts = meta.split()
        if len(parts) < 3:
            continue
        blob_hash = parts[2]
        tree[path] = blob_hash
    return tree


def get_changed_files(repo_path: str, ref_old: str, ref_new: str = "HEAD") -> Tuple[List[str], List[RenamedFile]]:
    """Git tracks files. Git does NOT diff content, and Git does NOT guess renames.

    We pull raw {path: blob_hash} for both trees and do the bucketing ourselves:
      - identical hash under a different name  -> pure rename (fact, not guess)
      - hash changed                           -> modify   -> blob
      - path only in old                       -> delete   -> blob
      - path only in new                       -> add      -> blob

    The only similarity check in this whole layer is hash EQUALITY, which is
    identity, not a heuristic. Git's -M rename detector never runs.
    """
    old_tree = _ls_tree(repo_path, ref_old)
    new_tree = _ls_tree(repo_path, ref_new)

    changed: List[str] = []
    renamed: List[RenamedFile] = []

    old_paths = set(old_tree)
    new_paths = set(new_tree)

    # Raw truth first: what appeared, what vanished, what mutated in place.
    deleted = old_paths - new_paths
    added = new_paths - old_paths
    common = old_paths & new_paths

    # Modifies: same path, different hash. These go into the blob.
    for path in common:
        if old_tree[path] != new_tree[path]:
            changed.append(path)

    # Pure-rename reconstruction, heuristic-free.
    # Build {hash: [paths]} for the vanished and the appeared, then match on
    # exact hash. A vanished blob that reappears under a new name IS a rename,
    # because it's the SAME blob hash — byte-identical, git's own storage says so.
    deleted_by_hash: Dict[str, List[str]] = {}
    for path in deleted:
        deleted_by_hash.setdefault(old_tree[path], []).append(path)

    added_by_hash: Dict[str, List[str]] = {}
    for path in added:
        added_by_hash.setdefault(new_tree[path], []).append(path)

    consumed_deleted: set = set()
    consumed_added: set = set()

    for blob_hash, old_names in deleted_by_hash.items():
        new_names = added_by_hash.get(blob_hash)
        if not new_names:
            continue
        # Same hash on both sides under different names -> pure rename(s).
        # Pair them off positionally; any leftovers fall through to add/delete.
        for old_name, new_name in zip(sorted(old_names), sorted(new_names)):
            renamed.append(RenamedFile(old_name, new_name, 100))
            consumed_deleted.add(old_name)
            consumed_added.add(new_name)

    # Whatever wasn't consumed by a rename is a genuine delete or add -> blob.
    for path in deleted:
        if path not in consumed_deleted:
            changed.append(path)
    for path in added:
        if path not in consumed_added:
            changed.append(path)

    return changed, renamed

def get_file_content(repo_path: str, ref: str, path: str) -> str:
    """Pull the raw blob for a single path at the given ref.
    Returns empty string if the file didn't exist at that ref (new add or pure delete)."""
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True, text=True, cwd=repo_path
    )
    if result.returncode != 0:
        return ""
    return result.stdout
