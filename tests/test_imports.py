# tests/test_imports.py
#
# Before testing what any function DOES, prove the code can even be loaded.
# match.py imports cacycle.py, which compiles ~12 regexes from hand-transpiled
# JS unicode ranges AT MODULE LOAD. A single reversed range [b-a] is an
# re.error thrown on import, before one line of logic runs. If this file is
# red, every other test is meaningless.

def test_cacycle_imports_and_regexes_compile():
    # The import itself runs _parse_unicode_ranges and re.compile on every
    # RE_SPLIT pattern. If any transpiled range is malformed, this raises here.
    import blockdiff.cacycle as c
    # Touch the regex table so we KNOW they materialized, not just that the
    # module object exists.
    assert c.RE_SPLIT["word"].search("hello")
    assert c.RE_SPLIT["line"]
    assert c.RE_COUNT_WORDS.search("word")


def test_engine_instantiates():
    from blockdiff.cacycle import BlockDiffEngine
    eng = BlockDiffEngine()
    # The knob table the CLI and MCP both build themselves from. If it's
    # malformed, both frontends generate broken interfaces.
    assert BlockDiffEngine.TUNABLE_PARAMS
    for row in BlockDiffEngine.TUNABLE_PARAMS:
        assert len(row) == 4  # (name, type, default, help)


def test_engine_defaults_match_init_signature():
    # mcp_server builds _ENGINE_DEFAULTS from TUNABLE_PARAMS and passes them
    # as **kwargs to BlockDiffEngine. If a param name in the table isn't a
    # real __init__ arg, the MCP server explodes at runtime, not here — so
    # catch it here.
    import inspect
    from blockdiff.cacycle import BlockDiffEngine
    sig = inspect.signature(BlockDiffEngine.__init__)
    init_args = set(sig.parameters) - {"self"}
    table_names = {name for name, _t, _d, _h in BlockDiffEngine.TUNABLE_PARAMS}
    missing = table_names - init_args
    assert not missing, f"TUNABLE_PARAMS names not in __init__: {missing}"


def test_match_imports():
    from blockdiff.match import build_blobs, find_moves, desentinel, classify
    assert build_blobs and find_moves and desentinel and classify


def test_parse_imports():
    from blockdiff.parse import get_changed_files, get_file_content, RenamedFile
    assert get_changed_files and get_file_content and RenamedFile


def test_package_init_imports():
    # __init__.py re-exports. If it references a name that got renamed in a
    # refactor, `import blockdiff` dies and both entry points die with it.
    import blockdiff
    assert blockdiff.find_moves
    assert blockdiff.MovedBlock
    assert blockdiff.ResultBlock