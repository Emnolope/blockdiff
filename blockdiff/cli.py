# cli.py — human-facing entry point. Clanker-human parity: every engine knob the
# MCP server exposes is surfaced here as a flag, generated from the SAME
# BlockDiffEngine.TUNABLE_PARAMS table. One source of truth.
#


import argparse
from .parse import get_changed_files, get_file_content
from .match import find_moves
from .output import render_diff, render_json
from .cacycle import BlockDiffEngine


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


def _collect(repo_path, ref_old, ref_new, files):
    old_files, new_files, renamed = {}, {}, []
    if files:
        old_path, new_path = files
        with open(old_path, encoding="utf-8", errors="replace") as f:
            old_files[old_path] = f.read()
        with open(new_path, encoding="utf-8", errors="replace") as f:
            new_files[new_path] = f.read()
    else:
        changed, renamed = get_changed_files(repo_path, ref_old, ref_new)
        for path in changed:
            oc = get_file_content(repo_path, ref_old, path)
            nc = get_file_content(repo_path, ref_new, path)
            # Don't drop a side purely for falsy content; keep regions aligned.
            if oc or (not oc and not nc):
                old_files[path] = oc
            if nc or (not oc and not nc):
                new_files[path] = nc
    return old_files, new_files, renamed


def main():
    parser = argparse.ArgumentParser(description="blockdiff - detect cross-file moved blocks.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--repo-path", default=".")
    parser.add_argument("--files", nargs=2, metavar=("OLD", "NEW"),
                        help="Diff two files directly, no git.")
    parser.add_argument("ref_old", nargs="?", default="HEAD~1")
    parser.add_argument("ref_new", nargs="?", default="HEAD")
    _add_engine_args(parser)

    args = parser.parse_args()

    old_files, new_files, renamed = _collect(
        args.repo_path, args.ref_old, args.ref_new, args.files)

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
        render_diff(removed, added, moved, renamed)


if __name__ == "__main__":
    main()
