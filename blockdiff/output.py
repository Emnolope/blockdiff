import json
from typing import List
from rich.console import Console
from rich.panel import Panel
from rich.markup import escape

from .parse import RenamedFile
from .match import MovedBlock, ResultBlock


def _payload(removed: List[ResultBlock], added: List[ResultBlock],
             moved: List[MovedBlock], renamed: List[RenamedFile] = None) -> dict:
    """Single source of truth for the structured output. CLI --json and the
    MCP server both serialize THIS. Keeps clanker-human parity honest."""
    renamed = renamed or []
    return {
        "renamed": [{"old_path": r.old_path, "new_path": r.new_path, "similarity": r.similarity}
                    for r in renamed],
        "removed": [{"file": r.file_path, "line_start": r.start_line, "content": r.content}
                    for r in removed],
        "added": [{"file": a.file_path, "line_start": a.start_line, "content": a.content}
                  for a in added],
        "moved": [{"from_file": m.source_file, "from_line": m.source_line,
                   "to_file": m.target_file, "to_line": m.target_line,
                   "content": m.content} for m in moved],
        "summary": {"renamed_count": len(renamed), "removed_count": len(removed),
                    "added_count": len(added), "moved_count": len(moved)},
    }


def render_diff(removed: List[ResultBlock], added: List[ResultBlock],
                moved: List[MovedBlock], renamed: List[RenamedFile] = None):
    renamed = renamed or []
    console = Console()

    if renamed:
        console.print(Panel("RENAMED FILES", style="cyan bold"))
        for r in renamed:
            console.print(escape(f"RENAMED: {r.old_path} -> {r.new_path} ({r.similarity}%)"),
                          style="cyan bold")
        console.print()

    if moved:
        console.print(Panel("MOVED BLOCKS", style="yellow bold"))
        for m in moved:
            console.print(escape(f"FROM: {m.source_file}:{m.source_line} -> "
                                 f"TO: {m.target_file}:{m.target_line}"), style="yellow bold")
            for line in m.content.split('\n'):
                console.print(f"~ {escape(line)}", style="yellow")
            console.print()

    if removed:
        console.print(Panel("REMOVED BLOCKS (No cross-file match)", style="red bold"))
        for rem in removed:
            console.print(escape(f"--- {rem.file_path}:{rem.start_line}"), style="red bold")
            for line in rem.content.split('\n'):
                console.print(escape(line), style="red")
            console.print()

    if added:
        console.print(Panel("ADDED BLOCKS (No cross-file match)", style="green bold"))
        for add in added:
            console.print(escape(f"+++ {add.file_path}:{add.start_line}"), style="green bold")
            for line in add.content.split('\n'):
                console.print(escape(line), style="green")
            console.print()

    if not (renamed or moved or removed or added):
        console.print("No significant block changes detected.", style="dim")


def render_json(removed: List[ResultBlock], added: List[ResultBlock],
                moved: List[MovedBlock], renamed: List[RenamedFile] = None):
    print(json.dumps(_payload(removed, added, moved, renamed), indent=2))
