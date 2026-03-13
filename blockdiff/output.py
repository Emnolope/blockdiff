import json
from typing import List
from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.markdown import Markdown

from .parse import DiffBlock, RenamedFile
from .match import MovedBlock

def render_diff(removed: List[DiffBlock], added: List[DiffBlock], moved: List[MovedBlock], renamed: List[RenamedFile] = None):
    """
    Renders the diff using rich, outputting RENAMED, MOVED, ADDED, and REMOVED blocks.
    """
    if renamed is None:
        renamed = []
        
    console = Console()
    
    # Render RENAMED files first
    if renamed:
        console.print(Panel("RENAMED FILES", style="cyan bold"))
        for r in renamed:
            header = f"RENAMED: {r.old_path} -> {r.new_path} ({r.similarity}%)"
            console.print(header, style="cyan bold")
        console.print()
    
    # Render MOVED blocks
    if moved:
        console.print(Panel("MOVED BLOCKS", style="yellow bold"))
        for m in moved:
            header = f"FROM: {m.source_file}:{m.source_line} -> TO: {m.target_file}:{m.target_line}"
            console.print(header, style="yellow bold")
            for line in m.source_content.split('\n'):
                console.print(f"~ {line}", style="yellow")
            console.print()

    # Render REMOVED blocks
    if removed:
        console.print(Panel("REMOVED BLOCKS (No cross-file match)", style="red bold"))
        for rem in removed:
            header = f"--- {rem.file_path}:{rem.start_line}"
            console.print(header, style="red bold")
            for line in rem.raw_lines:
                console.print(line, style="red")
            console.print()

    # Render ADDED blocks
    if added:
        console.print(Panel("ADDED BLOCKS (No cross-file match)", style="green bold"))
        for add in added:
            header = f"+++ {add.file_path}:{add.start_line}"
            console.print(header, style="green bold")
            for line in add.raw_lines:
                console.print(line, style="green")
            console.print()

def render_json(removed: List[DiffBlock], added: List[DiffBlock], moved: List[MovedBlock], renamed: List[RenamedFile] = None):
    """
    Outputs the diff as JSON.
    """
    if renamed is None:
        renamed = []
        
    res = {
        "renamed": [
            {"old_path": r.old_path, "new_path": r.new_path, "similarity": r.similarity}
            for r in renamed
        ],
        "removed": [
            {"file": r.file_path, "line_start": r.start_line, "content": r.content}
            for r in removed
        ],
        "added": [
            {"file": a.file_path, "line_start": a.start_line, "content": a.content}
            for a in added
        ],
        "moved": [],
        "summary": {
            "renamed_count": len(renamed),
            "removed_count": len(removed),
            "added_count": len(added),
            "moved_count": len(moved)
        }
    }

    for m in moved:
        res["moved"].append({
            "from_file": m.source_file,
            "from_line": m.source_line,
            "to_file": m.target_file,
            "to_line": m.target_line,
            "content": m.target_content
        })

    print(json.dumps(res, indent=2))
