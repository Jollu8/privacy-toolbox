"""Local text operations with explicit line-ending and comparison semantics."""
import difflib
import re


def run(tool, options):
    text = options.get('text', '')
    if tool == 'text-cleaner':
        result = text
        if options.get('normalize_endings'):
            result = result.replace('\r\n', '\n').replace('\r', '\n')
        if options.get('tabs'):
            result = result.replace('\t', '    ')
        if options.get('non_printable'):
            result = ''.join(c for c in result if c.isprintable() or c in '\r\n\t')
        lines = []
        for match in re.finditer(r'([^\r\n]*)(\r\n|\r|\n|$)', result):
            line, ending = match.groups()
            if not line and not ending:
                continue
            if options.get('extra_spaces', True):
                line = re.sub(r' {2,}', ' ', line)
            if options.get('trim', True):
                line = line.strip()
            if options.get('empty_lines', True) and not line.strip():
                continue
            lines.append(line + ending)
        result = ''.join(lines)
        return {'text': result, 'details': [f'Before: {len(text)} characters · After: {len(result)} characters'], 'extension': 'txt'}
    if tool == 'remove-duplicate-lines':
        lines = text.splitlines()
        unique = {}
        for line in lines:
            if options.get('trim'):
                line = line.strip()
            key = line.casefold() if options.get('ignore_case') else line
            unique.setdefault(key, line)
        values = list(unique.values()) if options.get('keep_order', True) else [unique[key] for key in sorted(unique)]
        return {'text': '\n'.join(values), 'details': [f'Input lines: {len(lines)}', f'Unique lines: {len(values)}',
                f'Duplicates removed: {len(lines) - len(values)}'], 'extension': 'txt'}
    if tool == 'text-diff':
        modified = options.get('modified', '')
        if max(len(text), len(modified)) > 200_000:
            raise ValueError('Diff accepts at most 200,000 characters per input.')
        old, new = text.splitlines(keepends=True), modified.splitlines(keepends=True)
        if max(len(old), len(new)) > 5000:
            raise ValueError('Diff accepts at most 5,000 lines per input.')
        matcher = difflib.SequenceMatcher(None, old, new)
        added = removed = changed = 0
        for kind, i, j, a, b in matcher.get_opcodes():
            if kind in {'replace', 'delete'}:
                removed += j - i
            if kind in {'replace', 'insert'}:
                added += b - a
            if kind == 'replace':
                changed += min(j - i, b - a)
        output = []
        for line in difflib.unified_diff(old, new, fromfile='original', tofile='modified'):
            output.append(line if line.endswith(('\n', '\r')) else line + '\n\\ No newline at end of file\n')
        return {'text': ''.join(output) if output else 'No differences.', 'extension': 'diff',
                'details': [f'Added: {added} lines · Removed: {removed} lines · Changed pairs: {changed}',
                            'Changed pairs are included in added/removed totals.']}
    raise ValueError('Unknown text tool.')
