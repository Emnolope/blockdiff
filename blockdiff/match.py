from dataclasses import dataclass
from typing import List

from .parse import DiffBlock

@dataclass
class MovedBlock:
    source_file: str
    source_line: int
    target_file: str
    target_line: int
    source_content: str
    target_content: str

def normalize(text: str) -> str:
    """Normalize whitespace for matching."""
    return " ".join(text.split())

def find_moves(removed_blocks, added_blocks, min_words=20):
    remaining_removed = []
    remaining_added = list(added_blocks)
    moved_blocks = []

    for removed in removed_blocks:
        if removed.word_count < min_words:
            remaining_removed.append(removed)
            continue

        norm_rem = normalize(removed.content)
        matched_indices = []

        for i, added in enumerate(remaining_added):
            if added.word_count < min_words:
                continue
            norm_add = normalize(added.content)
            if norm_rem == norm_add or norm_add in norm_rem:
                moved_blocks.append(MovedBlock(
                    source_file=removed.file_path,
                    source_line=removed.start_line,
                    target_file=added.file_path,
                    target_line=added.start_line,
                    source_content=added.content,
                    target_content=added.content
                ))
                matched_indices.append(i)

        if matched_indices:
            for i in sorted(matched_indices, reverse=True):
                remaining_added.pop(i)

            # ← THE FIX: compute what wasn't moved
            residual = norm_rem
            for i in matched_indices:
                # matched_indices were popped, so grab content from moved_blocks
                pass

            # Rebuild residual by stripping matched content from removed
            residual = norm_rem
            for m in moved_blocks[-len(matched_indices):]:
                residual = residual.replace(normalize(m.source_content), "", 1)
            residual = residual.strip()

            if residual:
                remaining_removed.append(DiffBlock(
                    file_path=removed.file_path,
                    start_line=removed.start_line,
                    content=residual,
                    is_added=False,
                    raw_lines=[f"-{line}" for line in residual.split('\n')]
                ))
        else:
            remaining_removed.append(removed)

    return remaining_removed, remaining_added, moved_blocks
