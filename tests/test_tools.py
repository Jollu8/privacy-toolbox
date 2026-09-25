import base64
import json
from io import BytesIO
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from hash_tool import calculate_hash
from url_cleaner import clean_url
from base64_tool import convert
from json_tool import transform
from dispatch import dispatch
from image_tool import process_image
from PIL import Image, PngImagePlugin


class TextToolsTests(unittest.TestCase):
    def test_hash_known_vectors(self):
        self.assertEqual(calculate_hash(b'abc'), 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
        self.assertEqual(calculate_hash(b'', 'md5'), 'd41d8cd98f00b204e9800998ecf8427e')
        for algorithm, length in [('sha384', 96), ('sha512', 128), ('sha1', 40)]:
            self.assertEqual(len(calculate_hash(b'abc', algorithm)), length)
        with self.assertRaises(ValueError):
            calculate_hash(b'', 'shake_128')

    def test_url_preserves_raw_values_duplicates_and_fragment(self):
        result = clean_url('https://example.com/p?UTM_SOURCE=a&x=%20&x=+&blank=&flag&fbclid=1#part')
        self.assertEqual(result['text'], 'https://example.com/p?x=%20&x=+&blank=&flag#part')
        self.assertEqual(result['removed'], ['UTM_SOURCE', 'fbclid'])
        self.assertEqual(clean_url('https://example.com/?%75tm_source=a')['text'], 'https://example.com/')
        for url in ['javascript:alert(1)', '/relative', 'https://', 'https://x:abc', 'https://x/\na']:
            with self.assertRaises(ValueError):
                clean_url(url)

    def test_base64_text_and_binary_roundtrip(self):
        text = 'Привет, 🌍'
        encoded = convert('encode-text', text)['text']
        self.assertEqual(convert('decode-text', encoded)['text'], text)
        data = bytes(range(256))
        encoded = convert('encode-file', data=data)['text']
        self.assertEqual(base64.b64decode(convert('decode-file', encoded)['base64']), data)
        self.assertEqual(convert('decode-text', '')['text'], '')
        for invalid in ['@abc', 'abc', '🤖']:
            with self.assertRaises(ValueError):
                convert('decode-text', invalid)
        with self.assertRaisesRegex(ValueError, 'UTF-8'):
            convert('decode-text', '/w==')

    def test_json(self):
        self.assertEqual(transform('{"z": 1, "a": [true, null]}', 'minify')['text'], '{"z":1,"a":[true,null]}')
        self.assertLess(transform('{"z":1,"a":2}', 'sort')['text'].index('a'), transform('{"z":1,"a":2}', 'sort')['text'].index('z'))
        for invalid in ['{"a":}', '{"a":1,"a":2}', 'NaN', 'Infinity', '1e999']:
            with self.assertRaises(ValueError):
                transform(invalid)
        self.assertIn('Valid JSON', transform('null', 'validate')['text'])
        self.assertEqual(json.loads(transform('123456789012345678901234567890')['text']), 123456789012345678901234567890)

    def test_dispatch(self):
        self.assertEqual(json.loads(dispatch('hash', {}, b'abc'))['text'], calculate_hash(b'abc'))
        with self.assertRaises(ValueError):
            dispatch('missing', {})
        with self.assertRaises(ValueError):
            dispatch('json', {'text': 'a' * (8 * 1024 * 1024 + 1)})


class ImageTests(unittest.TestCase):
    def test_jpeg_exif_removed_and_orientation_applied(self):
        source = Image.new('RGB', (12, 8), 'red')
        exif = Image.Exif()
        exif[272] = 'Private camera'
        exif[274] = 6
        data = BytesIO()
        source.save(data, 'JPEG', exif=exif)
        result = process_image(data.getvalue(), 'image-metadata')
        self.assertEqual(result['metadata']['Camera'], 'Private camera')
        with Image.open(BytesIO(base64.b64decode(result['base64']))) as clean:
            self.assertFalse(clean.getexif())
            self.assertEqual(clean.size, (8, 12))

    def test_png_text_removed_transparency_preserved(self):
        source = Image.new('RGBA', (10, 10), (20, 40, 60, 0))
        info = PngImagePlugin.PngInfo()
        info.add_text('Author', 'Private name')
        data = BytesIO()
        source.save(data, 'PNG', pnginfo=info)
        result = process_image(data.getvalue(), 'image-metadata')
        with Image.open(BytesIO(base64.b64decode(result['base64']))) as clean:
            self.assertNotIn('Author', clean.info)
            self.assertEqual(clean.getpixel((0, 0))[3], 0)
        result = process_image(data.getvalue(), 'image-compressor', 75, 'JPEG')
        with Image.open(BytesIO(base64.b64decode(result['base64']))) as clean:
            self.assertEqual(clean.getpixel((0, 0)), (255, 255, 255))

    def test_formats_corruption_animation_and_size(self):
        source = Image.new('RGB', (10, 10), 'red')
        data = BytesIO()
        source.save(data, 'PNG')
        for target in ['JPEG', 'PNG', 'WEBP']:
            result = process_image(data.getvalue(), 'image-compressor', 65, target)
            with Image.open(BytesIO(base64.b64decode(result['base64']))) as clean:
                self.assertEqual(clean.format, target)
                self.assertFalse(clean.getexif())
        with self.assertRaises(ValueError):
            process_image(b'not an image', 'image-metadata')
        animated = BytesIO()
        source.save(animated, 'PNG', save_all=True, append_images=[Image.new('RGB', (10, 10), 'blue')])
        with self.assertRaisesRegex(ValueError, 'Animated'):
            process_image(animated.getvalue(), 'image-metadata')
        old_limit = Image.MAX_IMAGE_PIXELS
        try:
            Image.MAX_IMAGE_PIXELS = 50
            with self.assertRaisesRegex(ValueError, 'too large'):
                process_image(data.getvalue(), 'image-metadata')
        finally:
            Image.MAX_IMAGE_PIXELS = old_limit


if __name__ == '__main__':
    unittest.main()
