"""Compare source files, never GitHub URLs or the JSON transport envelope."""
import io
import json
import re
import tokenize
from difflib import SequenceMatcher
from pathlib import PurePosixPath

SOURCE_SUFFIXES = {'.py', '.pyw', '.pyi', '.c', '.h', '.cc', '.cpp', '.hpp', '.java',
                   '.js', '.jsx', '.ts', '.tsx', '.go', '.rs', '.cs', '.php', '.rb', '.swift', '.kt'}
DEPENDENCY_DIRS = {'.git', '.venv', 'venv', 'env', '__pycache__', 'node_modules',
                   'site-packages', 'vendor', 'dist', 'build'}


def source_tokens(source, suffix):
    if suffix in {'.py', '.pyw', '.pyi'}:
        try:
            ignored = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                       tokenize.DEDENT, tokenize.ENDMARKER, tokenize.ENCODING}
            # Python's tokenizer preserves // division and URLs inside string literals.
            return tuple(token.string for token in tokenize.generate_tokens(io.StringIO(source).readline)
                         if token.type not in ignored and token.string.strip())
        except (tokenize.TokenError, IndentationError, SyntaxError):
            pass
    # Conservative fallback: preserve content, including strings and comments.
    return tuple(re.findall(r'\w+|[^\w\s]', source))


def prepare_github_source(raw, max_chars=50000):
    payload = json.loads(raw)
    if not isinstance(payload, dict) or not isinstance(payload.get('files'), list):
        raise ValueError('GitHub files have not been loaded')
    files = []
    size = 0
    for part in payload['files']:
        if not isinstance(part, dict) or not isinstance(part.get('name'), str) or not isinstance(part.get('content'), str):
            continue
        path = PurePosixPath(part['name'].replace('\\', '/'))
        suffix = path.suffix.lower()
        if suffix not in SOURCE_SUFFIXES or any(p.lower() in DEPENDENCY_DIRS for p in path.parts[:-1]):
            continue
        size += len(part['content'])
        if size > max_chars:
            raise ValueError('GitHub source exceeds similarity size limit')
        tokens = source_tokens(part['content'], suffix)
        if tokens:
            files.append(tokens)
    # Sorting by content makes renaming/reordering files irrelevant. Names and README
    # text must not inflate the match. Boundaries avoid fusing tokens across files.
    return tuple(token for file in sorted(files) for token in (*file, '\0FILE_END'))


def source_similarity(a, b):
    if not a or not b:
        return 0
    if a == b:
        return 100
    # Compare tokens, not characters; repeated Python keywords are meaningful here.
    forward = SequenceMatcher(None, a, b, autojunk=False).ratio()
    backward = SequenceMatcher(None, b, a, autojunk=False).ratio()
    return round(100 * (forward + backward) / 2)
