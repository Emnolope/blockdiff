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

def find_moves(removed_blocks: List[DiffBlock], added_blocks: List[DiffBlock],
               min_words=20) -> tuple[List[DiffBlock], List[DiffBlock], List[MovedBlock]]:
    """
    Finds moved blocks between removed and added blocks.
    Handles two cases:
      1. Exact move: entire removed block == entire added block
      2. Split move: removed block was split into multiple smaller added blocks
         (added block content is a substring of the removed block)

    Returns:
        (remaining_removed, remaining_added, moved_blocks)
    """
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

            # Case 1: exact match (block moved wholesale)
            # Case 2: subset match (block was split; this added chunk came from removed)
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
            # Pop matched added blocks in reverse so indices stay valid
            for i in sorted(matched_indices, reverse=True):
                remaining_added.pop(i)
            # The removed block was accounted for — don't add to remaining_removed
        else:
            remaining_removed.append(removed)

    return remaining_removed, remaining_added, moved_blocks
