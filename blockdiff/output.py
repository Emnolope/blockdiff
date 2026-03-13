import json
from typing import List
from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.markdown import Markdown

from .parse import DiffBlock
from .match import MovedBlock
from redlines import Redlines

def render_diff(removed: List[DiffBlock], added: List[DiffBlock], moved: List[MovedBlock]):
    """
    Renders the diff using rich, outputting REMOVED, ADDED, and MOVED blocks.
    """
    console = Console()
    
    # Render MOVED blocks
    if moved:
        console.print(Panel("MOVED BLOCKS", style="yellow bold"))
        for m in moved:
            header = f"FROM: {m.source_file}:{m.source_line} -> TO: {m.target_file}:{m.target_line}"
            console.print(header, style="yellow bold")
            
            if m.is_exact:
                for line in m.source_content.split('\n'):
                    console.print(f"~ {line}", style="yellow")
            else:
                # Modified move, use redlines for word-level inline diff
                rl = Redlines(m.source_content, m.target_content)
                console.print(Markdown(rl.output_markdown))
                
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
def render_json(removed: List[DiffBlock], added: List[DiffBlock], moved: List[MovedBlock]):
    """
    Outputs the diff as JSON.
    """
    res = {
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
            "removed_count": len(removed),
            "added_count": len(added),
            "moved_count": len(moved),
            "modified_moves_count": sum(1 for m in moved if not m.is_exact)
        }
    }

    for m in moved:
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

    print(json.dumps(res, indent=2))
