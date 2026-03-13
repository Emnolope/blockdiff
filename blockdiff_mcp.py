from mcp.server.fastmcp import FastMCP
import subprocess
import json
import os
import sys

# Add the current directory to sys.path so we can import blockdiff
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from blockdiff.parse import parse_diff
from blockdiff.match import find_moves

mcp = FastMCP("blockdiff")

@mcp.tool()
def blockdiff(repo_path: str, ref1: str = "HEAD~1", ref2: str = "HEAD", min_words: int = 20) -> str:
    """
    Detect moved, added, and removed content blocks across files in a git repository. 
    Finds cross-file paragraph moves that git diff misses. Returns structured JSON.
    """
    try:
        # Change to the repo directory
        original_cwd = os.getcwd()
        os.chdir(repo_path)
        
        try:
            # Run git diff
            cmd = ["git", "diff", ref1, ref2]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            diff_text = result.stdout
            
            if not diff_text.strip():
                return json.dumps({"message": "No differences found.", "removed": [], "added": [], "moved": [], "summary": {}}, indent=2)

            removed, added = parse_diff(diff_text)
            rem_out, add_out, moved_out = find_moves(removed, added, min_words=min_words, similarity_threshold=0.8)
            
            # Construct JSON response
            from blockdiff.output import Redlines
            
            res = {
                "removed": [{"file": r.file_path, "line_start": r.start_line, "content": r.content} for r in rem_out],
                "added": [{"file": a.file_path, "line_start": a.start_line, "content": a.content} for a in add_out],
                "moved": [],
                "summary": {
                    "removed_count": len(rem_out),
                    "added_count": len(add_out),
                    "moved_count": len(moved_out),
                    "modified_moves_count": sum(1 for m in moved_out if not m.is_exact)
                }
            }

            for m in moved_out:
                word_diff = None
                if not m.is_exact:
                    rl = Redlines(m.source_content, m.target_content)
                    word_diff = rl.output_markdown
                    
                res["moved"].append({
                    "from_file": m.source_file,
                    "from_line": m.source_line,
                    "to_file": m.target_file,
                    "to_line": m.target_line,
                    "content": m.target_content,
                    "similarity": m.similarity,
                    "modified": not m.is_exact,
                    "word_diff": word_diff
                })

            return json.dumps(res, indent=2)
            
        finally:
            os.chdir(original_cwd)
            
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)

if __name__ == "__main__":
    mcp.run()
