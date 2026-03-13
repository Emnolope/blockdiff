"""
Heckel algorithm for block-level diff.
Based on Paul Heckel (1978) - "A technique for isolating differences between files"
"""
from dataclasses import dataclass
from typing import List, Dict, Set, Tuple

from .parse import DiffBlock

@dataclass
class HeckelBlock:
    """A block classified by the Heckel algorithm."""
    source_file: str
    source_line: int
    target_file: str
    target_line: int
    source_content: str
    target_content: str
    block_type: str  # "moved", "removed", "added", "unchanged"

def tokenize(text: str) -> List[str]:
    """Split text into words."""
    return text.split()

def get_unique_words(blocks: List[DiffBlock]) -> Set[str]:
    """
    Find words that appear exactly once across all blocks.
    These are unique anchors for alignment.
    """
    word_freq: Dict[str, int] = {}
    
    for block in blocks:
        words = set(tokenize(block.content.lower()))
        for word in words:
            word_freq[word] = word_freq.get(word, 0) + 1
    
    # Words appearing exactly once
    return {word for word, count in word_freq.items() if count == 1}

def find_heckel_matches(removed_blocks: List[DiffBlock], added_blocks: List[DiffBlock],
                        min_words: int = 20) -> Tuple[List[DiffBlock], List[DiffBlock], List[HeckelBlock]]:
    """
    Heckel algorithm for cross-file move detection.
    
    Steps:
    1. Find unique words in removed and added blocks
    2. Use unique words as anchors to identify matching blocks
    3. Classify blocks as moved/removed/added
    """
    # Skip small blocks
    removed_filtered = [b for b in removed_blocks if b.word_count >= min_words]
    added_filtered = [b for b in added_blocks if b.word_count >= min_words]
    
    # Step 1: Find unique words in each set
    removed_unique = get_unique_words(removed_filtered)
    added_unique = get_unique_words(added_filtered)
    
    # Step 2: Find blocks with unique words
    removed_with_unique = {}
    for block in removed_filtered:
        words = set(tokenize(block.content.lower()))
        unique_in_block = words & removed_unique
        if unique_in_block:
            for w in unique_in_block:
                removed_with_unique[w] = block
    
    added_with_unique = {}
    for block in added_filtered:
        words = set(tokenize(block.content.lower()))
        unique_in_block = words & added_unique
        if unique_in_block:
            for w in unique_in_block:
                added_with_unique[w] = block
    
    # Step 3: Match blocks via unique words
    matched_words = removed_unique & added_unique
    
    moved_blocks = []
    remaining_removed = list(removed_filtered)
    remaining_added = list(added_filtered)
    
    matched_indices_removed = set()
    matched_indices_added = set()
    
    for word in matched_words:
        if word in removed_with_unique and word in added_with_unique:
            src_block = removed_with_unique[word]
            tgt_block = added_with_unique[word]
            
            for i, b in enumerate(remaining_removed):
                if i not in matched_indices_removed and b == src_block:
                    for j, a in enumerate(remaining_added):
                        if j not in matched_indices_added and a == tgt_block:
                            moved_blocks.append(HeckelBlock(
                                source_file=src_block.file_path,
                                source_line=src_block.start_line,
                                target_file=tgt_block.file_path,
                                target_line=tgt_block.start_line,
                                source_content=src_block.content,
                                target_content=tgt_block.content,
                                block_type="moved"
                            ))
                            matched_indices_removed.add(i)
                            matched_indices_added.add(j)
                            break
                    break
    
    final_removed = [b for i, b in enumerate(remaining_removed) if i not in matched_indices_removed]
    final_added = [b for i, b in enumerate(remaining_added) if i not in matched_indices_added]
    
    return final_removed, final_added, moved_blocks
