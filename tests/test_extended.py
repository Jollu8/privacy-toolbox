import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from dispatch import dispatch, execute_tool
from hash_tool import stream_hash
from image_tool import process_image
from PIL import Image


def call(tool, **payload):
    return json.loads(dispatch(tool, payload))


class GeneratorTests(unittest.TestCase):
    def test_password_groups_and_avoid_similar(self):
        for _ in range(20):
            value = call('password-generator', length=24, avoid_similar=True)['text']
            self.assertEqual(len(value), 24)
            self.assertTrue(any(c.islower() for c in value))
            self.assertTrue(any(c.isupper() for c in value))
            self.assertTrue(any(c.isdigit() for c in value))
            self.assertTrue(any(not c.isalnum() for c in value))
            self.assertFalse(set(value) & set('Il1O0o'))
        result = call('password-generator', length=4, uppercase=False, lowercase=False, symbols=False)
        self.assertIn('13.3 bits', result['details'][1])
        with self.assertRaises(ValueError):
            call('password-generator', uppercase=False, lowercase=False, numbers=False, symbols=False)
        with patch('privacy_tools.secrets.choice', side_effect=RuntimeError('RNG unavailable')):
            with self.assertRaises(RuntimeError):
                call('password-generator')

    def test_uuid_version_variant(self):
        result = call('uuid-generator', amount=100)
        self.assertEqual(len(result['items']), 100)
        for value in result['items']:
            parsed = uuid.UUID(value)
            self.assertEqual(parsed.version, 4)
            self.assertEqual(parsed.variant, uuid.RFC_4122)
        for amount in [0, 1001, 'bad']:
            with self.assertRaises(ValueError):
                call('uuid-generator', amount=amount)

    def test_tokens(self):
        for mode in ['hex', 'base64', 'urlsafe']:
            result = call('random-token', mode=mode, bytes=32)
            value = result['text']
            decoded = bytes.fromhex(value) if mode == 'hex' else base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
            self.assertEqual(len(decoded), 32)
            self.assertIn('256 bits', result['details'][0])


class DataTests(unittest.TestCase):
    def test_csv_quotes_multiline_and_export(self):
        original = 'name,code,notes\r\n"A, B",001,"one\ntwo"\r\n'
        rows = json.loads(call('csv-json', text=original)['text'])
        self.assertEqual(rows, [{'name': 'A, B', 'code': '001', 'notes': 'one\ntwo'}])
        csv = call('csv-json', mode='json-csv', text=json.dumps(rows), safe_export=False)['text']
        self.assertEqual(json.loads(call('csv-json', text=csv)['text']), rows)
        protected = call('csv-json', mode='json-csv', text='[{"=name":"=cmd","other":null}]')['text']
        self.assertIn("'=cmd", protected)
        self.assertIn("'=name", protected)
        for value in ['a,a\n1,2', 'a,b\n1', ',b\n1,2']:
            with self.assertRaises(ValueError): call('csv-json', text=value)
        for value in ['{}', '[{"x":[]}]']:
            with self.assertRaises(ValueError): call('csv-json', mode='json-csv', text=value)
        self.assertEqual(call('csv-json', mode='json-csv', text='[]')['text'], '')

    def test_url_encoding(self):
        value = 'hello world & Привет +'
        encoded = call('url-encoder', text=value)['text']
        self.assertIn('%20', encoded)
        self.assertEqual(call('url-encoder', mode='decode', text=encoded)['text'], value)
        self.assertEqual(call('url-encoder', mode='decode', text='a+b')['text'], 'a+b')
        for value in ['%', '%0x', '%FF']:
            with self.assertRaises(ValueError): call('url-encoder', mode='decode', text=value)

    def test_timestamp(self):
        self.assertEqual(call('timestamp', text='0')['iso'], '1970-01-01T00:00:00Z')
        self.assertEqual(call('timestamp', text='-1')['iso'], '1969-12-31T23:59:59Z')
        self.assertEqual(call('timestamp', text='1001', unit='milliseconds')['iso'], '1970-01-01T00:00:01.001000Z')
        result = call('timestamp', mode='date', text='1970-01-01T03:00:00+03:00')
        self.assertIn('Unix seconds: 0', result['text'])
        self.assertIn('Unix milliseconds: -1', call('timestamp', mode='date', text='1969-12-31T23:59:59.999Z')['text'])
        for value in ['NaN', 'Infinity', '1e999', 'bad']:
            with self.assertRaises(ValueError): call('timestamp', text=value)

    def test_jwt_untrusted_and_invalid(self):
        def part(value): return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=')
        token = part({'alg': 'none'}) + '.' + part({'sub':'<script>', 'exp':0, 'iss':'https://example.com'}) + '.'
        result = call('jwt-decoder', text=token)
        self.assertIn('<script>', result['text'])
        self.assertIn('Signature NOT verified', result['details'][0])
        self.assertTrue(result['sensitive'])
        for value in ['a.b.c.d.e', 'a.b.c', part([])+'.'+part({})+'.']:
            with self.assertRaises(ValueError): call('jwt-decoder', text=value)

    def test_json_options_and_error_protocol(self):
        self.assertIn('\n    "a"', call('json', text='{"z":1,"a":2}', indent='4', sort_keys=True)['text'])
        self.assertIn('Valid JSON', call('json-validator', text='null')['text'])
        result = json.loads(execute_tool('json-validator', {'text':'{bad}'}))
        self.assertFalse(result['success'])
        self.assertEqual(result['error']['code'], 'INVALID_JSON')
        self.assertIn('line 1', result['error']['message'])
        self.assertEqual(call('url-cleaner', text='https://a.test/?ref=x&id=1', remove_ref=True)['text'], 'https://a.test/?id=1')


class TextTests(unittest.TestCase):
    def test_cleanup_preserves_endings_and_unicode(self):
        result = call('text-cleaner', text='  A   B  \r\n\r\nC\tD\r\n')['text']
        self.assertEqual(result, 'A B\r\nC\tD\r\n')
        result = call('text-cleaner', text='A\tB\x00\rC', tabs=True, non_printable=True, normalize_endings=True, extra_spaces=False)['text']
        self.assertEqual(result, 'A    B\nC')
        self.assertEqual(call('text-cleaner', text='')['text'], '')

    def test_dedupe_semantics(self):
        result = call('remove-duplicate-lines', text=' Apple \napple\nBanana\napple\n', ignore_case=True, trim=True)
        self.assertEqual(result['text'], 'Apple\nBanana')
        self.assertIn('Duplicates removed: 2', result['details'])
        self.assertEqual(call('remove-duplicate-lines', text='b\na\nb', keep_order=False)['text'], 'a\nb')
        self.assertEqual(call('remove-duplicate-lines', text='')['details'][0], 'Input lines: 0')

    def test_diff_and_final_newline(self):
        result = call('text-diff', text='old\n', modified='new\n')
        self.assertIn('-old\n+new\n', result['text'])
        self.assertIn('Changed pairs: 1', result['details'][0])
        self.assertIn('No newline', call('text-diff', text='a', modified='a\n')['text'])
        self.assertEqual(call('text-diff', text='a', modified='a')['text'], 'No differences.')
        with self.assertRaises(ValueError): call('text-diff', text='a' * 200001)


class FileTests(unittest.TestCase):
    def test_stream_hash_over_original_limit(self):
        chunk = b'x' * (4 * 1024 * 1024)
        reference = hashlib.sha256()
        stream_hash('hash-start')
        for _ in range(17):
            reference.update(chunk)
            stream_hash('hash-chunk', chunk)
        self.assertEqual(stream_hash('hash-finish')['text'], reference.hexdigest())
        with self.assertRaises(ValueError): stream_hash('hash-finish')
        stream_hash('hash-start')
        self.assertEqual(stream_hash('hash-finish')['text'], hashlib.sha256(b'').hexdigest())

    def test_inspect_resize_and_all_formats(self):
        image = Image.new('RGBA', (40, 20), (1, 2, 3, 0))
        stream = BytesIO(); image.save(stream, 'PNG')
        data = stream.getvalue()
        info = process_image(data, 'image-inspect')
        self.assertEqual((info['width'], info['height'], info['format']), (40,20,'PNG'))
        result = process_image(data, 'image-resizer', output='PNG', settings={'width':10,'height':19,'keep_aspect':True})
        self.assertEqual((result['width'], result['height']), (10,5))
        result = process_image(data, 'image-resizer', output='PNG', settings={'width':10,'height':19,'keep_aspect':False})
        self.assertEqual((result['width'], result['height']), (10,19))
        for target in ['BMP','JPEG','PNG','WEBP']:
            result = process_image(data, 'image-converter', output=target, quality=100)
            with Image.open(BytesIO(base64.b64decode(result['base64']))) as converted:
                self.assertEqual(converted.format, target)
        with self.assertRaises(ValueError):
            process_image(data, 'image-resizer', settings={'width':20000000,'height':2,'keep_aspect':False})
