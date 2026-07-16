# blockdiff/output.py
import json
from typing import List
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.rule import Rule

from .parse import RenamedFile
from .match import MovedBlock, ResultBlock, MoveFragment


# ── palette ───────────────────────────────────────────────────────────────
# One place to fiddle colors. Change these, restyle the whole tool.
C_RENAME = "cyan"
C_MOVE   = "yellow"
C_DEL    = "red"
C_ADD    = "green"
C_GUTTER = "grey42"      # line-number gutter, dim so content leads
C_ARROW  = "bright_white"

# Move palette (Light / Dark variant pairs), deliberately avoiding red/green
MOVE_PALETTE = [
    ("bright_blue",    "blue"),
    ("bright_magenta", "magenta"),
    ("bright_cyan",    "cyan"), 
    ("orange3",        "dark_orange3"),
    ("plum2",          "purple4"),
    ("khaki1",         "gold3"),
]
MAX_MOVE_COLORS = len(MOVE_PALETTE)


def color_for(color_id):
    if color_id is None:
        return (C_MOVE, C_MOVE)  # fallback: old single-yellow behavior
    idx = (color_id - 1) % MAX_MOVE_COLORS
    return MOVE_PALETTE[idx]


def _payload(removed: List[ResultBlock], added: List[ResultBlock],
             moved: List[MovedBlock], renamed: List[RenamedFile] = None) -> dict:
    """Single source of truth for structured output. CLI --json and the MCP
    server both serialize THIS. Untouched — cosmetics never touch the data."""
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
                   "content": m.content,
                   "color_id": getattr(m, 'color_id', None),
                   "fragments": [{"kind": f.kind, "content": f.content} for f in getattr(m, 'fragments', [])]} 
                  for m in moved],
        "summary": {"renamed_count": len(renamed), "removed_count": len(removed),
                    "added_count": len(added), "moved_count": len(moved)},
    }


def _body_fragments(console: Console, fragments: List[MoveFragment], gutter_start: int, tint: str = C_MOVE, side_filter: str = None):
    n = gutter_start if gutter_start >= 0 else None
    current_text = Text()
    line_has_target_content = False

    def emit_line():
        nonlocal n, current_text, line_has_target_content
        if line_has_target_content:
            gutter = f"{n:>5} " if n is not None else "    · "
        else:
            gutter = "      "
        out = Text()
        out.append(gutter, style=C_GUTTER)
        out.append(current_text)
        console.print(out)
        current_text = Text()
        line_has_target_content = False

    base_style = {'=': tint, '+': C_ADD, '-': C_DEL}

    for frag in fragments:
        if side_filter == "dark_side" and frag.kind == '+':
            continue
        if side_filter == "light_side" and frag.kind == '-':
            continue
            
        style = base_style.get(frag.kind, "")
        parts = frag.content.split('\n')
        
        for i, part in enumerate(parts):
            if i > 0:
                emit_line()
                if n is not None:
                    # In dark (source) side, only advance lines for = and -
                    if side_filter == "dark_side" and frag.kind in ('=', '-'):
                        n += 1
                    # In light (target) side, advance lines for = and +
                    elif side_filter != "dark_side" and frag.kind in ('=', '+'):
                        n += 1
            if part:
                current_text.append(part, style=style)
                if side_filter == "dark_side" and frag.kind in ('=', '-'):
                    line_has_target_content = True
                elif side_filter != "dark_side" and frag.kind in ('=', '+'):
                    line_has_target_content = True

    if len(current_text) > 0:
        emit_line()


def render_diff(removed: List[ResultBlock], added: List[ResultBlock],
                moved: List[MovedBlock], renamed: List[RenamedFile] = None,
                display_mode: str = "target"):
    renamed = renamed or []
    console = Console()

    if renamed:
        _section(console, "RENAMED FILES", C_RENAME, len(renamed))
        for r in renamed:
            t = Text()
            t.append("  rename  ", style=f"{C_RENAME} bold")
            t.append(r.old_path, style=C_RENAME)
            t.append("  →  ", style=C_ARROW)
            t.append(r.new_path, style=C_RENAME)
            t.append(f"  ({r.similarity}%)", style="dim")
            console.print(t)

    if moved:
        _section(console, "MOVED BLOCKS", C_MOVE, len(moved))
        for m in moved:
            light, dark = color_for(m.color_id)
            fragments = getattr(m, 'fragments', [])

            if display_mode == "source":
                head = Text()
                head.append("  ", style="")
                head.append(f"{m.source_file}:{m.source_line}", style=f"{dark} bold")
                head.append("  →  ", style=C_ARROW)
                head.append(f"{m.target_file}:{m.target_line}", style=dark)
                console.print(head)
                
                if fragments:
                    _body_fragments(console, fragments, m.source_line, tint=dark, side_filter="dark_side")
                else:
                    _body(console, m.content, dark, m.source_line)

            elif display_mode == "both":
                head1 = Text()
                head1.append("  ", style="")
                head1.append(f"{m.source_file}:{m.source_line}", style=f"{dark} bold")
                console.print(head1)
                
                if fragments:
                    _body_fragments(console, fragments, m.source_line, tint=dark, side_filter="dark_side")
                
                arrow = Text("      moved to ", style=C_ARROW)
                arrow.append(f"{m.target_file}:{m.target_line}", style=f"{light} bold")
                console.print(arrow)
                
                if fragments:
                    _body_fragments(console, fragments, m.target_line, tint=light, side_filter="light_side")
                else:
                    _body(console, m.content, light, m.target_line)

            else:  # "target" (default)
                head = Text()
                head.append("  ", style="")
                head.append(f"{m.source_file}:{m.source_line}", style=light)
                head.append("  →  ", style=C_ARROW)
                head.append(f"{m.target_file}:{m.target_line}", style=f"{light} bold")
                console.print(head)
                
                if fragments:
                    _body_fragments(console, fragments, m.target_line, tint=light, side_filter="light_side")
                else:
                    _body(console, m.content, light, m.target_line)
                
            console.print()

    if removed:
        _section(console, "REMOVED  (no cross-file match)", C_DEL, len(removed))
        for rem in removed:
            head = Text()
            head.append("  − ", style=f"{C_DEL} bold")
            head.append(f"{rem.file_path}:{rem.start_line}", style=f"{C_DEL} bold")
            console.print(head)
            _body(console, rem.content, C_DEL, rem.start_line)
            console.print()

    if added:
        _section(console, "ADDED  (no cross-file match)", C_ADD, len(added))
        for add in added:
            head = Text()
            head.append("  + ", style=f"{C_ADD} bold")
            head.append(f"{add.file_path}:{add.start_line}", style=f"{C_ADD} bold")
            console.print(head)
            _body(console, add.content, C_ADD, add.start_line)
            console.print()

    if not (renamed or moved or removed or added):
        console.print("No significant block changes detected.", style="dim")
    else:
        console.print()
        console.print(Rule(style="grey30"))
        summary = Text()
        summary.append(f"  {len(renamed)} renamed", style=C_RENAME)
        summary.append("   ")
        summary.append(f"{len(moved)} moved", style=C_MOVE)
        summary.append("   ")
        summary.append(f"{len(removed)} removed", style=C_DEL)
        summary.append("   ")
        summary.append(f"{len(added)} added", style=C_ADD)
        console.print(summary)


def _section(console: Console, title: str, style: str, count: int):
    """A titled rule instead of a boxed panel — reads cleaner, wastes no width."""
    console.print()
    console.print(Rule(f"[{style} bold]{title}[/]  [dim]({count})[/]",
                       style=style, align="left"))


def _body(console: Console, content: str, style: str, gutter_start: int):
    """Fallback for raw single-colored blocks without threaded fragments."""
    lines = content.split("\n")
    for i, line in enumerate(lines):
        n = gutter_start + i if gutter_start >= 0 else None
        gutter = f"{n:>5} " if n is not None else "    · "
        t = Text()
        t.append(gutter, style=C_GUTTER)
        t.append(line, style=style)
        console.print(t)


def render_json(removed: List[ResultBlock], added: List[ResultBlock],
                moved: List[MovedBlock], renamed: List[RenamedFile] = None):
    print(json.dumps(_payload(removed, added, moved, renamed), indent=2))
