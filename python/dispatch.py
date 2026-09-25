"""Shared tool dispatch, with a versioned envelope at the worker boundary."""
import json
from hash_tool import calculate_hash, stream_hash
from url_cleaner import clean_url
from base64_tool import convert
from json_tool import transform
from privacy_tools import run as privacy_run
from text_tools import run as text_run
from data_tools import run as data_run


def dispatch(action, options, data=b''):
    if len(data) > 64 * 1024 * 1024:
        raise ValueError('Files must be 64 MB or smaller.')
    for key in ['text', 'modified']:
        if len(options.get(key, '').encode('utf-8')) > 8 * 1024 * 1024:
            raise ValueError('Text must be 8 MB or smaller.')
    text = options.get('text', '')
    if action in {'hash-start', 'hash-chunk', 'hash-finish'}:
        result = stream_hash(action, data, options.get('algorithm', 'sha256'))
    elif action == 'hash':
        result = {'text': calculate_hash(data, options.get('algorithm', 'sha256'))}
    elif action == 'url-cleaner':
        result = clean_url(text, options.get('remove_ref', False))
    elif action == 'base64':
        result = convert(options.get('mode', 'encode-text'), text, data)
    elif action in {'json', 'json-validator'}:
        indent = int(options.get('indent', 2))
        if indent not in {2, 4}:
            raise ValueError('Choose 2 or 4 spaces for indentation.')
        result = transform(text, 'validate' if action == 'json-validator' else options.get('mode', 'format'), indent, options.get('sort_keys', False))
    elif action in {'image-inspect', 'image-metadata', 'image-compressor', 'image-resizer', 'image-converter'}:
        from image_tool import process_image
        result = process_image(data, action, int(options.get('quality', 75)), options.get('output', 'original'), options)
    elif action in {'password-generator', 'uuid-generator', 'random-token'}:
        result = privacy_run(action, options)
    elif action in {'text-cleaner', 'remove-duplicate-lines', 'text-diff'}:
        result = text_run(action, options)
    elif action in {'csv-json', 'url-encoder', 'timestamp', 'jwt-decoder'}:
        result = data_run(action, options)
    else:
        raise ValueError('Unknown tool.')
    return json.dumps(result, ensure_ascii=False)


def execute_tool(tool, payload, data=b''):
    try:
        return json.dumps({'success': True, 'result': json.loads(dispatch(tool, payload, data)), 'metadata': {}}, ensure_ascii=False)
    except (ValueError, TypeError, RecursionError, OverflowError) as exc:
        code = 'INVALID_JSON' if tool in {'json', 'json-validator'} else 'INVALID_INPUT'
        return json.dumps({'success': False, 'error': {'code': code, 'message': str(exc)}}, ensure_ascii=False)
