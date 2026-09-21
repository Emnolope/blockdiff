# =============================================================================
# blockdiff/cli.py — THE STEERING WHEEL (Human CLI Entry Point)
# =============================================================================
# SUBSYSTEM ROLE
#   Human-facing command-line interface. Picks a file-collection mode, runs
#   the prefilter, invokes the match/attribution pipeline, and delegates
#   rendering entirely to output.py.
#
# INVOLABLE DATA CONTRACTS & INVARIANTS
#   - CLANKER-HUMAN PARITY: engine flags are generated dynamically from
#     BlockDiffEngine.TUNABLE_PARAMS (_add_engine_args). The human CLI and the
#     FastMCP server must never drift apart -- same table, one source of truth.
#   - Supports Git refs (default HEAD~1..HEAD), --files, --folders, and
#     --folder-vs-git.
#   - In --files mode the canonical key equivalence (key = old_path) is FORCED
#     across both file dicts so build_blobs sees one shared slot. Mismatched
#     keys would manufacture phantom cross-file moves of stationary text.
#
# TOMBSTONES (DO NOT TOUCH)
#   - Never hardcode CLI engine flags independently of TUNABLE_PARAMS.
#   - Never pass mismatched keys in --files mode.
#   - Never re-implement engine or attribution logic inside this file.
#
# COUPLING BOUNDARIES
#   Imports: .parse, .hashdiff, .match, .output, .cacycle (one direction,
#   downstream). Exposes `main` as the `blockdiff` console script entry point.
# =============================================================================
import argparse
import os
from .parse import get_changed_files, get_file_content, get_tree_files
from .hashdiff import prefilter_files, read_directory
from .match import find_moves
from .output import render_diff, render_json
from .cacycle import BlockDiffEngine


# cli.py — human-facing entry point. Clanker-human parity: every engine knob the
# MCP server exposes is surfaced here as a flag, generated from the SAME
# BlockDiffEngine.TUNABLE_PARAMS table. One source of truth.
#


def _add_engine_args(parser):
    for name, typ, default, help_text in BlockDiffEngine.TUNABLE_PARAMS:
        flag = "--" + name.replace("_", "-")
        if typ is bool:
            parser.add_argument(flag, dest=name, action="store_true", default=default,
                                help=help_text + f" (default {default})")
            parser.add_argument("--no-" + name.replace("_", "-"), dest=name,
                                action="store_false", help=argparse.SUPPRESS)
        else:
            parser.add_argument(flag, dest=name, type=typ, default=default,
                                help=help_text + f" (default {default})")


def _engine_config(args):
    return {name: getattr(args, name) for name, _t, _d, _h in BlockDiffEngine.TUNABLE_PARAMS}


def _collect_files(old_path, new_path):
    with open(old_path, encoding="utf-8", errors="replace") as f:
        old_content = f.read()
    with open(new_path, encoding="utf-8", errors="replace") as f:
        new_content = f.read()
    # --files diffs two versions of ONE logical file. Use the OLD path as
    # the canonical key on both sides so build_blobs sees a single shared
    # slot. Using distinct keys here silently violates build_blobs'
    # "every path appears in both dicts under the same key" assumption:
    # it would drop new content into a phantom slot labeled NEW, and
    # attribute OLD-side diffs to OLD and NEW-side diffs to NEW, producing
    # bogus cross-file "moves" of stationary text. For genuine rename
    # detection, use git mode: a commit that renames A->B surfaces as a
    # RenamedFile there.
    key = old_path
    return {key: old_content}, {key: new_content}, []


def _collect_git(repo_path, ref_old, ref_new):
    changed, renamed = get_changed_files(repo_path, ref_old, ref_new)
    renamed_paths = {r.old_path for r in renamed} | {r.new_path for r in renamed}
    old_files, new_files = {}, {}
    for path in changed:
        if path in renamed_paths:
            continue
        oc = get_file_content(repo_path, ref_old, path)
        nc = get_file_content(repo_path, ref_new, path)
        if oc or (not oc and not nc):
            old_files[path] = oc
        if nc or (not oc and not nc):
            new_files[path] = nc
    return old_files, new_files, renamed


def _collect_folders(old_folder, new_folder):
    old_files = read_directory(old_folder)
    new_files = read_directory(new_folder)
    return old_files, new_files, []


def _collect_folder_vs_git(repo_path, folder, ref):
    """Compare a filesystem folder to a Git tree/ref.

    Hashes line up because read_directory uses git_blob_hash, which is the
    same SHA-1("blob <size>\\0<bytes>") format Git stores.
    """
    folder_files = read_directory(folder)
    git_files = get_tree_files(repo_path, ref)
    return folder_files, git_files, []


def _run_prefilter(old_files, new_files, renamed_git):
    old_diff, new_diff, renamed_prefilter, removed, added = prefilter_files(
        old_files, new_files)
    # Combine with any already-known pure renames from git mode.
    return old_diff, new_diff, renamed_git + renamed_prefilter, removed, added


def main():
    parser = argparse.ArgumentParser(description="blockdiff - detect cross-file moved blocks.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--repo-path", default=".")
    parser.add_argument("--files", nargs=2, metavar=("OLD", "NEW"),
                        help="Diff two files directly, no git.")
    parser.add_argument("--folders", nargs=2, metavar=("OLD", "NEW"),
                        help="Diff two folders directly, no git.")
    parser.add_argument("--folder-vs-git", nargs=2, metavar=("FOLDER", "REF"),
                        dest="folder_vs_git",
                        help="Diff a folder against a Git ref (uses Git's blob hash).")
    parser.add_argument("ref_old", nargs="?", default="HEAD~1")
    parser.add_argument("ref_new", nargs="?", default="HEAD")
    parser.add_argument("--display-mode", choices=["source", "target", "both"], default="target",
                        help="How to display moved blocks with inline edits.")
    _add_engine_args(parser)

    args = parser.parse_args()

    # Decide collection mode.
    if args.files:
        old_files, new_files, renamed = _collect_files(*args.files)
    elif args.folders:
        old_files, new_files, renamed = _collect_folders(*args.folders)
    elif args.folder_vs_git:
        folder, ref = args.folder_vs_git
        old_files, new_files, renamed = _collect_folder_vs_git(
            args.repo_path, folder, ref)
        # Normalize ordering: folder is "old", git ref is "new".
    else:
        old_files, new_files, renamed = _collect_git(
            args.repo_path, args.ref_old, args.ref_new)

    old_files, new_files, renamed, removed_paths, added_paths = _run_prefilter(
        old_files, new_files, renamed)

    if not old_files and not new_files and not renamed:
        if args.json:
            render_json([], [], [], [])
        else:
            print("No differences found.")
        return

    removed, added, moved = find_moves(
        old_files, new_files, engine_config=_engine_config(args))

    if args.json:
        render_json(removed, added, moved, renamed)
    else:
        render_diff(removed, added, moved, renamed, display_mode=args.display_mode)

if __name__ == "__main__":
    main()
