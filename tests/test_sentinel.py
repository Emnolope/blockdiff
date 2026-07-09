# tests/test_sentinel.py
#
# The one invariant everything else stands on: a sentinel goes INTO a blob and
# comes BACK OUT of the engine's diff intact, and _SEP_RE finds it. If the
# engine's tokenizer ever splits a fence across tokens, every cross-file
# attribution is silently wrong and NOTHING crashes. That is the exact failure
# class that ate 40 iterations: no error, just wrong. So we test it directly,
# below the whole pipeline, no git.

from blockdiff.match import _new_sentinel, _SEP_RE, build_blobs, desentinel
from blockdiff.cacycle import BlockDiffEngine


def test_sentinel_is_findable():
    """Floor of the floor: the regex matches the thing we generate, whole."""
    s = _new_sentinel()
    m = _SEP_RE.search(s)
    assert m is not None, "regex can't even find a freshly minted sentinel"
    assert m.group(0) == s, "regex matched a SUBSET of the sentinel"


def test_sentinels_are_unique_per_call():
    """Attribution maps content->file by sentinel. Collisions = cross-wiring."""
    seen = {_new_sentinel() for _ in range(1000)}
    assert len(seen) == 1000, "sentinel collision — runtime uniqueness is a lie"


def test_build_blobs_maps_every_file():
    """Every file gets exactly one sentinel, and it's identical on both sides
    so the engine can anchor it. first_file is the leftmost, for stage-1 default."""
    old = {"a.md": "alpha", "b.md": "beta"}
    new = {"a.md": "alpha", "c.md": "gamma"}
    old_blob, new_blob, sep_map, first = build_blobs(old, new)

    # union of paths, dedup-ordered
    assert set(sep_map.values()) == {"a.md", "b.md", "c.md"}
    assert len(sep_map) == 3, "a file got two sentinels or two files share one"
    assert first == "a.md"

    # each sentinel appears in BOTH blobs (that's what lets it anchor)
    for sentinel in sep_map:
        assert sentinel in old_blob
        assert sentinel in new_blob


def test_sentinel_survives_the_engine():
    """THE load-bearing claim. Inputs DIFFER so the engine actually tokenizes
    and refines (identical inputs hit a trivial-trap and never split). After a
    real diff, every fragment must still land in a real file — no orphans, no
    sentinel debris leaking into content."""
    old = {"a.md": "alpha one\nsecond line here", "b.md": "beta two\nmore text"}
    new = {"a.md": "alpha ONE\nsecond line here", "b.md": "beta two\nmore text"}

    old_blob, new_blob, sep_map, first = build_blobs(old, new)
    blocks = BlockDiffEngine().compute_diff(old_blob, new_blob)
    old_f, new_f = desentinel(blocks, sep_map, first)

    files_seen = {f.file_path for f in old_f} | {f.file_path for f in new_f}
    assert files_seen == {"a.md", "b.md"}, (
        f"a file's content vanished during attribution: got {files_seen}")

    # no raw fence bytes survived into any fragment's content
    for frag in old_f + new_f:
        assert "\ue000" not in frag.content, "sentinel debris leaked into content"
        assert "\ue003" not in frag.content, "sentinel debris leaked into content"


def test_line_of_reports_minus_one_not_a_lie():
    """The OTHER silent liar. _line_of must return -1 for content that isn't
    present verbatim, rather than a plausible-but-wrong line number."""
    from blockdiff.match import _line_of
    content = "line one\nline two\nline three"
    assert _line_of(content, "line two") == 2
    assert _line_of(content, "line one") == 1
    assert _line_of(content, "nonexistent fragment") == -1
