from mcp.server.fastmcp import FastMCP
import subprocess
import json

from blockdiff.parse import parse_diff
from blockdiff.match import find_moves

mcp = FastMCP("blockdiff")

@mcp.tool()
def blockdiff(repo_path: str = ".", git_args: list[str] = [], file1: str = "", file2: str = "",
              diff_text: str = "", min_words: int = 20) -> str:
    try:
        if diff_text:
            text = diff_text
        elif file1 and file2:
            r = subprocess.run(["git", "diff", "--no-index", file1, file2],
                                capture_output=True, text=True, cwd=repo_path, stdin=subprocess.DEVNULL)
            text = r.stdout
        else:
            cmd = ["git", "diff"] + list(git_args)
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_path, stdin=subprocess.DEVNULL)
            text = r.stdout

        if not text.strip():
            return json.dumps({"message": "No differences found.", "removed": [], "added": [], "moved": [], "summary": {}}, indent=2)

        removed, added, renamed = parse_diff(text)
        rem_out, add_out, moved_out = find_moves(removed, added, min_words=min_words)

        res = {
            "renamed": [{"old_path": r.old_path, "new_path": r.new_path, "similarity": r.similarity} for r in renamed],
            "removed": [{"file": r.file_path, "line_start": r.start_line, "content": r.content} for r in rem_out],
            "added": [{"file": a.file_path, "line_start": a.start_line, "content": a.content} for a in add_out],
            "moved": [{"from_file": m.source_file, "from_line": m.source_line, "to_file": m.target_file,
                       "to_line": m.target_line, "content": m.target_content} for m in moved_out],
            "summary": {"renamed_count": len(renamed), "removed_count": len(rem_out),
                        "added_count": len(add_out), "moved_count": len(moved_out)}
        }
        return json.dumps(res, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)

def run():
    mcp.run()

if __name__ == "__main__":
    run()