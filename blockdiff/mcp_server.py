# mcp_server.py — machine-facing entry point.
#
#
# One source of truth for engine knobs: BlockDiffEngine.TUNABLE_PARAMS. The
# human CLI generates flags from it; we generate defaults from it. Same table.

from mcp.server.fastmcp import FastMCP
import json

from .parse import get_changed_files, get_file_content
from .match import find_moves
from .output import _payload
from .cacycle import BlockDiffEngine

mcp = FastMCP("blockdiff")

# Defaults pulled straight from the engine's declared knobs.
_ENGINE_DEFAULTS = {name: default for name, _t, default, _h in BlockDiffEngine.TUNABLE_PARAMS}

@mcp.tool()
def blockdiff(repo_path: str = ".", ref_old: str = "HEAD~1", ref_new: str = "HEAD",
              file1: str = "", file2: str = "",
              engine_overrides: dict = None) -> str:
    """
    Detect cross-file moved blocks.

    Pipeline: git tracks the changed files -> their old/new contents get
    concatenated into two blobs (one per version) separated by runtime-random
    fenced sentinels -> cacycle runs ONE block-move diff over the whole blob ->
    output is parsed back to per-file attribution via the sentinels.

    Engine knobs live in BlockDiffEngine.TUNABLE_PARAMS. Pass any subset via
    engine_overrides, e.g. {"char_diff": false, "block_min_length": 5}. Unset
    knobs use the engine's own defaults. The human CLI exposes the identical
    set as flags — clanker-human parity.
    """
    try:
        old_files, new_files, renamed = {}, {}, []
        if file1 and file2:
            with open(file1, encoding="utf-8", errors="replace") as f:
                old_files[file1] = f.read()
            with open(file2, encoding="utf-8", errors="replace") as f:
                new_files[file2] = f.read()
        else:
            changed, renamed = get_changed_files(repo_path, ref_old, ref_new)
            renamed_paths = {r.old_path for r in renamed} | {r.new_path for r in renamed}
            for path in changed:
                if path in renamed_paths:
                    continue
                oc = get_file_content(repo_path, ref_old, path)
                nc = get_file_content(repo_path, ref_new, path)
                if oc or (not oc and not nc):
                    old_files[path] = oc
                if nc or (not oc and not nc):
                    new_files[path] = nc

        if not old_files and not new_files and not renamed:
            return json.dumps(_payload([], [], [], []), indent=2)

        engine_config = dict(_ENGINE_DEFAULTS)
        if engine_overrides:
            for k, v in engine_overrides.items():
                if k in _ENGINE_DEFAULTS:
                    engine_config[k] = v

        removed, added, moved = find_moves(
            old_files, new_files, engine_config=engine_config)
        return json.dumps(_payload(removed, added, moved, renamed), indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def run():
    mcp.run()


if __name__ == "__main__":
    run()
