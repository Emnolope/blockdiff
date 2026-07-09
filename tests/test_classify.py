# tests/test_classify.py
#
# match.py does attribution, not judgment. The engine already decided what moved,
# what's noise, and how to resolve near-identical blocks — that verdict arrives
# baked into each fragment's `fixed` flag. classify() only reads those verdicts
# and puts each block back in its file. These tests pin that contract:
#
#     - a proven move (fixed=False, one home per side, differing homes) is
#       recovered as a MovedBlock and appears in NEITHER removed nor added
#     - a '-' becomes removed, a '+' becomes added, untouched
#     - classify invents no pairings of its own: duplicates and ambiguous
#       content stay exactly as the engine left them
#
# The seam is tested on hand-built fragments (facts we control), never through
# the engine, so a test never becomes hostage to the engine's legitimate freedom
# to anchor or not anchor a given block.

from blockdiff.match import classify, TaggedFragment, MovedBlock, ResultBlock


def _old(path, kind, content, fixed=None):
    return TaggedFragment(path, kind, "old", fixed, content)


def _new(path, kind, content, fixed=None):
    return TaggedFragment(path, kind, "new", fixed, content)


def test_proven_move_is_recovered_and_not_double_counted():
    """A '=' block the engine marked fixed=False on both sides, with a single
    home each and differing homes, is the ONLY path to a move. It becomes one
    MovedBlock with correct FROM/TO and leaks into neither removed nor added."""
    old_frags = [_old("a.md", "=", "the unique anchor line", fixed=False)]
    new_frags = [_new("b.md", "=", "the unique anchor line", fixed=False)]
    old_files = {"a.md": "the unique anchor line"}
    new_files = {"b.md": "the unique anchor line"}

    removed, added, moved = classify(old_frags, new_frags, old_files, new_files)

    assert len(moved) == 1
    assert moved[0].source_file == "a.md"
    assert moved[0].target_file == "b.md"
    assert moved[0].content == "the unique anchor line"
    assert removed == [], "a proven move leaked into removed"
    assert added == [], "a proven move leaked into added"


def test_move_line_numbers_are_recovered():
    """FROM/TO line numbers come from locating the content in each file, not
    from a running offset. A block sitting on line 3 of its source and line 1
    of its target reports exactly that."""
    old_frags = [_old("a.md", "=", "moved paragraph", fixed=False)]
    new_frags = [_new("b.md", "=", "moved paragraph", fixed=False)]
    old_files = {"a.md": "first\nsecond\nmoved paragraph"}
    new_files = {"b.md": "moved paragraph\nrest"}

    _, _, moved = classify(old_frags, new_frags, old_files, new_files)

    assert moved[0].source_line == 3
    assert moved[0].target_line == 1


def test_fixed_block_is_not_a_move():
    """A '=' block the engine left stationary (fixed=True) stays put. It is
    neither a move nor a change, so it appears in nothing."""
    old_frags = [_old("a.md", "=", "stationary line", fixed=True)]
    new_frags = [_new("a.md", "=", "stationary line", fixed=True)]
    old_files = {"a.md": "stationary line"}
    new_files = {"a.md": "stationary line"}

    removed, added, moved = classify(old_frags, new_frags, old_files, new_files)

    assert moved == []
    assert removed == []
    assert added == []


def test_same_file_reorder_is_not_a_move():
    """fixed=False alone isn't enough — a move requires the homes to DIFFER. A
    block that moved within one file has the same home on both sides and must
    not be reported as a cross-file move."""
    old_frags = [_old("a.md", "=", "shuffled line", fixed=False)]
    new_frags = [_new("a.md", "=", "shuffled line", fixed=False)]
    old_files = {"a.md": "shuffled line"}
    new_files = {"a.md": "shuffled line"}

    _, _, moved = classify(old_frags, new_frags, old_files, new_files)

    assert moved == [], "a within-file reorder was reported as a cross-file move"


def test_plain_delete_is_removed():
    """A '-' fragment becomes a ResultBlock in removed, with its file and line,
    and touches nothing else."""
    old_frags = [_old("doc.md", "-", "gone forever")]
    new_frags = []
    old_files = {"doc.md": "keep this\ngone forever"}
    new_files = {"doc.md": "keep this"}

    removed, added, moved = classify(old_frags, new_frags, old_files, new_files)

    assert len(removed) == 1
    assert removed[0].file_path == "doc.md"
    assert removed[0].content == "gone forever"
    assert removed[0].start_line == 2
    assert added == []
    assert moved == []


def test_plain_add_is_added():
    """A '+' fragment becomes a ResultBlock in added, symmetric to delete."""
    old_frags = []
    new_frags = [_new("doc.md", "+", "brand new")]
    old_files = {"doc.md": "existing"}
    new_files = {"doc.md": "existing\nbrand new"}

    removed, added, moved = classify(old_frags, new_frags, old_files, new_files)

    assert len(added) == 1
    assert added[0].file_path == "doc.md"
    assert added[0].content == "brand new"
    assert added[0].start_line == 2
    assert removed == []
    assert moved == []


def test_short_structural_line_survives_as_removed():
    """A short line carries no size privilege here — gating is the engine's job
    and it's soft. Whatever the engine hands classify() as a '-' is reported.
    A lone delimiter deleted from a file must show up, not vanish."""
    old_frags = [_old("doc.md", "-", "# [[splitter]]")]
    new_frags = []
    old_files = {"doc.md": "# [[splitter]]"}
    new_files = {}

    removed, added, moved = classify(old_frags, new_frags, old_files, new_files)

    assert any(r.content == "# [[splitter]]" for r in removed), \
        "a short structural line was swallowed instead of reported as removed"
    assert added == []
    assert moved == []


def test_ambiguous_move_falls_through_to_add_remove():
    """When proven-moved content has more than one home on a side, WHICH copy
    went where is unknowable, so _sole_home omits it and no move is claimed.
    Here the same content is fixed=False in two old files and one new file: the
    source is ambiguous, so classify refuses to pair and reports honestly."""
    dup = "ambiguous block"
    old_frags = [
        _old("a.md", "=", dup, fixed=False),
        _old("b.md", "=", dup, fixed=False),
    ]
    new_frags = [_new("c.md", "=", dup, fixed=False)]
    old_files = {"a.md": dup, "b.md": dup}
    new_files = {"c.md": dup}

    removed, added, moved = classify(old_frags, new_frags, old_files, new_files)

    assert moved == [], "ambiguous source was guessed into a move"


def test_classify_invents_no_pairings():
    """The load-bearing negative. Byte-identical content arrives purely as a '-'
    and a '+' (the engine did NOT anchor it as a move). classify must not pair
    them itself — no Counter, no positional matching. They stay add + remove."""
    text = "identical but unanchored"
    old_frags = [_old("a.md", "-", text)]
    new_frags = [_new("b.md", "+", text)]
    old_files = {"a.md": text}
    new_files = {"b.md": text}

    removed, added, moved = classify(old_frags, new_frags, old_files, new_files)

    assert moved == [], "classify paired an add+remove into a move on its own"
    assert len(removed) == 1 and removed[0].file_path == "a.md"
    assert len(added) == 1 and added[0].file_path == "b.md"


def test_empty_input_is_empty_output():
    """No fragments in, three empty lists out. No crash on the trivial case."""
    removed, added, moved = classify([], [], {}, {})
    assert removed == []
    assert added == []
    assert moved == []


def test_missing_file_content_yields_minus_one_line():
    """If a fragment's file isn't in the content map, line lookup returns -1
    rather than a fabricated number. The block is still reported."""
    old_frags = [_old("ghost.md", "-", "orphaned content")]
    new_frags = []

    removed, added, moved = classify(old_frags, new_frags, {}, {})

    assert len(removed) == 1
    assert removed[0].file_path == "ghost.md"
    assert removed[0].start_line == -1
