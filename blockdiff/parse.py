from dataclasses import dataclass
from typing import List, Optional
from unidiff import PatchSet

@dataclass
class DiffBlock:
    file_path: str
    start_line: int
    content: str
    is_added: bool
    
    # Track the original diff lines for rendering if it stays as added/removed
    raw_lines: List[str] 

    @property
    def word_count(self) -> int:
        return len(self.content.split())

@dataclass
class RenamedFile:
    old_path: str
    new_path: str
    similarity: int  # 0-100%

def parse_diff(diff_text: str) -> tuple[List[DiffBlock], List[DiffBlock], List[RenamedFile]]:
    """
    Parses unified diff text into lists of added and removed blocks.
    A block is a contiguous run of changed lines within a hunk, separated by empty lines.
    
    Also detects renamed files (via similarity index in git diff).
    """
    patch_set = PatchSet(diff_text)
    removed_blocks = []
    added_blocks = []
    renamed_files = []

    # Track rename mappings from git diff metadata
    # Git diff outputs: similarity index, rename from, rename to
    pending_sim = None
    pending_old = None
    
    for line in diff_text.split('\n'):
        if line.startswith('similarity index '):
            # "similarity index 82%"
            parts = line.split()
            pending_sim = int(parts[2].rstrip('%'))
        elif line.startswith('rename from '):
            pending_old = line[12:]  # "rename from path"
        elif line.startswith('rename to '):
            new_path = line[10:]  # "rename to path"
            if pending_sim is not None and pending_old is not None:
                renamed_files.append(RenamedFile(pending_old, new_path, pending_sim))
            pending_sim = None
            pending_old = None

    for patched_file in patch_set:
        file_path = patched_file.path
        
        for hunk in patched_file:
            current_removed = []
            current_removed_raw = []
            removed_start = None
            
            current_added = []
            current_added_raw = []
            added_start = None

            def flush_removed():
                nonlocal current_removed, current_removed_raw, removed_start
                if current_removed:
                    content = "\n".join(current_removed)
                    removed_blocks.append(DiffBlock(file_path, removed_start, content, False, current_removed_raw.copy()))
                current_removed.clear()
                current_removed_raw.clear()
                removed_start = None

            def flush_added():
                nonlocal current_added, current_added_raw, added_start
                if current_added:
                    content = "\n".join(current_added)
                    added_blocks.append(DiffBlock(file_path, added_start, content, True, current_added_raw.copy()))
                current_added.clear()
                current_added_raw.clear()
                added_start = None

            for line in hunk:
                text = line.value.rstrip("\r\n")
                
                if line.is_removed:
                    if removed_start is None:
                        removed_start = line.source_line_no
                    if not text.strip():
                        flush_removed()
                    else:
                        current_removed.append(text)
                        current_removed_raw.append(f"-{text}")
                else:
                    flush_removed()
                    
                if line.is_added:
                    if added_start is None:
                        added_start = line.target_line_no
                    if not text.strip():
                        flush_added()
                    else:
                        current_added.append(text)
                        current_added_raw.append(f"+{text}")
                else:
                    flush_added()
                    
            flush_removed()
            flush_added()

    return removed_blocks, added_blocks, renamed_files
