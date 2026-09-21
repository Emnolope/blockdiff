**blockdiff** — a cross-file moved-block diff engine that treats provenance as sacred.

`git diff` shows a relocated paragraph as a *deletion in file A* and an *insertion in file B* —
indistinguishable from permanent content loss. `blockdiff` recovers the truth: it detects when a
paragraph or code block moved from one file to another, re-attaches inline edits (`=`, `+`, `-`) to
the move, and reports *Renamed*, *Removed*, *Added*, and *Moved* with deterministic integer
provenance — never fuzzy similarity guesses.

---

# PHILOSOPHY & PROVENANCE (The Soul)

## The Domain Impetus & Operational Origin

- **Constrained origin environment.** `blockdiff` was developed and vibe-coded inside
  resource-constrained environments, on a Termux session on a OnePlus 6T mobile device. That
  constraint is architectural law: **zero heavy runtimes** (no Node.js, no Rust toolchain) and
  **zero expensive LLM API dependencies** for standard diffing. The entire engine is pure typed
  Python with exactly two runtime dependencies (`rich`, and `mcp[cli]` for the optional agent mode).
- **PKM vault maintenance & automated splitting.** The tool was built to support automated
  refactoring of large personal knowledge management (PKM) vaults into content-addressed notes
  (`hash_<xxhash64>.md`). Splitting and reorganizing thousands of interlinked notes is exactly the
  operation where a naive `git diff` makes every intentional move look like mass deletion.
- **The existential risk of silent knowledge loss.** In unstructured notes and personal knowledge
  vaults, accidental deletion or hallucinated loss is irreversible knowledge destruction. A diff
  tool must act as an uncompromising stop-gap against silent omission — which is why `removed`
  content is treated as a red-flag candidate for loss, never as a routine cosmetic event.

## The Failure of Standard Diff Tools

- **Git's ontological mismatch.** Git models identity at the **file** level (`{path: blob_hash}`),
  while refactoring models identity at the **content-block** level. The two ontologies disagree
  exactly where the damage happens: when blocks cross file boundaries.
- **The false deletion/insertion illusion.** In `git diff` — even with `--color-moved` — a
  cross-file relocation renders as an unrelated deletion in file A and an unrelated insertion in
  file B. To human reviewers and AI agents, that rendering is **indistinguishable from permanent
  content loss**.
- **The failure of heuristic similarity (`-M`).** Git's rename detector (`-M`, `-M100%`) uses lossy
  similarity heuristics across file paths. It *guesses* renames. `blockdiff` never guesses: a
  rename is proven by 100% byte-identical Git blob hashes or not reported at all.

## The Anti-Optimization Principle (Provenance is Sacred)

- **The semantic inversion trap.** Standard diff engines minimize character/word edit distance. But
  minimizing edit distance can destroy human meaning — a lone dropped word ("not") is a one-character
  win for the optimizer and a total inversion of the sentence's logical truth for the reader.
  `blockdiff` therefore **does not optimize edit distance as the primary objective**. It anchors on
  exact identity and preserves meaning.
- **Exact identity over probabilistic guessing.** Exact byte and token anchoring outranks fuzzy
  approximation. Identity is anchored on deterministic integer character offsets. Content is
  *cargo* — used only for display, never to decide a match.
- **Preservation of semantic integrity.** A relocation must preserve its inline edit history
  (`=`, `+`, `-`) as a single unified narrative rather than shattering into disjoint shards. That is
  the paragraph you moved *plus the edits you made while moving it*.

---

# ARCHITECTURE & THE MONOLITHIC BLOB (How It Works)

## Foundational Shifts & The "Caveman Technique"

- **The failure of pairwise file comparison.** Matching files pairwise collapses quadratically
  (`O(N²)`) and fails completely on *twin/straddle* paragraphs — identical paragraphs moving
  simultaneously cross-match into phantom deletes.
- **The Caveman Technique proof-of-concept.** Concatenate all "before" files into a single buffer
  and all "after" files into another, then diff the two buffers **globally** through Paul Heckel's
  unique-token anchoring and the cascading split engine of **wikEd diff** (Cacycle). A cross-file
  move is now an ordinary in-blob move — the engine detects it natively in one pass.
- **Transpilation to typed Python.** Cacycle's JavaScript engine was transpiled into pure typed
  Python (`blockdiff/cacycle.py`), gutting all browser DOM/CSS/HTML logic so it returns purely
  structured dataclasses (`DiffBlock`, `DiffGroup`, `DiffText`, plus the `TokenInfo` doubly-linked
  list). The original JS survives at `0riginal_Cacycle_diff.js` for algorithmic lineage.

## The Three Inviolable Architectural Layers

| Layer | Files | Role | Car Analogy |
|-------|-------|------|-------------|
| 1. State & File Tracking | `parse.py`, `hashdiff.py` | Tree inventory, hash prefiltering, pure-rename proof | Fuel Filter & Drive Train |
| 2. Monolithic Content Diffing & Move Detection | `cacycle.py` | Heckel anchoring, cascading splits, energy DP, move verdicts | The V8 Engine Core |
| 3. Intentionally Dumb Post-Hoc Attribution | `match.py` | Pure coordinate arithmetic, file-boundary attribution | The Chassis |

### Layer 1: State & File Tracking (`parse.py`, `hashdiff.py`)

- **Git is demoted to tree-state inventory.** `parse.py` calls `git ls-tree -r` and `git show`
  directly. It resolves changed paths and pure renames from raw `{path: blob_hash}` tree hash
  comparisons. **Git never diffs content here.**
- **Rejection of Git `-M`.** Pure renames are identified exclusively via 100% byte-identity Git blob
  hashes — the exact SHA-1 over the Git object header `"blob <size>\0<bytes>"` (`git_blob_hash`).
  Identical blob under a different name *is* a rename; a fact, not a guess.
- **Non-Git directory walking and prefiltering.** `read_directory` walks filesystem folders and
  `prefilter_files` buckets `{path: content}` maps by hash, dropping byte-identical files,
  reconstructing pure renames, and emitting clean `(old_diff_files, new_diff_files, renamed,
  removed_paths, added_paths)` — **without any pairwise diffing**.
- **Handoff:** Layer 1 outputs clean path-to-content maps of additions, deletions, and
  modifications. No file is ever paired against another file here.

### Layer 2: Monolithic Content Diffing & Move Detection (`cacycle.py`)

- Concatenates changed files into single monolithic blobs (`old_blob` vs `new_blob`) separated by
  runtime-randomized, fenced sentinels.
- **Heckel unique-token anchoring** combined with cascading split refinement:
  **Paragraph → Line → Sentence → Chunk → Word → Character**.
- **Ambiguous gap sliding** (`_slide_gaps`) aligns unresolved boundaries with line breaks or word
  boundaries.
- **Fine-grained character splitting** (`_split_refine_chars`) across unresolved gaps
  (guarded by `char_diff`).
- **Owns every heuristic, energy minimization, and block-movement verdict.** Decisions made here;
  nowhere else.

### Layer 3: Intentionally Dumb Post-Hoc Attribution (`match.py`)

- **Zero heuristic logic.** No content-string comparison, no similarity scoring, no size gating.
- **Runtime UUID4 sentinels** wrapped in Private-Use-Area Unicode fences
  (`\ue000\ue001\ue002<32-hex>\ue003\ue004\ue005`) are injected between files with double-newline
  padding. Uniqueness forces the engine to anchor each sentinel as its own token, giving a clean
  integer boundary that never fuses with surrounding content.
- **File ownership is resolved strictly by deterministic integer arithmetic** against authored
  character offsets (`old_char`, `new_char`). Content is cargo.
- **Safe line-number calculation** (`_line_of`) via single-pass newline counting
  (`rel = char_offset − file_start_offset − _SENTINEL_LEN − 2`); string searching in file content
  is strictly forbidden.

## The Four Historic Algorithmic Traps & Breakthrough Solutions

### Trap 1: The "Bus Illusion" (Ground Frame Evaporation)

- **Failure mode:** a massive moved block outweighed stationary file content in the DP longest
  increasing subsequence calculation, crowning *itself* as the stationary ground frame and making
  true stationary text appear to accelerate backwards — as if you were driving in a bus and the
  street seemed to move.
- **Solution (Street-Pole Sentinels):** caller-asserted prelinks (`kind="stationary"`) pin sentinel
  spans. Sentinels break block runs in `_get_same_blocks`, instantiate as singleton ground-frame
  groups, are unconditionally forced `fixed=True`, and are exempted from movement DP and unlinking.
  The poles cannot drift.
- **Engine chaining door:** `prelinks` also supports `kind="moved"`, letting upstream engines assert
  pre-computed relocations as immutable truth (warm-start diffing). Believe, link, diff around —
  never re-litigate.

### Trap 2: Stationary Spine DP & The Monotonicity Bug

- **Ergonomic keystroke metric.** Raw character counts were replaced with typing-friction cost in
  `_find_max_path`:
  `spine_value(size) = w_char·size − (move_base + move_log_k·ln(1 + size))`
  — the keystrokes *saved* by leaving a group stationary instead of cut-pasting it.
- **The monotonicity bug.** Candidate spine selection originally enforced monotonicity only on
  `old_number`, letting the DP zig-zag across `new_number` and freeze genuine movers into the
  stationary spine.
- **Resolution:** strict dual-order monotonicity is enforced across **both** `old_number` and
  `new_number` (sound under transitivity of monotonicity; the recursion cache stays correct).
  The raw-character-count baseline is preserved commented in-code as an A/B fallback.

### Trap 3: Lone-Unique Multi-Document Coincidences (`trust_lone_unique`)

- **Failure mode:** single coincidental words (`"unique"`, `"fix"`) occurring once across
  concatenated multi-file blobs were erroneously linked as cross-file moved blocks.
- **Resolution:** wikEd's single-document assumption is disabled
  (`trust_lone_unique=False` by default), forcing lone unique tokens to adhere to the scalable
  `block_min_length` floor. One source of truth for this lever is the engine knob row.

### Trap 4: Inline Edit Sharding & Trailing Insertion Orphans

- **Failure mode:** when moved blocks underwent simultaneous edits, trailing additions (`+` escaped
  the group and became isolated top-level orphan blocks.
- **Resolution:** a three-pass grouping engine in `_set_ins_groups`:
  **Pass 1** intra-group filling, **Pass 1.5** positional trailing-orphan absorption (excluding
  anchors and stationary sections), **Pass 2** standalone singleton allocation.
- **Presentation:** `classify()` in `match.py` threads inline `=`, `+`, `-` fragments directly into
  `MoveFragment` records so a move carries its edit history as one narrative.

---

# OPERATIONAL REFERENCE & CLI/MCP (How to Use It)

## Installation & Requirements

- **Standard CLI installation:** `pip install blockdiff`
- **AI Agent / MCP server installation:** `pip install "blockdiff[mcp]"`
- **Dependencies:** `rich` (terminal UI) and, optionally, `mcp[cli]` (FastMCP server).
- **Requires:** Python 3.10+ (developed against 3.12). Windows / macOS / Linux.

For a no-admin, zero-footprint developer sandbox, use `uv` (Astral):

```powershell
uv venv --python 3.12
uv pip install -e ".[mcp]" pytest
uv run pytest
```

Everything lives inside `.venv`. No global writes, no registry edits, no system Python.

## Multi-Modal Usage Modes

**Git ref comparison** (default — positional refs default to `HEAD~1` and `HEAD`):

```bash
blockdiff HEAD~1 HEAD
blockdiff main feature-branch
blockdiff <commit_a> <commit_b>
```

**Direct file comparison (no Git):**

```bash
blockdiff --files old_note.md new_note.md
```

> Enforces canonical key equivalence (`key = old_path`) across both slots. Using distinct keys would
> silently violate `build_blobs`' "every path appears in both dicts under the same key" assumption
> and manufacture phantom cross-file moves of stationary text. For genuine rename detection, use git
> mode.

**Standalone directory comparison:**

```bash
blockdiff --folders /path/to/old_vault /path/to/new_vault
```

**Hybrid folder-vs-git tree comparison:**

```bash
blockdiff --folder-vs-git /path/to/vault HEAD
```

> Compares an uncommitted filesystem folder directly against a Git ref. Hashes line up because
> `read_directory` uses `git_blob_hash`, the same SHA-1 `"blob <size>\0<bytes>"` format Git stores.

**Machine JSON output:**

```bash
blockdiff HEAD~1 HEAD --json
```

## Visual Output Semantics & Perspective Rendering

- **Terminal rules over panels.** Clean titled horizontal rules
  (`rich.rule.Rule`) maximize reading width without constricting boxes.
- **Color taxonomy (aesthetic non-red/non-green rule):**

| Event | Color | Meaning |
|-------|-------|---------|
| `Renamed` | Cyan | 100% byte-identical file relocation |
| `Removed` | Red | true deletion with no cross-file destination |
| `Added` | Green | true insertion with no cross-file origin |
| `Moved` | 6 cycled light/dark pairs | relocated block (`bright_blue/blue`, `bright_magenta/magenta`, `bright_cyan/cyan`, `orange3/dark_orange3`, `plum2/purple4`, `khaki1/gold3`) |

  **Red and green are strictly forbidden as move tints** — a moved block must never be confused with
  a `+`/`−` edit.

- **Perspective display modes (`--display-mode`):**
  - `target` (default, light side): moved blocks rendered in destination-file context; hides `-`
    deletions, renders `+` additions in green, advances lines on `=` and `+`.
  - `source` (dark side): moved blocks rendered in origin-file context; hides `+` additions,
    renders `-` deletions in red, advances lines on `=` and `-`.
  - `both`: dual rendering — origin context (dark side), a connector rule
    (`moved to <target_file>:<target_line>`), then destination context (light side).
- **Gutter precision:** 5-character dim `grey42` gutter (`f"{n:>5} "`), 6-space suppression on
  lines containing exclusively filtered-out fragments, and a middle-dot indicator (`"    · "`) for
  missing addresses (an honest `-1`, never a guessed line).

## AI Agent Integration & MCP Configuration

`blockdiff` ships a FastMCP server so AI agents can verify *before committing* that no knowledge was
destroyed.

**Registration (`claude_desktop_config.json`):**

```json
{
  "mcpServers": {
    "blockdiff": {
      "command": "blockdiff-mcp"
    }
  }
}
```

**Clanker–human parity guarantee.** Every engine parameter exposed on the CLI is identically exposed
to the FastMCP tool schema. Both derive flags, types, and defaults dynamically from the single
`BlockDiffEngine.TUNABLE_PARAMS` table — the same table, one source of truth, no drift.

**Agent decision protocol.** Agents call `blockdiff()` prior to committing. If
`summary.removed_count > 0` and deletions were not intended, the agent must treat this as potential
**knowledge destruction**, halt, and audit relocations before proceeding.

## Tunable Engine Knobs Reference (`BlockDiffEngine.TUNABLE_PARAMS`)

The single source of truth. The CLI and MCP surface these exact rows; do not add a knob here without
adding it to the engine's `__init__` and vice-versa.

| # | Knob | Type | Default | Meaning |
|---|------|------|---------|---------|
| 1 | `char_diff` | `bool` | `True` | Refine diffs down to character level in unresolved gaps |
| 2 | `repeated_diff` | `bool` | `True` | Re-diff across matched crossovers repeatedly |
| 3 | `recursive_diff` | `bool` | `True` | Recurse into gaps between matched anchors |
| 4 | `recursion_max` | `int` | `10` | Maximum recursion depth for recursive diffing |
| 5 | `unlink_blocks` | `bool` | `True` | Drop short non-unique `=` fragments as noise |
| 6 | `unlink_max` | `int` | `5` | Maximum unlinking rejection cycles |
| 7 | `block_min_length` | `int` | `3` | Minimum token length floor for valid blocks |
| 8 | `w_char` | `float` | `1.0` | Weight of a kept stationary character on the DP spine |
| 9 | `move_base` | `float` | `4.0` | Flat keystroke penalty for a cut-paste (Ctrl-X/Ctrl-V) |
| 10 | `move_log_k` | `float` | `1.0` | Logarithmic selection-penalty scaling factor |
| 11 | `trust_lone_unique` | `bool` | `False` | Treat lone unique tokens across concatenated blobs as coincidence (False, subject to `block_min_length` floor) rather than single-document signal (True) |

**Soft vs. hard gating.** `--block-min-length` is a *scalable floor* for groups and lone unique
tokens, but short **structural** markdown markers (e.g. `# [[splitter]]` or heading tags) survive
whenever Heckel anchoring pairs them. Moves are never gated by size — a relocation is trustworthy
because the engine already proved it is the same content in a new place.

## Component Map & In-File Guardrails (Localized Soul Anchors)

Every core module opens with a standardized high-voltage header stating its subsystem role (car
analogy), its inviolable data contracts, and its tombstones. Summary:

| Module | Component | Contract in one line |
|--------|-----------|-----------------------|
| `blockdiff/cacycle.py` | The V8 Engine Core | All heuristics live here; returns `List[DiffBlock]`; spine DP is dual-order monotonic; anchor groups are pinned ground frame |
| `blockdiff/match.py` | The Chassis | Intentionally dumb arithmetic: attribution by integer char offsets only, zero similarity scoring |
| `blockdiff/hashdiff.py` | The Fuel Filter | Exact SHA-1 `"blob <size>\0<bytes>"`; prefilter before the engine, never after |
| `blockdiff/parse.py` | The Drive Train | `git ls-tree -r` / `git show` only; a strict ban on `git diff` and `-M` |
| `blockdiff/output.py` | The Dashboard | Read-only observer; `_payload()` is the single JSON serialization source; no red/green move tints |
| `blockdiff/cli.py` | The Steering Wheel | Human entry point; engine flags generated from `TUNABLE_PARAMS`; `--files` forces `key = old_path` |
| `blockdiff/mcp_server.py` | The Machine Interface | FastMCP endpoint; defaults derive from `TUNABLE_PARAMS`; JSON matches `_payload()` schema |
| `blockdiff/__init__.py` | The Gauge Cluster | Explicit `__all__`; entry points `blockdiff` / `blockdiff-mcp`; `0riginal_Cacycle_diff.js` preserved for lineage |

## Verification Guardrails & Red-Test Protocol

- **The "Green Suite Lies" axiom.** Passing synthetic unit tests does not guarantee move-detection
  integrity — unit tests reflect anticipated behavior, not emergent multi-document blob interactions.
- **The Git self-diff empirical reality check.** Ground-truth validation requires running
  `blockdiff HEAD~1 HEAD --json` across real repository history and inspecting raw JSON payloads to
  verify relocated blocks and inline fragments maintain provenance.
- **RED-first bugfix protocol.** Before touching engine logic in `cacycle.py` or attribution logic in
  `match.py`, write a failing RED regression test reproducing the exact failure mode.

**Mandatory green canaries (must never fail):**

- `test_sentinels_are_the_fixed_spine_after_a_big_move` — sentinels anchor the stationary ground
  frame and prevent the Bus Illusion.
- `test_whole_body_relocation_when_source_file_survives` — whole-body relocation detection when the
  source file retains surviving text.
- `test_twin_straddling_one_sentinel` — twin paragraphs across sentinel boundaries identified by
  distinct char offsets without aliasing.
- `test_move_and_genuine_deletion_in_one_commit_do_not_smear` — stationary groups with deletions
  remain in `removed`.

**Inviolable architectural tombstones (do not violate — documented per-module in-file):**

1. **No string keys in attribution.** Character offsets are integers; content is cargo. Never key on
   content strings or dictionary pairings in `match.py`.
2. **No external heuristics.** All move heuristics belong exclusively to `cacycle.py`. Never add size
   gates or similarity scoring to `match.py` or `output.py`.
3. **No Git rename heuristics.** Git `-M` is permanently rejected. Renames require 100% byte-identical
   blob-hash equality.
4. **No red/green move palettes.** Never use red or green tints for moved blocks.

## Project Roadmap

- **Semantic equivalence verification** — identifying paraphrased or synthesized moves.
- **Wikilink graph diffing** — for PKM vault link structures.
- **LLM-assisted residual loss verification** — auditing unmatched deletions as candidate knowledge
  loss.
- **Direct IDE/editor visual gutter plugins** — in-editor moved-block visualization.