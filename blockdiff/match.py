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
    Finds exact moved blocks between removed and added blocks.
    Returns:
        (remaining_removed, remaining_added, moved_blocks)
    """
    remaining_removed = []
    remaining_added = added_blocks.copy()
    moved_blocks = []

    for removed in removed_blocks:
        if removed.word_count < min_words:
            remaining_removed.append(removed)
            continue

        # Exact match only
        for i, added in enumerate(remaining_added):
            if added.word_count < min_words:
                continue
            if normalize(removed.content) == normalize(added.content):
                moved_blocks.append(MovedBlock(
                    source_file=removed.file_path,
                    source_line=removed.start_line,
                    target_file=added.file_path,
                    target_line=added.start_line,
                    source_content=removed.content,
                    target_content=added.content
                ))
                remaining_added.pop(i)
                break
        else:
            remaining_removed.append(removed)

    return remaining_removed, remaining_added, moved_blocks
