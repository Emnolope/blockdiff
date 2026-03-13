import sys
import argparse
import subprocess

from .parse import parse_diff
from .match import find_moves
from .output import render_diff, render_json

def main():
    parser = argparse.ArgumentParser(description="blockdiff - Detect cross-file moved lines in git diffs.")
    parser.add_argument("--files", nargs=2, help="Compare two specific files instead of a git diff.")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format.")
    parser.add_argument("git_args", nargs="*", help="Arguments to pass to git diff (e.g. HEAD, HEAD~1)")
    
    args = parser.parse_args()

    diff_text = ""

    if args.files:
        file1, file2 = args.files
        # Run git diff --no-index file1 file2
        result = subprocess.run(["git", "diff", "--no-index", file1, file2], capture_output=True, text=True, encoding="utf-8")
        diff_text = result.stdout
    elif args.git_args:
        # Run git diff with args
        cmd = ["git", "diff"] + args.git_args
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        diff_text = result.stdout
    elif not sys.stdin.isatty():
        # Read from stdin
        diff_text = sys.stdin.read()
    else:
        # Run git diff (no args)
        result = subprocess.run(["git", "diff"], capture_output=True, text=True, encoding="utf-8")
        diff_text = result.stdout

    if not diff_text.strip():
        print("No differences found.")
        return

    removed, added = parse_diff(diff_text)
    rem_out, add_out, moved_out = find_moves(removed, added, min_words=20)
    
    if args.json:
        render_json(rem_out, add_out, moved_out)
    else:
        render_diff(rem_out, add_out, moved_out)

if __name__ == "__main__":
    main()
