# blockdiff

A drop-in replacement tool for `git diff` that detects cross-file moved lines.

> [!NOTE]
> This project was vibe coded in an IDE by **Antigravity** (powered by **Gemini 2.0 Flash Thinking**).

## The Problem
`git diff --color-moved` detects moved lines but only within the same file. It cannot detect when a paragraph or code block moves from `file_a.md` to `file_b.md`. Standard `git diff` shows the move as a deletion in A and an insertion in B, which is indistinguishable from actual content loss.

## The Solution
`blockdiff` parses `git diff` output and reclassifies cross-file moves as a single `MOVED` block instead. It works on markdown, source code, and any text files.

## Installation

```bash
pip install blockdiff

# Or with MCP support for AI agents:
pip install "blockdiff[mcp]"
```

## Usage

Use it as a drop-in replacement for `git diff`:

```bash
git diff HEAD | blockdiff

# Or run directly:
blockdiff HEAD
blockdiff HEAD~3 HEAD
blockdiff abc123 def456

# Works on any two files directly (no git needed):
blockdiff --files old.md new.md

# Output as JSON:
blockdiff HEAD --json
```

## Output Format

`blockdiff` uses the standard diff format but adds a new block type:

* **Removed (Red)**: Content deleted, no match found anywhere
* **Added (Green)**: Content inserted, no match found anywhere  
* **Moved (Yellow)**: Content that disappeared from one file and appeared in another. Shown as `FROM: file_a.md:47 -> TO: file_b.md:12`. If the block was modified slightly, word-level inline diffs are shown.

Moved blocks are removed from the deleted and added block lists entirely. Small blocks (under 20 words) are ignored to prevent noise on minor edits.

## Using with AI agents (MCP)

`blockdiff` includes an MCP server that exposes the move detection tool to AI agents.

Add to your MCP config:
```json
{
  "mcpServers": {
    "blockdiff": {
      "command": "python",
      "args": ["/path/to/blockdiff_mcp.py"]
    }
  }
}
```

The agent can now call `blockdiff()` after modifying files to verify nothing was permanently lost before committing.

## TODO

* **Semantic equivalence checking**: verify that reorganized content is informationally lossless (detect merged/split paragraphs, paraphrased moves, synthesized content)
* **LLM-assisted residual audit**: for unmatched deletions
* **Graph diff**: for wikilink structure (Obsidian vaults)
* **Configurable similarity threshold**: (default 0.8)
* **IDE/editor plugins**
