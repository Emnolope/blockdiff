# tests/test_imports.py
#
# The floor. Not "does it work" — "does it LOAD." Forty iterations of vibe-code
# have never been run; the first thing that breaks in an unrun package is import
# time: a syntax error, a stale name in __all__, a relative import that points
# nowhere, a circular import between match <-> cacycle <-> output.
#
# This test asserts nothing about diffing. It asserts the package is a package.
# If this fails, no other test can even be collected, so this runs first and
# alone tells you whether you have a Python module or a text file that ends in .py.
#
# ONE deliberate exception: mcp_server imports `mcp`, which is an OPTIONAL
# dependency (pyproject: blockdiff[mcp]). On a bare install its import SHOULD
# fail with ModuleNotFoundError('mcp'). That is correct behavior, not a bug, so
# we allow exactly that one failure and nothing else. Any other error on
# mcp_server — a bad *relative* import, a missing name from .output or .match —
# is a real defect and must still blow up.

import importlib
import pytest

# Pure modules: no optional deps. These MUST import clean, no excuses.
CORE_MODULES = [
    "blockdiff",            # the package __init__ (re-exports)
    "blockdiff.cacycle",    # the engine — do not touch, but must load
    "blockdiff.parse",      # git file tracker
    "blockdiff.match",      # blob + stage1/stage2 attribution
    "blockdiff.output",     # rich/json rendering
    "blockdiff.cli",        # human entry point
]


@pytest.mark.parametrize("module_name", CORE_MODULES)
def test_core_module_imports(module_name):
    """Each core module loads without raising. This is the whole test."""
    importlib.import_module(module_name)


def test_mcp_server_imports_or_only_lacks_mcp():
    """mcp_server may fail ONLY because the optional `mcp` package is absent.
    Any other ImportError (a broken .output/.match/.parse reference, a typo in a
    relative import) is a real bug and is re-raised."""
    try:
        importlib.import_module("blockdiff.mcp_server")
    except ModuleNotFoundError as e:
        # Tolerate the one legitimate absence; nothing else.
        if (e.name or "").split(".")[0] != "mcp":
            raise


def test_package_exports_match_reality():
    """__init__ promises names in __all__. A promise the module can't keep is a
    NameError waiting to happen the first time someone does `from blockdiff
    import X`. Verify each promised name actually resolves on the package."""
    import blockdiff
    for name in blockdiff.__all__:
        assert hasattr(blockdiff, name), f"__all__ promises {name!r}, package doesn't have it"
