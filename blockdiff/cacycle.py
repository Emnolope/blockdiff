"""
BlockDiff Engine Core 
=====================
A highly structured, data-only block move detection diff engine.

Credits & Attribution:
- Original JavaScript Author: Cacycle (WikEd Diff)
- Prompt Engineering & Architecture: Emnolope
- Python Transpilation & Refactoring: Gemini 3.1 Pro Preview / AI Assistant

Outputs a clean array of structured `DiffBlock`s describing moves, 
inserts, deletes, and matches. Ready to be serialized to JSON and 
consumed by a modern frontend.
"""
import re
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple


# --- Data Structures ---

@dataclass
class TokenInfo:
    """One token in the doubly-linked list."""
    token: str
    prev: Optional[int] = None
    next: Optional[int] = None
    link: Optional[int] = None
    number: Optional[int] = None
    unique: bool = False
    char_offset: Optional[int] = None
    # Caller-pinned state. Set by _apply_prelinks BEFORE block detection.
    #   anchor=True            -> pinned stationary (ground frame). fixed=True.
    #   prelink_moved=True     -> pinned as a caller-asserted MOVE. The engine
    #                             did not find this; a prior engine did. Link it,
    #                             believe it, diff around it, never re-litigate.
    anchor: bool = False
    prelink_moved: bool = False


@dataclass
class DiffBlock:
    type: str
    text: str
    old_number: Optional[int] = None
    new_number: Optional[int] = None
    old_start_token: Optional[int] = None
    count: Optional[int] = None
    unique: bool = False
    words: int = 0
    chars: int = 0
    section: Optional[int] = None
    group: Optional[int] = None
    fixed: Optional[bool] = None
    moved_to_group: Optional[int] = None
    old_char: Optional[int] = None
    new_char: Optional[int] = None
    old_block_idx: Optional[int] = None
    new_block_idx: Optional[int] = None
    # Caller-pinned classification, carried from tokens up to blocks.
    is_anchor: bool = False        # stationary ground frame (do not move it)
    is_prelink_moved: bool = False # caller-asserted move (do not re-litigate it)

@dataclass
class DiffGroup:
    old_number: int
    block_start: int
    block_end: int
    unique: bool
    max_words: int
    words: int
    chars: int
    fixed: bool
    moved_from_group: Optional[int] = None
    color_id: Optional[int] = None
    is_anchor: bool = False          # singleton ground-frame group
    new_number: Optional[int] = None # new-order pos of first block (for spine DP)

# --- Regex Setup ---
def _parse_unicode_ranges(s: str) -> str:
    """Translates JS hex unicode ranges into Python-compatible characters."""
    return re.sub(r'([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), s)

_JS_UNICODE_HEX = (
    '00AA00B500BA00C0-00D600D8-00F600F8-02C102C6-02D102E0-02E402EC02EE0370-037403760377037A-'
    '037D03860388-038A038C038E-03A103A3-03F503F7-0481048A-05270531-055605590561-058705D0-05EA'
    '05F0-05F20620-064A066E066F0671-06D306D506E506E606EE06EF06FA-06FC06FF07100712-072F074D-'
    '07A507B107CA-07EA07F407F507FA0800-0815081A082408280840-085808A008A2-08AC0904-0939093D'
    '09500958-09610971-09770979-097F0985-098C098F09900993-09A809AA-09B009B209B6-09B909BD09CE'
    '09DC09DD09DF-09E109F009F10A05-0A0A0A0F0A100A13-0A280A2A-0A300A320A330A350A360A380A39'
    '0A59-0A5C0A5E0A72-0A740A85-0A8D0A8F-0A910A93-0AA80AAA-0AB00AB20AB30AB5-0AB90ABD0AD00AE0'
    '0AE10B05-0B0C0B0F0B100B13-0B280B2A-0B300B320B330B35-0B390B3D0B5C0B5D0B5F-0B610B710B83'
    '0B85-0B8A0B8E-0B900B92-0B950B990B9A0B9C0B9E0B9F0BA30BA40BA8-0BAA0BAE-0BB90BD00C05-0C0C'
    '0C0E-0C100C12-0C280C2A-0C330C35-0C390C3D0C580C590C600C610C85-0C8C0C8E-0C900C92-0CA80CAA-'
    '0CB30CB5-0CB90CBD0CDE0CE00CE10CF10CF20D05-0D0C0D0E-0D100D12-0D3A0D3D0D4E0D600D610D7A-'
    '0D7F0D85-0D960D9A-0DB10DB3-0DBB0DBD0DC0-0DC60E01-0E300E320E330E40-0E460E810E820E840E87'
    '0E880E8A0E8D0E94-0E970E99-0E9F0EA1-0EA30EA50EA70EAA0EAB0EAD-0EB00EB20EB30EBD0EC0-0EC4'
    '0EC60EDC-0EDF0F000F40-0F470F49-0F6C0F88-0F8C1000-102A103F1050-1055105A-105D106110651066'
    '106E-10701075-1081108E10A0-10C510C710CD10D0-10FA10FC-1248124A-124D1250-12561258125A-125D'
    '1260-1288128A-128D1290-12B012B2-12B512B8-12BE12C012C2-12C512C8-12D612D8-13101312-1315'
    '1318-135A1380-138F13A0-13F41401-166C166F-167F1681-169A16A0-16EA1700-170C170E-17111720-'
    '17311740-17511760-176C176E-17701780-17B317D717DC1820-18771880-18A818AA18B0-18F51900-191C'
    '1950-196D1970-19741980-19AB19C1-19C71A00-1A161A20-1A541AA71B05-1B331B45-1B4B1B83-1BA0'
    '1BAE1BAF1BBA-1BE51C00-1C231C4D-1C4F1C5A-1C7D1CE9-1CEC1CEE-1CF11CF51CF61D00-1DBF1E00-1F15'
    '1F18-1F1D1F20-1F451F48-1F4D1F50-1F571F591F5B1F5D1F5F-1F7D1F80-1FB41FB6-1FBC1FBE1FC2-1FC4'
    '1FC6-1FCC1FD0-1FD31FD6-1FDB1FE0-1FEC1FF2-1FF41FF6-1FFC2071207F2090-209C21022107210A-2113'
    '21152119-211D212421262128212A-212D212F-2139213C-213F2145-2149214E218321842C00-2C2E2C30-'
    '2C5E2C60-2CE42CEB-2CEE2CF22CF32D00-2D252D272D2D2D30-2D672D6F2D80-2D962DA0-2DA62DA8-2DAE'
    '2DB0-2DB62DB8-2DBE2DC0-2DC62DC8-2DCE2DD0-2DD62DD8-2DDE2E2F300530063031-3035303B303C3041-'
    '3096309D-309F30A1-30FA30FC-30FF3105-312D3131-318E31A0-31BA31F0-31FF3400-4DB54E00-9FCC'
    'A000-A48CA4D0-A4FDA500-A60CA610-A61FA62AA62BA640-A66EA67F-A697A6A0-A6E5A717-A71FA722-'
    'A788A78B-A78EA790-A793A7A0-A7AAA7F8-A801A803-A805A807-A80AA80C-A822A840-A873A882-A8B3'
    'A8F2-A8F7A8FBA90A-A925A930-A946A960-A97CA984-A9B2A9CFAA00-AA28AA40-AA42AA44-AA4BAA60-'
    'AA76AA7AAA80-AAAFAAB1AAB5AAB6AAB9-AABDAAC0AAC2AADB-AADDAAE0-AAEAAAF2-AAF4AB01-AB06AB09-'
    'AB0EAB11-AB16AB20-AB26AB28-AB2EABC0-ABE2AC00-D7A3D7B0-D7C6D7CB-D7FBF900-FA6DFA70-FAD9'
    'FB00-FB06FB13-FB17FB1DFB1F-FB28FB2A-FB36FB38-FB3CFB3EFB40FB41FB43FB44FB46-FBB1FBD3-FD3D'
    'FD50-FD8FFD92-FDC7FDF0-FDFBFE70-FE74FE76-FEFCFF21-FF3AFF41-FF5AFF66-FFBEFFC2-FFC7FFCA-'
    'FFCFFFD2-FFD7FFDA-FFDC'
)

REG_EXP_LETTERS = 'a-zA-Z0-9' + _parse_unicode_ranges(_JS_UNICODE_HEX)
REG_EXP_NEWLINES = _parse_unicode_ranges('00852028')
REG_EXP_NEWLINES_ALL = '\n\r' + REG_EXP_NEWLINES
REG_EXP_BLANKS = ' \t\x0b' + _parse_unicode_ranges('2000-200B202F205F3000')
REG_EXP_FULL_STOPS = _parse_unicode_ranges('058906D40701070209640DF41362166E180318092CF92CFE2E3C3002A4FFA60EA6F3FE52FF0EFF61')
REG_EXP_NEW_PARA = '\f' + _parse_unicode_ranges('2029')
REG_EXP_EXCLAMATION = _parse_unicode_ranges('01C301C301C3055C055C07F919441944203C203C20482048FE15FE57FF01')
REG_EXP_QUESTION = _parse_unicode_ranges('037E055E061F13671945204720492CFA2CFB2E2EA60FA6F7FE56FF1F')

RE_SPLIT = {
    'paragraph': re.compile(rf'(\r\n|\n|\r){{2,}}|[{REG_EXP_NEW_PARA}]'),
    'line': re.compile(rf'\r\n|\n|\r|[{REG_EXP_NEWLINES_ALL}]'),
    'sentence': re.compile(rf'[{REG_EXP_BLANKS}].*?[.!?:;{REG_EXP_FULL_STOPS}{REG_EXP_EXCLAMATION}{REG_EXP_QUESTION}]+(?=[{REG_EXP_BLANKS}]|$)'),
    # NOTE: this is an f-string, so every LITERAL regex brace is doubled ({{ }})
    # to survive f-string parsing and emerge as a single brace for the regex.
    # {REG_EXP_LETTERS}-style single braces are real interpolations and stay single.
    'chunk': re.compile(rf'\[\[[^\[\]\n]+\]\]|\{{\{{[^{{\}}\n]+\}}\}}|\[[^\[\]\n]+\]|<\/?[^<>[\]{{\}}\n]+>|\[\[[^\[\]\|\n]+\]\]\||\{{\{{[^\{{\}}\|\n]+\||((https?:|)\/\/)[^\x00-\x20\s"\[\]\x7f]+'),
    'word': re.compile(rf'(\w+|[_{REG_EXP_LETTERS}])+([\'’][_{REG_EXP_LETTERS}]*)*|\[\[|\]\]|\{{\{{|\}}\}}|&\w+;|\'\'\'|\'\'|==+|\{{\||\|\}}|\|-|.'),
    'character': re.compile(r'[^\n\r\u2028\u2029]')
}

RE_BLANK_ONLY = re.compile(rf'[^{REG_EXP_BLANKS}{REG_EXP_NEWLINES_ALL}{REG_EXP_NEW_PARA}]')
RE_SLIDESTOP = re.compile(rf'[{REG_EXP_NEWLINES_ALL}{REG_EXP_NEW_PARA}]$')
RE_SLIDEBORDER = re.compile(rf'[{REG_EXP_BLANKS}]$')
RE_COUNT_WORDS = re.compile(rf'(\w+|[_{REG_EXP_LETTERS}])+([\'’][_{REG_EXP_LETTERS}]*)*')
RE_COUNT_CHUNKS = RE_SPLIT['chunk']


# --- Core Logic ---

class DiffText:
    """Manages the tokenization and parsing of a single text version."""
    def __init__(self, text: str):
        # Normalize line endings
        self.text = str(text).replace('\r\n', '\n').replace('\r', '\n')
        self.tokens: List[TokenInfo] = []
        self.first: Optional[int] = None
        self.last: Optional[int] = None
        
        # Counter inherently handles initial zero-values
        self.words: Counter[str] = Counter()
        
        self._count_words(RE_COUNT_WORDS)
        self._count_words(RE_COUNT_CHUNKS)

    def _count_words(self, regex: re.Pattern):
        """Populates the word frequency counter for uniqueness checks."""
        self.words.update(match.group(0) for match in regex.finditer(self.text))

    def split_text(self, level: str, token_idx: Optional[int] = None):
        """Progressively splits the text or a specific token down to a more granular level."""
        prev_idx, next_idx = None, None
        current = len(self.tokens)
        first_idx = current

        text_to_split = self.text if token_idx is None else self.tokens[token_idx].token
        if token_idx is not None:
            prev_idx = self.tokens[token_idx].prev
            next_idx = self.tokens[token_idx].next

        number = 0
        split_chunks = []
        last_index = 0

        # Emulates JavaScript's `regExp.exec()` moving window
        for match in RE_SPLIT[level].finditer(text_to_split):
            if match.start() > last_index:
                split_chunks.append(text_to_split[last_index:match.start()])
            split_chunks.append(match.group(0))
            last_index = match.end()

        if last_index < len(text_to_split):
            split_chunks.append(text_to_split[last_index:])

        # Build doubly linked list nodes out of the splits
        for chunk in split_chunks:
            self.tokens.append(TokenInfo(token=chunk, prev=prev_idx))
            if prev_idx is not None:
                self.tokens[prev_idx].next = current
            prev_idx = current
            current += 1
            number += 1

        if number > 0 and token_idx is not None:
            if prev_idx is not None:
                self.tokens[prev_idx].next = next_idx
            if next_idx is not None:
                self.tokens[next_idx].prev = prev_idx

        # Update absolute start/end pointers if we are overwriting boundaries
        if number > 0:
            if token_idx is None:
                self.first = 0
                self.last = prev_idx
            else:
                if token_idx == self.first:
                    self.first = first_idx
                if token_idx == self.last:
                    self.last = prev_idx

    def split_refine(self, level: str):
        """Refines only unresolved (unlinked) tokens by breaking them down further."""
        i = self.first
        while i is not None:
            if self.tokens[i].link is None:
                self.split_text(level, i)
            i = self.tokens[i].next

    def enumerate_tokens(self):
        """Assigns sequential index numbers AND character offsets to the final
        tokens. char_offset is a running sum of token lengths in stream order,
        so it equals the token's exact character position in the concatenated
        blob — the same order every block-builder concatenates text in, so the
        two can never drift."""
        number = 0
        offset = 0
        i = self.first
        while i is not None:
            self.tokens[i].number = number
            self.tokens[i].char_offset = offset
            number += 1
            offset += len(self.tokens[i].token)
            i = self.tokens[i].next


class BlockDiffEngine:
    """
    Core algorithmic engine. 
    Excludes all presentation (DOM/HTML) elements to return purely typed data structures.
    """
    # (name, type, default, help). Downstream (CLI, MCP) reads this and builds
    # its interface from it. Add a knob to __init__? Add its row here. One spot.
    TUNABLE_PARAMS = [
        ("char_diff",        bool, True,  "Refine diffs down to the character level."),
        ("repeated_diff",    bool, True,  "Re-diff across matched crossovers repeatedly."),
        ("recursive_diff",   bool, True,  "Recurse into gaps between matched anchors."),
        ("recursion_max",    int,  10,    "Max recursion depth for recursive_diff."),
        ("unlink_blocks",    bool, True,  "Drop short non-unique '=' fragments as +/- noise."),
        ("unlink_max",       int,  5,     "Max unlink passes."),
        ("block_min_length", int,  3,     "Min token length before a block counts as real."),
        # --- keystroke-energy knobs (spine selection in _find_max_path) ---
        # These three define the ONLY energy metric. All ergonomic constants,
        # zero similarity fuzz. See _find_max_path for how they're used.
        ("w_char",     float, 1.0, "Weight of one kept (stationary) character on the spine."),
        ("move_base",  float, 4.0, "Flat cost of one cut-paste move (Ctrl-X/Ctrl-V ~= 4 keys)."),
        ("move_log_k", float, 1.0, "How fast selection effort grows with block size (log scale)."),
    ]
    def __init__(self, 
                 char_diff: bool = True, 
                 repeated_diff: bool = True, 
                 recursive_diff: bool = True, 
                 recursion_max: int = 10, 
                 unlink_blocks: bool = True, 
                 unlink_max: int = 5, 
                 block_min_length: int = 3,
                 w_char: float = 1.0,
                 move_base: float = 4.0,
                 move_log_k: float = 1.0):
                 
        self.char_diff = char_diff
        self.repeated_diff = repeated_diff
        self.recursive_diff = recursive_diff
        self.recursion_max = recursion_max
        self.unlink_blocks = unlink_blocks
        self.unlink_max = unlink_max
        self.block_min_length = block_min_length

        # Keystroke-energy knobs. Read only by _find_max_path.
        self.w_char = w_char
        self.move_base = move_base
        self.move_log_k = move_log_k

        self.new_text: Optional[DiffText] = None
        self.old_text: Optional[DiffText] = None
        
        self.symbols: Dict[str, Any] = {'token': [], 'hashTable': {}, 'linked': False}
        self.borders_down: List[Tuple[int, int]] = []
        self.borders_up: List[Tuple[int, int]] = []
        
        self.blocks: List[DiffBlock] = []
        self.groups: List[DiffGroup] = []
        self.sections: List[Dict[str, int]] = []
        
        self.max_words = 0

    def compute_diff(self, old_string: str, new_string: str,
                     prelinks=None) -> List[DiffBlock]:
        """Main entry point. old_string -> new_string, returns typed DiffBlocks.

        prelinks: OPTIONAL list of caller-asserted correspondences. Each is a
        tuple (old_span, new_span, kind) where old_span/new_span are
        (start_char, end_char) half-open character ranges into old_string /
        new_string respectively, and kind is one of:

            "stationary" -> the two ranges are the SAME content in the SAME
                            logical place. Pin them to the ground frame: they
                            become their own '=' blocks, their own groups,
                            forced fixed=True, exempt from the move DP and from
                            unlink. THIS is how a caller (e.g. match.py's
                            sentinels) nails a coordinate frame. The engine
                            never inspects the content — it trusts the caller.

            "moved"      -> the two ranges are the SAME content in a DIFFERENT
                            place, as ALREADY DETERMINED BY ANOTHER PASS/ENGINE.
                            The engine force-links them, marks them a move it is
                            NOT allowed to re-litigate, and diffs only around
                            them. THIS is diff warm-starting / engine chaining:
                            engine #1's output becomes engine #2's input, so the
                            expensive pass never re-examines what the cheap pass
                            already proved. (The 150MB-change-one-line dream:
                            pin everything identical, diff only the residual.)

        prelinks=None -> EXACT legacy behavior, total no-op. Every new branch is
        gated on a prelink flag that is False when no prelinks are supplied.

        NOTE ON COORDINATES: spans are CHARACTER offsets, not token indices,
        because tokenization happens INSIDE this method — the caller cannot know
        token numbers in advance. We resolve spans to tokens ourselves, after
        enumerate_tokens stamps char_offset on every token.
        """
        self.blocks.clear()
        self.groups.clear()
        self.sections.clear()
        self.max_words = 0

        # Trivial Trap 1: Identical
        if old_string == new_string:
            return [DiffBlock(
                type='=', text=new_string,
                words=len(list(RE_COUNT_WORDS.finditer(new_string))),
                chars=len(new_string))]

        # Trivial Trap 2: Old empty
        if not old_string or (old_string == '\n' and new_string.endswith('\n')):
            return [DiffBlock(
                type='+', text=new_string,
                words=len(list(RE_COUNT_WORDS.finditer(new_string))),
                chars=len(new_string))]

        # Trivial Trap 3: New empty
        if not new_string or (new_string == '\n' and old_string.endswith('\n')):
            return [DiffBlock(
                type='-', text=old_string,
                words=len(list(RE_COUNT_WORDS.finditer(old_string))),
                chars=len(old_string))]

        self.new_text = DiffText(new_string)
        self.old_text = DiffText(old_string)

        # 1. Progressive split and diff phases (Heckel heuristic)
        self._run_split_and_diff('paragraph')
        self._run_split_and_diff('line', refine=True)
        self._run_split_and_diff('sentence', refine=True)
        self._run_split_and_diff('chunk', refine=True)

        self.new_text.split_refine('word')
        self.old_text.split_refine('word')
        self._calculate_diff('word', recurse=True)

        self._slide_gaps(self.new_text, self.old_text)
        self._slide_gaps(self.old_text, self.new_text)

        # 2. Character refinement (Optional)
        if self.char_diff:
            self._split_refine_chars()
            self._calculate_diff('character', recurse=True)
            self._slide_gaps(self.new_text, self.old_text)
            self._slide_gaps(self.old_text, self.new_text)

        # 3. Enumerate, THEN apply caller prelinks, THEN detect blocks.
        #    Order matters: _apply_prelinks needs char_offset (from enumerate)
        #    and must run before _detect_blocks (which reads the pinned flags).
        self.new_text.enumerate_tokens()
        self.old_text.enumerate_tokens()
        self._apply_prelinks(prelinks)

        self._detect_blocks()

        return self.blocks


    def _tokens_in_span(self, text_obj: 'DiffText', start: int, end: int):
        """Yield token indices whose char_offset falls in [start, end). A pinned
        span is almost always a RUN of tokens (e.g. a sentinel tokenizes into
        fence-chars + hex + fence-chars), never a single one — which is exactly
        why matching by CONTENT STRING was abandoned: there is no single token
        to match. We match by authored position instead."""
        i = text_obj.first
        while i is not None:
            off = text_obj.tokens[i].char_offset
            if off is not None and start <= off < end:
                yield i
            i = text_obj.tokens[i].next

    def _apply_prelinks(self, prelinks):
        """Turn caller-asserted (old_span, new_span, kind) correspondences into
        per-token pins. Pure no-op when prelinks is falsy.

        stationary: mark every token in either span as anchor=True. Downstream,
        _get_same_blocks refuses to fuse anchor runs with content, _get_groups
        makes them singleton fixed groups, _set_fixed refuses to un-fix them,
        _unlink_blocks refuses to eat them.

        moved: force a LINK between the old-span tokens and the new-span tokens
        positionally, and mark both sides prelink_moved=True. Force-linking means
        the normal matcher treats them as already-matched identical content and
        will not tear them apart or re-decide them; marking them moved means we
        carried a verdict IN rather than computing it. We overwrite any link the
        engine may have already guessed for these tokens, because the caller's
        assertion outranks the engine's guess — that is the whole point of a
        warm start.

        HONEST LIMITATION (read before trusting 'moved' in anger): stationary is
        proven by the failing whole-body-move tests. 'moved' is wired and
        structurally coherent but UNPROVEN against a real second engine. If a
        moved prelink's two spans tokenize to different token COUNTS, we link the
        positional minimum and leave the remainder to the normal matcher — a
        deliberate, safe degradation, not a guarantee of optimality."""
        if not prelinks:
            return

        for old_span, new_span, kind in prelinks:
            o_start, o_end = old_span
            n_start, n_end = new_span
            old_idxs = list(self._tokens_in_span(self.old_text, o_start, o_end))
            new_idxs = list(self._tokens_in_span(self.new_text, n_start, n_end))

            if kind == "stationary":
                for oi in old_idxs:
                    self.old_text.tokens[oi].anchor = True
                for ni in new_idxs:
                    self.new_text.tokens[ni].anchor = True

            elif kind == "moved":
                # Positional force-link. Overwrite prior guesses; caller wins.
                for oi, ni in zip(old_idxs, new_idxs):
                    # Sever any stale links first so we don't leave dangles.
                    old_link = self.old_text.tokens[oi].link
                    if old_link is not None:
                        self.new_text.tokens[old_link].link = None
                    new_link = self.new_text.tokens[ni].link
                    if new_link is not None:
                        self.old_text.tokens[new_link].link = None
                    # Assert the caller's correspondence.
                    self.old_text.tokens[oi].link = ni
                    self.new_text.tokens[ni].link = oi
                    self.old_text.tokens[oi].prelink_moved = True
                    self.new_text.tokens[ni].prelink_moved = True
                    self.old_text.tokens[oi].unique = True
                    self.new_text.tokens[ni].unique = True

            else:
                raise ValueError(
                    f"prelink kind must be 'stationary' or 'moved', got {kind!r}")

    def _run_split_and_diff(self, level: str, refine: bool = False):
        """Helper to invoke a split cycle followed by a diff pass."""
        if not refine:
            self.new_text.split_text(level)
            self.old_text.split_text(level)
        else:
            self.new_text.split_refine(level)
            self.old_text.split_refine(level)
        self._calculate_diff(level)

    def _calculate_diff(self, level: str, recurse: bool = False, repeating: bool = False, 
                        new_start: int = None, old_start: int = None, up: bool = False, recursion_level: int = 0):
        """The core Paul Heckel algorithmic matching logic."""
        if new_start is None: new_start = self.new_text.first
        if old_start is None: old_start = self.old_text.first

        if recursion_level == 0 and not repeating:
            symbols = self.symbols
            borders_down = self.borders_down
            borders_up = self.borders_up
        else:
            symbols = {'token': [], 'hashTable': {}, 'linked': False}
            borders_down: List[Tuple[int, int]] = []
            borders_up: List[Tuple[int, int]] = []

        borders_up_next: List[Tuple[int, int]] = []
        borders_down_next: List[Tuple[int, int]] = []

        # Pass 1 & 2: Parse new and old text into symbol tables
        for text_obj, is_new in [(self.new_text, True), (self.old_text, False)]:
            idx = new_start if is_new else old_start
            while idx is not None:
                if text_obj.tokens[idx].link is None:
                    token = text_obj.tokens[idx].token
                    if token not in symbols['hashTable']:
                        symbols['hashTable'][token] = len(symbols['token'])
                        sym_entry = {'newCount': 0, 'oldCount': 0, 'newToken': None, 'oldToken': None}
                        if is_new:
                            sym_entry.update({'newCount': 1, 'newToken': idx})
                        else:
                            sym_entry.update({'oldCount': 1, 'oldToken': idx})
                        symbols['token'].append(sym_entry)
                    else:
                        hash_idx = symbols['hashTable'][token]
                        if is_new:
                            symbols['token'][hash_idx]['newCount'] += 1
                        else:
                            symbols['token'][hash_idx]['oldCount'] += 1
                            symbols['token'][hash_idx]['oldToken'] = idx
                elif recursion_level > 0:
                    break
                idx = text_obj.tokens[idx].next if not up else text_obj.tokens[idx].prev

        # Pass 3: Connect unique tokens
        for sym in symbols['token']:
            if sym['newCount'] == 1 and sym['oldCount'] == 1:
                new_t = sym['newToken']
                old_t = sym['oldToken']
                if self.new_text.tokens[new_t].link is None:
                    if RE_BLANK_ONLY.search(self.new_text.tokens[new_t].token):
                        self.new_text.tokens[new_t].link = old_t
                        self.old_text.tokens[old_t].link = new_t
                        symbols['linked'] = True
                        
                        # Tuples appended for memory efficiency
                        borders_down.append((new_t, old_t))
                        borders_up.append((new_t, old_t))

                        if recursion_level == 0:
                            unique = False
                            if level == 'character':
                                unique = True
                            else:
                                t_str = self.new_text.tokens[new_t].token
                                words = [m.group(0) for m in RE_COUNT_WORDS.finditer(t_str)]
                                words.extend([m.group(0) for m in RE_COUNT_CHUNKS.finditer(t_str)])
                                
                                if len(words) >= self.block_min_length:
                                    unique = True
                                else:
                                    for w in words:
                                        # Use Counter's get to safely check dictionary presence
                                        if self.old_text.words.get(w) == 1 and self.new_text.words.get(w) == 1:
                                            unique = True
                                            break
                            if unique:
                                self.new_text.tokens[new_t].unique = True
                                self.old_text.tokens[old_t].unique = True

        if symbols['linked']:
            # Pass 4 & 5: Connect adjacent identical tokens
            for b_list, dir_attr, b_next in [(borders_down, 'next', borders_down_next), (borders_up, 'prev', borders_up_next)]:
                for i, j in b_list:
                    i_match, j_match = i, j
                    i, j = getattr(self.new_text.tokens[i], dir_attr), getattr(self.old_text.tokens[j], dir_attr)
                    while i is not None and j is not None and self.new_text.tokens[i].link is None and self.old_text.tokens[j].link is None:
                        if self.new_text.tokens[i].token == self.old_text.tokens[j].token:
                            self.new_text.tokens[i].link = j
                            self.old_text.tokens[j].link = i
                        else:
                            b_next.append((i_match, j_match))
                            break
                        i_match, j_match = i, j
                        i, j = getattr(self.new_text.tokens[i], dir_attr), getattr(self.old_text.tokens[j], dir_attr)

            # Connect boundaries (start and end)
            if recursion_level == 0 and not repeating:
                # Top down
                i, j = self.new_text.first, self.old_text.first
                i_m, j_m = None, None
                while (i is not None and j is not None and 
                       self.new_text.tokens[i].link is None and self.old_text.tokens[j].link is None and 
                       self.new_text.tokens[i].token == self.old_text.tokens[j].token):
                    self.new_text.tokens[i].link = j
                    self.old_text.tokens[j].link = i
                    i_m, j_m = i, j
                    i, j = self.new_text.tokens[i].next, self.old_text.tokens[j].next
                if i_m is not None: 
                    borders_down_next.append((i_m, j_m))

                # Bottom up
                i, j = self.new_text.last, self.old_text.last
                i_m, j_m = None, None
                while (i is not None and j is not None and 
                       self.new_text.tokens[i].link is None and self.old_text.tokens[j].link is None and 
                       self.new_text.tokens[i].token == self.old_text.tokens[j].token):
                    self.new_text.tokens[i].link = j
                    self.old_text.tokens[j].link = i
                    i_m, j_m = i, j
                    i, j = self.new_text.tokens[i].prev, self.old_text.tokens[j].prev
                if i_m is not None: 
                    borders_up_next.append((i_m, j_m))

            # Merge matched boundaries
            if recursion_level == 0 and not repeating:
                self.borders_down = borders_down_next
                self.borders_up = borders_up_next
            else:
                self.borders_down.extend(borders_down_next)
                self.borders_up.extend(borders_up_next)

            # Repeated diffs against cross-overs
            if not repeating and self.repeated_diff:
                self._calculate_diff(level, recurse, True, new_start, old_start, up, recursion_level)

            # Recursive diffs against cross-overs
            if recurse and self.recursive_diff and recursion_level < self.recursion_max:
                for b_list, dir_attr, is_up in [(borders_down_next, 'next', False), (borders_up_next, 'prev', True)]:
                    for i_idx, j_idx in b_list:
                        i = getattr(self.new_text.tokens[i_idx], dir_attr)
                        j = getattr(self.old_text.tokens[j_idx], dir_attr)
                        if i is not None and j is not None and self.new_text.tokens[i].link is None and self.old_text.tokens[j].link is None:
                            self._calculate_diff(level, recurse, False, i, j, is_up, recursion_level + 1)

    def _slide_gaps(self, text_obj: DiffText, text_linked: DiffText):
        """Moves gaps with ambiguous identical fronts to the last newline border or word border."""
        i = text_obj.first
        gap_start = None
        while i is not None:
            if gap_start is None and text_obj.tokens[i].link is None:
                gap_start = i
            elif gap_start is not None and text_obj.tokens[i].link is not None:
                gap_front, gap_back = gap_start, text_obj.tokens[i].prev
                
                # Slide down
                front, back = gap_front, text_obj.tokens[gap_back].next
                if (front is not None and back is not None and 
                    text_obj.tokens[front].link is None and 
                    text_obj.tokens[back].link is not None and 
                    text_obj.tokens[front].token == text_obj.tokens[back].token):
                    
                    text_obj.tokens[front].link = text_obj.tokens[back].link
                    text_linked.tokens[text_obj.tokens[front].link].link = front
                    text_obj.tokens[back].link = None
                    gap_front = text_obj.tokens[gap_front].next
                    gap_back = text_obj.tokens[gap_back].next

                # Slide up
                front, back = text_obj.tokens[gap_front].prev, gap_back
                gap_front_blank_test = bool(RE_SLIDEBORDER.search(text_obj.tokens[gap_front].token))
                front_stop = front
                
                if text_obj.tokens[back].link is None:
                    while (front is not None and back is not None and 
                           text_obj.tokens[front].link is not None and 
                           text_obj.tokens[front].token == text_obj.tokens[back].token):
                        
                        if bool(RE_SLIDESTOP.search(text_obj.tokens[front].token)):
                            front_stop = front
                            break
                        if bool(RE_SLIDEBORDER.search(text_obj.tokens[front].token)) != gap_front_blank_test:
                            front_stop = front
                            
                        front, back = text_obj.tokens[front].prev, text_obj.tokens[back].prev

                # Actually slide up to stop
                front, back = text_obj.tokens[gap_front].prev, gap_back
                while (front is not None and back is not None and front != front_stop and 
                       text_obj.tokens[front].link is not None and 
                       text_obj.tokens[back].link is None and 
                       text_obj.tokens[front].token == text_obj.tokens[back].token):
                    
                    text_obj.tokens[back].link = text_obj.tokens[front].link
                    text_linked.tokens[text_obj.tokens[back].link].link = back
                    text_obj.tokens[front].link = None
                    front, back = text_obj.tokens[front].prev, text_obj.tokens[back].prev
                    
                gap_start = None
            i = text_obj.tokens[i].next

    def _split_refine_chars(self):
        """Splits tokens into characters across unresolved regions to find tighter matches."""
        gaps = []
        gap = None
        i, j = self.new_text.first, self.old_text.first

        # Collect gap metrics
        while i is not None:
            new_link = self.new_text.tokens[i].link
            old_link = self.old_text.tokens[j].link if j is not None else None

            if gap is None and new_link is None and old_link is None:
                gap = len(gaps)
                gaps.append({'newFirst': i, 'newLast': i, 'newTokens': 1, 'oldFirst': j, 'oldLast': j, 'oldTokens': 0, 'charSplit': None})
            elif gap is not None and new_link is None:
                gaps[gap]['newLast'] = i
                gaps[gap]['newTokens'] += 1
            elif gap is not None and new_link is not None:
                gap = None

            if new_link is not None:
                j = self.old_text.tokens[new_link].next
            i = self.new_text.tokens[i].next

        for gap_obj in gaps:
            j = gap_obj['oldFirst']
            while j is not None and self.old_text.tokens[j] is not None and self.old_text.tokens[j].link is None:
                gap_obj['oldLast'] = j
                gap_obj['oldTokens'] += 1
                j = self.old_text.tokens[j].next

        # Check thresholds for whether we should split characters
        for gap_obj in gaps:
            char_split = True
            if gap_obj['newTokens'] != gap_obj['oldTokens']:
                if gap_obj['newTokens'] == 1 and gap_obj['oldTokens'] == 3:
                    token = self.new_text.tokens[gap_obj['newFirst']].token
                    token_first = self.old_text.tokens[gap_obj['oldFirst']].token
                    token_last = self.old_text.tokens[gap_obj['oldLast']].token
                    if not token.startswith(token_first) or not token.endswith(token_last):
                        continue
                elif gap_obj['oldTokens'] == 1 and gap_obj['newTokens'] == 3:
                    token = self.old_text.tokens[gap_obj['oldFirst']].token
                    token_first = self.new_text.tokens[gap_obj['newFirst']].token
                    token_last = self.new_text.tokens[gap_obj['newLast']].token
                    if not token.startswith(token_first) or not token.endswith(token_last):
                        continue
                else:
                    continue
                gap_obj['charSplit'] = True
            else:
                i, j = gap_obj['newFirst'], gap_obj['oldFirst']
                while i is not None:
                    new_token = self.new_text.tokens[i].token
                    old_token = self.old_text.tokens[j].token
                    shorter, longer = (new_token, old_token) if len(new_token) < len(old_token) else (old_token, new_token)

                    if len(new_token) != len(old_token):
                        left = right = 0
                        while left < len(shorter) and new_token[left] == old_token[left]: left += 1
                        while right < len(shorter) and new_token[-1 - right] == old_token[-1 - right]: right += 1
                        if left + right != len(shorter):
                            if shorter not in longer:
                                if len(shorter) > 0 and left < len(shorter) / 2 and right < len(shorter) / 2:
                                    char_split = False
                                    break
                    elif new_token != old_token:
                        ident = sum(1 for pos in range(len(shorter)) if shorter[pos] == longer[pos])
                        if len(shorter) > 0 and ident / len(shorter) < 0.49:
                            char_split = False
                            break
                            
                    if i == gap_obj['newLast']: break
                    i, j = self.new_text.tokens[i].next, self.old_text.tokens[j].next
                gap_obj['charSplit'] = char_split

        # Apply the split
        for gap_obj in gaps:
            if gap_obj['charSplit']:
                i, j = gap_obj['newFirst'], gap_obj['oldFirst']
                new_gap_length = i - gap_obj['newLast']
                old_gap_length = j - gap_obj['oldLast']
                
                while i is not None or j is not None:
                    if new_gap_length == old_gap_length and i is not None and j is not None and self.new_text.tokens[i].token == self.old_text.tokens[j].token:
                        self.new_text.tokens[i].link = j
                        self.old_text.tokens[j].link = i
                    else:
                        if i is not None: self.new_text.split_text('character', i)
                        if j is not None: self.old_text.split_text('character', j)
                        
                    if i == gap_obj['newLast']: i = None
                    if j == gap_obj['oldLast']: j = None
                    if i is not None: i = self.new_text.tokens[i].next
                    if j is not None: j = self.old_text.tokens[j].next

    def _detect_blocks(self):
        """Builds contiguous blocks out of linked tokens, detecting moves and dropping noise."""
        self._get_same_blocks()
        self._get_sections()
        self._get_groups()
        self._set_fixed()

        if self.unlink_blocks and self.block_min_length > 0 and self.max_words >= self.block_min_length:
            unlinked = True
            unlink_count = 0
            while unlinked and unlink_count < self.unlink_max:
                unlinked = self._unlink_blocks()
                if unlinked:
                    unlink_count += 1
                    self._slide_gaps(self.new_text, self.old_text)
                    self._slide_gaps(self.old_text, self.new_text)
                    self.max_words = 0
                    self._get_same_blocks()
                    self._get_sections()
                    self._get_groups()
                    self._set_fixed()

        self._get_del_blocks()
        self._position_del_blocks()
        self._get_ins_blocks()
        self._set_ins_groups()
        self._insert_marks()

    def _get_same_blocks(self):
        """Collect '=' blocks from linked tokens. A run STOPS the instant its
        pinned character changes — anchor-ness OR prelink-moved-ness flipping
        both break the run. This is what un-fuses a pinned span from the content
        next to it (the [sentinel][# title] fusion that hid whole-body moves)."""
        self.blocks.clear()
        j = self.old_text.first
        while j is not None:
            while j is not None and self.old_text.tokens[j].link is None:
                j = self.old_text.tokens[j].next

            if j is not None:
                i = self.old_text.tokens[j].link
                i_start, j_start = i, j
                count, text, unique = 0, "", False
                block_is_anchor = self.old_text.tokens[j].anchor
                block_is_moved = self.old_text.tokens[j].prelink_moved

                while (i is not None and j is not None
                       and self.old_text.tokens[j].link == i
                       and self.old_text.tokens[j].anchor == block_is_anchor
                       and self.old_text.tokens[j].prelink_moved == block_is_moved):
                    text += self.old_text.tokens[j].token
                    count += 1
                    if self.new_text.tokens[i].unique:
                        unique = True
                    i, j = self.new_text.tokens[i].next, self.old_text.tokens[j].next

                self.blocks.append(DiffBlock(
                    type='=', text=text,
                    old_number=self.old_text.tokens[j_start].number,
                    new_number=self.new_text.tokens[i_start].number,
                    old_start_token=j_start, count=count,
                    unique=unique or block_is_anchor,
                    words=len(list(RE_COUNT_WORDS.finditer(text))),
                    chars=len(text),
                    old_char=self.old_text.tokens[j_start].char_offset,
                    new_char=self.new_text.tokens[i_start].char_offset,
                    is_anchor=block_is_anchor,
                    is_prelink_moved=block_is_moved,
                    old_block_idx=len(self.blocks)))

        self.blocks.sort(key=lambda x: x.new_number)
        for block_idx in range(len(self.blocks)):
            self.blocks[block_idx].new_block_idx = block_idx

    def _get_sections(self):
        """Collect independent block sections to detect non-moving fixed groups."""
        self.sections.clear()
        b_idx = 0
        while b_idx < len(self.blocks):
            s_start = s_end = b_idx
            old_max = s_old_max = self.blocks[s_start].old_number
            for j in range(s_start + 1, len(self.blocks)):
                if self.blocks[j].old_number > old_max:
                    old_max = self.blocks[j].old_number
                elif self.blocks[j].old_number < s_old_max:
                    s_end, s_old_max = j, old_max
            
            if s_end >= s_start:
                for i in range(s_start, s_end + 1):
                    self.blocks[i].section = len(self.sections)
                self.sections.append({'blockStart': s_start, 'blockEnd': s_end})
                b_idx = s_end
            b_idx += 1

    def _get_groups(self):
        """Chain contiguous '=' blocks into groups. An anchor block NEVER chains
        with a non-anchor (singleton ground-frame group, born fixed). A
        prelink-moved block never chains with content either. Each group also
        records the new_number of its first block so _find_max_path can enforce
        BOTH-orders monotonicity when choosing the stationary spine."""
        self.groups.clear()
        b_idx = 0
        while b_idx < len(self.blocks):
            g_start = g_end = b_idx
            old_block = self.blocks[g_start].old_block_idx
            words = max_words = self.blocks[b_idx].words
            unique = self.blocks[b_idx].unique
            chars = self.blocks[b_idx].chars
            group_is_anchor = self.blocks[g_start].is_anchor
            group_is_moved = self.blocks[g_start].is_prelink_moved

            for i in range(g_end + 1, len(self.blocks)):
                if self.blocks[i].old_block_idx != old_block + 1:
                    break
                if self.blocks[i].is_anchor != group_is_anchor:
                    break
                if self.blocks[i].is_prelink_moved != group_is_moved:
                    break
                old_block = self.blocks[i].old_block_idx
                max_words = max(max_words, self.blocks[i].words)
                if self.blocks[i].unique:
                    unique = True
                words += self.blocks[i].words
                chars += self.blocks[i].chars
                g_end = i

            if g_end >= g_start:
                if group_is_anchor:
                    fixed = True
                else:
                    fixed = (self.blocks[g_start].section is None)
                for i in range(g_start, g_end + 1):
                    self.blocks[i].group = len(self.groups)
                    self.blocks[i].fixed = fixed
                grp = DiffGroup(
                    old_number=self.blocks[g_start].old_number,
                    block_start=g_start, block_end=g_end,
                    unique=unique, max_words=max_words,
                    words=words, chars=chars, fixed=fixed)
                grp.is_anchor = group_is_anchor
                # Record new-order position of the group's first block so the
                # spine DP can require monotonicity in new_number as well.
                grp.new_number = self.blocks[g_start].new_number
                self.groups.append(grp)
                self.max_words = max(self.max_words, max_words)
                b_idx = g_end
            b_idx += 1

    def _set_fixed(self):
        """Pick the max-energy increasing spine per section (the DP), then OVER-
        RIDE: anchor groups are ALWAYS fixed no matter what the DP decided. The
        anchors are the ground frame — the street poles you drove into the
        ground — and the DP is not permitted to vote them into motion. This is
        the line that kills the bus illusion: a big moved block can no longer
        crown itself 'stationary' by out-weighing the poles, because the poles
        don't compete — they're pinned before the contest and re-pinned after."""
        for section in self.sections:
            group_start = self.blocks[section['blockStart']].group
            group_end = self.blocks[section['blockEnd']].group

            cache = {}
            max_chars = 0
            max_path = []

            for i in range(group_start, group_end + 1):
                path_obj = self._find_max_path(i, group_end, cache)
                if path_obj['chars'] > max_chars:
                    max_path = path_obj['path']
                    max_chars = path_obj['chars']

            for group_idx in max_path:
                self.groups[group_idx].fixed = True
                for b in range(self.groups[group_idx].block_start,
                               self.groups[group_idx].block_end + 1):
                    self.blocks[b].fixed = True

        # Ground frame override. Poles cannot drift.
        for group in self.groups:
            if group.is_anchor:
                group.fixed = True
                for b in range(group.block_start, group.block_end + 1):
                    self.blocks[b].fixed = True

    def _find_max_path(self, start: int, group_end: int, cache: dict) -> dict:
        # ================================================================
        # A stationary spine must be monotonically increasing in BOTH
        # old_number AND new_number. That is the literal definition of "these
        # groups did not reorder relative to each other" — the only thing that
        # can honestly be called a stationary frame.
        #
        # THE BUG THIS FIXES: the old loop gated candidates on old_number alone.
        # That let the DP build a chain increasing in old-order but ZIG-ZAGGING
        # in new-order, then fix every group on it. A block that comes later in
        # old-order but EARLIER in new-order has demonstrably reordered against
        # `start`; it cannot share a stationary frame with it. Without the
        # new_number guard the DP crowned such a chain and froze a genuine mover
        # as if it stood still (the quorum-line evaporation the witness caught).
        #
        # CACHE SOUNDNESS (do not "simplify" this away): the cache is keyed on
        # `i` alone, yet the guard is caller-relative. It stays sound by
        # TRANSITIVITY of monotonicity: every group inside cache[i]['path'] has
        # new_number >= new_number(i) by induction, and we only attach i when
        # new_number(i) >= new_number(start), so the whole attached chain is
        # >= new_number(start). No context leaks across cache hits.
        #
        # KEYSTROKE-ENERGY METRIC (unchanged, still the only scoring):
        #   spine_value(size) = w_char*size - (move_base + move_log_k*ln(1+size))
        #   = keystrokes SAVED by leaving this group stationary vs cut-pasting it.
        #   Distance is deliberately absent (not in scope, moves cost the same
        #   near or far). log is concave so merged moves are cheaper than this
        #   additive DP assumes -> near-optimal, not provably optimal, on purpose.
        # ================================================================
        #
        # ----- OLD METRIC (raw character count). DO NOT DELETE. -----
        # Baseline for A/B, not dead code. If the keystroke metric misbehaves,
        # this is the fallback. Leave it commented, leave this warning attached.
        #
        #   max_chars = 0
        #   old_number = self.groups[start].old_number
        #   return_obj = {'path': [], 'chars': 0}
        #   for i in range(start + 1, group_end + 1):
        #       if self.groups[i].old_number < old_number:
        #           continue
        #       if i in cache:
        #           path_obj = {'path': cache[i]['path'][:], 'chars': cache[i]['chars']}
        #       else:
        #           path_obj = self._find_max_path(i, group_end, cache)
        #       if path_obj['chars'] > max_chars:
        #           max_chars = path_obj['chars']
        #           return_obj = path_obj
        #   return_obj['path'].insert(0, start)
        #   return_obj['chars'] += self.groups[start].chars
        #   if start not in cache:
        #       cache[start] = {'path': return_obj['path'][:], 'chars': return_obj['chars']}
        #   return return_obj
        # ----- END OLD METRIC -----

        max_score = 0.0
        old_number = self.groups[start].old_number
        new_number = self.groups[start].new_number
        return_obj = {'path': [], 'chars': 0.0}

        for i in range(start + 1, group_end + 1):
            # Both orderings must increase, or it is not a stationary spine.
            if self.groups[i].old_number is None or self.groups[i].old_number < old_number:
                continue
            if self.groups[i].new_number is None or new_number is None or self.groups[i].new_number < new_number:
                continue
            if i in cache:
                path_obj = {'path': cache[i]['path'][:], 'chars': cache[i]['chars']}
            else:
                path_obj = self._find_max_path(i, group_end, cache)

            if path_obj['chars'] > max_score:
                max_score = path_obj['chars']
                return_obj = path_obj

        return_obj['path'].insert(0, start)
        # spine_value of THIS group: keystrokes saved by leaving it stationary
        # instead of cut-pasting it. (Dict key stays 'chars' so cache/compare
        # code is untouched; it now holds a score, not a char count.)
        size = self.groups[start].chars
        spine_value = self.w_char * size - (self.move_base + self.move_log_k * math.log(1 + size))
        return_obj['chars'] += spine_value

        if start not in cache:
            cache[start] = {'path': return_obj['path'][:], 'chars': return_obj['chars']}
        return return_obj

    def _unlink_blocks(self) -> bool:
        """Convert short non-unique '=' runs into +/- noise. Anchor groups are
        EXEMPT — a pole is never noise, never eaten, even if it's short. Losing
        one silently dissolves a file boundary (two files fuse with no error) —
        the exact silent-wrong failure class this whole effort exists to kill."""
        unlinked = False
        for group in self.groups:
            if group.is_anchor:
                continue  # poles are exempt from unlink, unconditionally.

            block_start = group.block_start
            block_end = group.block_end

            if group.max_words < self.block_min_length and not group.unique:
                for b in range(block_start, block_end + 1):
                    if self.blocks[b].type == '=':
                        self._unlink_single_block(self.blocks[b])
                        unlinked = True
            else:
                for b in range(block_start, block_end + 1):
                    if self.blocks[b].type == '=':
                        if self.blocks[b].words > 1 or self.blocks[b].unique:
                            break
                        self._unlink_single_block(self.blocks[b])
                        unlinked = True
                        block_start = b

                for b in range(block_end, block_start, -1):
                    if self.blocks[b].type == '=':
                        if self.blocks[b].words > 1 or (self.blocks[b].words == 1 and self.blocks[b].unique):
                            break
                        self._unlink_single_block(self.blocks[b])
                        unlinked = True
        return unlinked

    def _unlink_single_block(self, block: DiffBlock):
        j = block.old_start_token
        for _ in range(block.count):
            self.new_text.tokens[self.old_text.tokens[j].link].link = None
            self.old_text.tokens[j].link = None
            j = self.old_text.tokens[j].next

    def _get_del_blocks(self):
        """Collects deletion ('-') blocks from the old text."""
        j = self.old_text.first
        while j is not None:
            old_start = j
            count = 0
            text = ""
            while j is not None and self.old_text.tokens[j].link is None:
                count += 1
                text += self.old_text.tokens[j].token
                j = self.old_text.tokens[j].next
            
            if count != 0:
                self.blocks.append(DiffBlock(
                    type='-',
                    text=text,
                    old_number=self.old_text.tokens[old_start].number,
                    old_start_token=old_start,
                    count=count,
                    chars=len(text),
                    old_char=self.old_text.tokens[old_start].char_offset,  # NEW
                ))            
            if j is not None:
                i = self.old_text.tokens[j].link
                while i is not None and j is not None and self.old_text.tokens[j].link == i:
                    i = self.new_text.tokens[i].next
                    j = self.old_text.tokens[j].next

    def _position_del_blocks(self):
        """Places deleted text chronologically next to closest stable markers."""
        # Using enumerate to securely track original block context parity 
        # before the shallow copy is mutated by sorting.
        blocks_old = [(i, b) for i, b in enumerate(self.blocks)]
        blocks_old.sort(key=lambda x: x[1].old_number if x[1].old_number is not None else 0)
        
        for block_idx, (orig_idx, del_block) in enumerate(blocks_old):
            if del_block.type != '-':
                continue

            prev_block = None
            if block_idx > 0:
                pb_new_idx = blocks_old[block_idx - 1][1].new_block_idx
                if pb_new_idx is not None:
                    prev_block = self.blocks[pb_new_idx]
            
            next_block = None
            if block_idx < len(blocks_old) - 1:
                nb_new_idx = blocks_old[block_idx + 1][1].new_block_idx
                if nb_new_idx is not None:
                    next_block = self.blocks[nb_new_idx]

            ref_block = None
            if prev_block and prev_block.type == '=' and prev_block.fixed:
                ref_block = prev_block
            elif next_block and next_block.type == '=' and next_block.fixed:
                ref_block = next_block
            elif prev_block and prev_block.type == '=' and prev_block != self.blocks[self.groups[prev_block.group].block_end]:
                ref_block = prev_block
            elif next_block and next_block.type == '=' and next_block != self.blocks[self.groups[next_block.group].block_start]:
                ref_block = next_block
            else:
                for fixed in range(block_idx, -1, -1):
                    if blocks_old[fixed][1].type == '=' and blocks_old[fixed][1].fixed:
                        ref_block = blocks_old[fixed][1]
                        break

            if ref_block is None:
                del_block.new_number = -1
            else:
                del_block.new_number = ref_block.new_number
                del_block.section = ref_block.section
                del_block.group = ref_block.group
                del_block.fixed = ref_block.fixed

        self._sort_blocks()

    def _get_ins_blocks(self):
        """Collect insertion ('+') blocks from the new text."""
        i = self.new_text.first
        while i is not None:
            while i is not None and self.new_text.tokens[i].link is not None:
                i = self.new_text.tokens[i].next
            
            if i is not None:
                i_start = i
                count = 0
                text = ""
                while i is not None and self.new_text.tokens[i].link is None:
                    count += 1
                    text += self.new_text.tokens[i].token
                    i = self.new_text.tokens[i].next
                
                self.blocks.append(DiffBlock(
                    type='+',
                    text=text,
                    new_number=self.new_text.tokens[i_start].number,
                    count=count,
                    chars=len(text),
                    new_char=self.new_text.tokens[i_start].char_offset,  # NEW
                ))
        self._sort_blocks()

    def _sort_blocks(self):
        """Re-sorts self.blocks to new_number chronological order and updates group start/ends."""
        self.blocks.sort(key=lambda x: (
            x.new_number if x.new_number is not None else 0,
            x.old_number if x.old_number is not None else 0
        ))

        current_group = None
        for block_idx, block in enumerate(self.blocks):
            block.new_block_idx = block_idx
            block_group = block.group
            
            if block_group is not None:
                if block_group != current_group:
                    current_group = block_group
                    self.groups[current_group].block_start = block_idx
                    self.groups[current_group].old_number = block.old_number
                self.groups[block_group].block_end = block_idx

    def _set_ins_groups(self):
        """Assigns the proper group block index to isolated insertion elements."""
        for group_idx, group in enumerate(self.groups):
            for b in range(group.block_start, group.block_end + 1):
                if self.blocks[b].group is None:
                    self.blocks[b].group = group_idx
                    self.blocks[b].fixed = group.fixed

        for block_idx, block in enumerate(self.blocks):
            if block.group is None:
                block.group = len(self.groups)
                self.groups.append(DiffGroup(
                    old_number=block.old_number,
                    block_start=block_idx,
                    block_end=block_idx,
                    unique=block.unique,
                    max_words=block.words,
                    words=block.words,
                    chars=block.chars,
                    fixed=block.fixed
                ))

    def _insert_marks(self):
        """Constructs and inserts '|' blocks denoting the original position of a moved group."""
        # Need a safe lookup to iterate the sorted state while preserving orig indexing
        blocks_old = [(i, b) for i, b in enumerate(self.blocks)]
        blocks_old.sort(key=lambda x: (
            x[1].old_number if x[1].old_number is not None else 0,
            x[1].new_number if x[1].new_number is not None else 0
        ))

        lookup_sorted = {orig_idx: sorted_idx for sorted_idx, (orig_idx, _) in enumerate(blocks_old)}
        color = 1
        
        for moved_idx, moved_group in enumerate(self.groups):
            if moved_group.fixed is not False:
                continue
            
            moved_old_number = moved_group.old_number
            block_idx_start = lookup_sorted[moved_group.block_start]
            prev_block = blocks_old[block_idx_start - 1][1] if block_idx_start > 0 else None
            
            block_idx_end = lookup_sorted[moved_group.block_end]
            next_block = blocks_old[block_idx_end + 1][1] if block_idx_end < len(blocks_old) - 1 else None

            ref_block = None
            if prev_block and prev_block.type == '=' and prev_block.fixed:
                ref_block = prev_block
            elif next_block and next_block.type == '=' and next_block.fixed:
                ref_block = next_block
            else:
                for fixed in range(lookup_sorted[moved_group.block_start] - 1, -1, -1):
                    if blocks_old[fixed][1].type == '=' and blocks_old[fixed][1].fixed:
                        ref_block = blocks_old[fixed][1]
                        break

            if ref_block is None:
                new_number = -1
                mark_group = len(self.groups)
                self.groups.append(DiffGroup(
                    old_number=0,
                    block_start=len(self.blocks),
                    block_end=len(self.blocks),
                    unique=False,
                    max_words=0,
                    words=0,
                    chars=0,
                    fixed=False
                ))
            else:
                new_number = ref_block.new_number
                mark_group = ref_block.group

            moved_start_block = self.blocks[moved_group.block_start]
            marker_old_char = None
            if moved_start_block.old_start_token is not None:
                marker_old_char = self.old_text.tokens[
                    moved_start_block.old_start_token].char_offset

            self.blocks.append(DiffBlock(
                type='|',
                text='',
                old_number=moved_old_number,
                new_number=new_number,
                chars=0,
                group=mark_group,
                fixed=True,
                moved_to_group=moved_idx,
                old_char=marker_old_char,  # NEW: origin position of the moved run
            ))

            moved_group.color_id = color
            moved_group.moved_from_group = mark_group
            color += 1

        self._sort_blocks()
