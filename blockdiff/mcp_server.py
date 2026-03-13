from mcp.server.fastmcp import FastMCP
import subprocess
import json

from blockdiff.parse import parse_diff
from blockdiff.match import find_moves

mcp = FastMCP("blockdiff")

@mcp.tool()
def blockdiff(repo_path: str = ".", ref1: str = "HEAD~1", ref2: str = "HEAD", min_words: int = 20) -> str:
    """
    Detect moved, added, and removed content blocks across files in a git repository. 
    Finds cross-file paragraph moves that git diff misses. Returns structured JSON.
    """
    try:
        # Run git diff using repo_path as cwd
        cmd = ["git", "diff", ref1, ref2]
        # stdin=DEVNULL prevents git from inheriting the MCP server's stdio pipes on Windows,
        # which would corrupt the JSON-RPC transport stream
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, 
                                cwd=repo_path, stdin=subprocess.DEVNULL)
        diff_text = result.stdout
        
        if not diff_text.strip():
            return json.dumps({"message": "No differences found.", "removed": [], "added": [], "moved": [], "summary": {}}, indent=2)

        removed, added = parse_diff(diff_text)
        rem_out, add_out, moved_out = find_moves(removed, added, min_words=min_words)
        
        # Construct JSON response
        
        res = {
            "removed": [{"file": r.file_path, "line_start": r.start_line, "content": r.content} for r in rem_out],
            "added": [{"file": a.file_path, "line_start": a.start_line, "content": a.content} for a in add_out],
            "moved": [],
            "summary": {
                "removed_count": len(rem_out),
                "added_count": len(add_out),
                "moved_count": len(moved_out)
            }
        }

        for m in moved_out:
            res["moved"].append({
                "from_file": m.source_file,
                "from_line": m.source_line,
                "to_file": m.target_file,
                "to_line": m.target_line,
                "content": m.target_content
            })

        return json.dumps(res, indent=2)
            
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)

def run():
    mcp.run()

if __name__ == "__main__":
    run()
