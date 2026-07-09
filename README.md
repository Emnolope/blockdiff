# blockdiff

A tool that detects **cross-file moved blocks**.

> [!NOTE]
> This project was vibe coded in an IDE by **Antigravity** (powered by **Gemini 3.0 Flash**).

## The Problem
`git diff --color-moved` detects moved lines but only within the same file. It cannot detect when a paragraph or code block moves from `file_a.md` to `file_b.md`. Standard `git diff` shows the move as a deletion in A and an insertion in B, which is indistinguishable from actual content loss.

## The Solution
`blockdiff` uses git for one job only: **tracking which files changed** (via `git ls-tree` on two refs, bucketed by blob hash — no rename heuristics, only hash identity). It then concatenates the old contents of the changed files into one blob and the new contents into another, separated by runtime-random sentinels, and runs a single block-move diff (a Python port of Cacycle's wikEd diff) over the whole thing. Blocks that flew between files are caught natively in one pass and re-attributed to their source/target files by the sentinels. It works on markdown, source code, and any text files.

## Installation

```bash
pip install blockdiff

# Or with MCP support for AI agents:
pip install "blockdiff[mcp]"
```

## Usage

```bash
# Diff two refs:
blockdiff HEAD~1 HEAD
blockdiff HEAD~3 HEAD
blockdiff abc123 def456

# Works on any two files directly (no git needed):
blockdiff --files old.md new.md

# Output as JSON:
blockdiff HEAD~1 HEAD --json
```

## Output Format

* **Renamed (Cyan)**: A file whose blob hash is byte-identical under a new name. This is identity, not a similarity guess — always reported at 100%.
* **Removed (Red)**: Content deleted, no cross-file match found.
* **Added (Green)**: Content inserted, no cross-file match found.
* **Moved (Yellow)**: Content that disappeared from one file and appeared in another. Shown as `FROM: file_a.md:47 -> TO: file_b.md:12`.

Moved blocks are removed from the deleted and added lists entirely. The `--min-words` gate is **soft**: long low-signal blocks are dropped, but short-but-structural lines (a lone heading, a delimiter like `# [[splitter]]`) always survive. Moves are never gated by size — a relocation is trustworthy because the engine already proved it's the same content in a new place.

## Using with AI agents (MCP)

`blockdiff` includes an MCP server that exposes the move detection tool to AI agents. Every engine knob available to the human CLI is available to the agent, and vice versa — clanker-human parity, generated from a single `BlockDiffEngine.TUNABLE_PARAMS` table.

Add to your MCP config:
```json
{
  "mcpServers": {
    "blockdiff": {
      "command": "blockdiff-mcp"
    }
  }
}
```

The agent can call `blockdiff()` after modifying files to verify nothing was permanently lost before committing.

## TODO

* **Semantic equivalence checking**: verify that reorganized content is informationally lossless (detect merged/split paragraphs, paraphrased moves, synthesized content)
* **LLM-assisted residual audit**: for unmatched deletions
* **Graph diff**: for wikilink structure (Obsidian vaults)
* **IDE/editor plugins**
