# =============================================================================
# blockdiff/__init__.py — THE GAUGE CLUSTER (Package Root & Manifest)
# =============================================================================
# SUBSYSTEM ROLE
#   Package root: defines the public API surface re-exported to consumers and
#   the project's build metadata contract.
#
# INVOLABLE DATA CONTRACTS & INVARIANTS
#   - Explicit __all__ list exporting the public API. Every name promised here
#     MUST resolve as an attribute (enforced by tests/test_imports.py::
#     test_package_exports_match_reality).
#   - pyproject.toml defines the two console-script entry points:
#       blockdiff      = blockdiff.cli:main
#       blockdiff-mcp  = blockdiff.mcp_server:run
#   - The original JS reference implementation (0riginal_Cacycle_diff.js) is
#     preserved at the repository root for algorithmic lineage.
#
# TOMBSTONES (DO NOT TOUCH)
#   - Never let __all__ drift from reality.
#   - Never import `mcp` here -- it is an OPTIONAL dependency (blockdiff[mcp])
#     and must stay optional.
#
# COUPLING BOUNDARIES
#   Imports: .match, .parse, .hashdiff only (re-export layer). Never import
#   .cacycle, .cli, .output, or .mcp_server into the package root.
# =============================================================================
# blockdiff/__init__.py
from .match import find_moves, MovedBlock, ResultBlock, MoveFragment
from .parse import get_changed_files, get_file_content, get_tree_files, RenamedFile
from .hashdiff import git_blob_hash, prefilter_files, read_directory

__all__ = [
    "find_moves",
    "MovedBlock",
    "ResultBlock",
    "MoveFragment",
    "get_changed_files",
    "get_file_content",
    "get_tree_files",
    "RenamedFile",
    "git_blob_hash",
    "prefilter_files",
    "read_directory",
]
