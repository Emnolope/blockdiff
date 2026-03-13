from dataclasses import dataclass
from typing import List, Optional
import difflib

from .parse import DiffBlock

@dataclass
class MovedBlock:
    source_file: str
    source_line: int
    target_file: str
    target_line: int
    source_content: str
    target_content: str
    is_exact: bool
    similarity: float = 1.0

def normalize(text: str) -> str:
    """Normalize whitespace for matching."""
    return " ".join(text.split())

def find_moves(removed_blocks: List[DiffBlock], added_blocks: List[DiffBlock], 
               min_words=20, similarity_threshold=0.8) -> tuple[List[DiffBlock], List[DiffBlock], List[MovedBlock]]:
    """
    Finds moved blocks between removed and added blocks.
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

        best_match = None
        best_ratio = 0.0
        best_added_idx = -1
        is_exact = False

        normalized_removed = normalize(removed.content)

        # 1. Exact match pass
        for i, added in enumerate(remaining_added):
            if added.word_count < min_words:
                continue
            if normalized_removed == normalize(added.content):
                best_match = added
                best_added_idx = i
                is_exact = True
                break
        
        # 2. Fuzzy match pass
        if not best_match:
            for i, added in enumerate(remaining_added):
                if added.word_count < min_words:
                    continue
                ratio = difflib.SequenceMatcher(None, normalized_removed, normalize(added.content)).ratio()
                if ratio > similarity_threshold and ratio > best_ratio:
                    best_ratio = ratio
                    best_match = added
                    best_added_idx = i

        if best_match:
            moved_blocks.append(MovedBlock(
                source_file=removed.file_path,
                source_line=removed.start_line,
                target_file=best_match.file_path,
                target_line=best_match.start_line,
                source_content=removed.content,
                target_content=best_match.content,
                is_exact=is_exact,
                similarity=1.0 if is_exact else best_ratio
            ))
            # Remove from added list
            remaining_added.pop(best_added_idx)
        else:
            remaining_removed.append(removed)

    return remaining_removed, remaining_added, moved_blocks
