"""Real Chromium/Pyodide integration checks. Requires playwright and CDN access."""
import base64
import hashlib
import json
import uuid
import zxingcpp
import os
from pathlib import Path
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from PIL import Image
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if not self.path.startswith('/privacy-toolbox/'):
            self.send_error(404)
            return
        self.path = self.path[len('/privacy-toolbox'):]
        super().do_GET()

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(ROOT / os.environ.get('PRIVACY_SITE_ROOT', '.'))))
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
base = f'http://127.0.0.1:{server.server_port}/privacy-toolbox/'
try:
    with sync_playwright() as p:
        executable = os.environ.get('PRIVACY_BROWSER_PATH')
        browser = p.chromium.launch(**({'executable_path': executable} if executable else {}))
        context = browser.new_context(accept_downloads=True, viewport={'width': 1440, 'height': 1100})
        page = context.new_page()
        errors = []
        requests = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append((request.method, request.url)))
        page.goto(base)
        expect(page.locator('.tool-card:visible')).to_have_count(23)
        assert not any('jsdelivr' in url for _, url in requests), 'Homepage loaded the runtime'
        page.get_by_role('button', name='Files', exact=True).click()
        expect(page.locator('.tool-card:visible')).to_have_count(5)
        page.locator('#search').fill('metadata')
        expect(page.locator('.tool-card:visible')).to_have_count(1)
        page.locator('#search').fill('')
        page.get_by_role('button', name='All tools').click()
        page.screenshot(path=str(Path(tempfile.gettempdir()) / 'privacy-desktop.png'), full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(Path(tempfile.gettempdir()) / 'privacy-mobile.png'), full_page=False)
        page.set_viewport_size({'width': 1440, 'height': 1100})
        print('PASS catalog, lazy loading, filters, desktop and mobile', flush=True)

        # Language must persist across routes without changing user input.
        page.locator('.language-switch').select_option('ru')
        expect(page.locator('html')).to_have_attribute('lang', 'ru')
        page.locator('#search').fill('парол')
        expect(page.locator('.tool-card:visible')).to_have_count(1)
        page.locator('.tool-card:visible').click()
        expect(page.locator('h1')).to_have_text('Генератор паролей')
        palette = page.evaluate("getComputedStyle(document.body).getPropertyValue('--bg')")
        page.goto(base + 'about/')
        expect(page.locator('h1')).to_contain_text('Ваши файлы')
        assert palette == page.evaluate("getComputedStyle(document.body).getPropertyValue('--bg')")
        page.goto(base + 'tools/qr-generator/')
        page.locator('#text').fill('Copy result')
        page.locator('button[type=submit]').click()
        expect(page.locator('#status')).to_contain_text('Готово.')
        page.locator('.language-switch').select_option('en')
        expect(page.locator('#text')).to_have_value('Copy result')
        expect(page.locator('#status')).to_contain_text('Done.')
        expect(page.locator('h1')).to_have_text('QR Code Generator')
        page.reload()
        expect(page.locator('html')).to_have_attribute('lang', 'en')
        for route in ['', 'about/', 'tools/json-formatter/']:
            page.goto(base + route)
            assert palette == page.evaluate("getComputedStyle(document.body).getPropertyValue('--bg')")
            page.locator('.language-switch').select_option('ru')
            page.set_viewport_size({'width': 320, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), route
            page.locator('.language-switch').select_option('en')
            page.set_viewport_size({'width': 1440, 'height': 1100})
        print('PASS RU/EN, persistence, unchanged input, shared palette and mobile routes', flush=True)

        def go(tool):
            page.goto(base + 'tools/' + tool + '/')

        def run():
            page.locator('button[type=submit]').click()
            expect(page.locator('#status')).to_contain_text('Done.', timeout=180_000)

        go('hash')
        page.locator('#file').set_input_files({'name': 'private.txt', 'mimeType': 'text/plain', 'buffer': b'abc'})
        run()
        expect(page.locator('#result-text')).to_have_value(hashlib.sha256(b'abc').hexdigest())
        page.locator('.language-switch').select_option('ru')
        expect(page.locator('#file-info')).to_contain_text('private.txt')
        expect(page.locator('#result-text')).to_have_value(hashlib.sha256(b'abc').hexdigest())
        expect(page.locator('#status')).to_contain_text('Готово.')
        page.screenshot(path=str(Path(tempfile.gettempdir()) / 'privacy-tool-ru.png'), full_page=True)
        page.locator('.language-switch').select_option('en')
        assert not any('pillow' in url.lower() for _, url in requests), 'Hash loaded Pillow'
        for algorithm in ['sha384', 'sha512', 'sha1', 'md5']:
            page.locator('#algorithm').select_option(algorithm)
            run()
            expect(page.locator('#result-text')).to_have_value(hashlib.new(algorithm, b'abc').hexdigest())
        print('PASS all five hash algorithms using transferred bytes', flush=True)

        go('url-cleaner')
        page.locator('#text').fill('https://example.com/?utm_source=secret&x=%20&fbclid=private#fragment')
        run()
        expect(page.locator('#result-text')).to_have_value('https://example.com/?x=%20#fragment')
        expect(page.locator('#result-details')).to_contain_text('utm_source, fbclid')
        page.locator('#text').fill('javascript:alert(1)')
        page.locator('button[type=submit]').click()
        expect(page.locator('#status')).to_have_class('error', timeout=30_000)
        print('PASS URL cleaning and validation', flush=True)

        go('json')
        page.locator('#text').fill('{"z":2,"a":1}')
        for mode in ['format', 'sort', 'minify', 'validate']:
            page.locator('#mode').select_option(mode)
            run()
        page.locator('#text').fill('{bad}')
        page.locator('button[type=submit]').click()
        expect(page.locator('#status')).to_contain_text('line 1', timeout=30_000)
        print('PASS JSON operations and parser errors', flush=True)

        go('base64')
        page.locator('#text').fill('Привет 🌍')
        run()
        encoded = page.locator('#result-text').input_value()
        assert encoded == base64.b64encode('Привет 🌍'.encode()).decode()
        page.locator('#mode').select_option('decode-text')
        page.locator('#text').fill(encoded)
        run()
        expect(page.locator('#result-text')).to_have_value('Привет 🌍')
        page.locator('#mode').select_option('encode-file')
        page.locator('#file').set_input_files({'name': 'bytes.bin', 'mimeType': 'application/octet-stream', 'buffer': bytes(range(256))})
        run()
        encoded = page.locator('#result-text').input_value()
        page.locator('#mode').select_option('decode-file')
        page.locator('#text').fill(encoded)
        run()
        with page.expect_download() as download:
            page.locator('#download').click()
        assert Path(download.value.path()).read_bytes() == bytes(range(256))
        print('PASS all Base64 modes and binary download', flush=True)

        picture = Image.new('RGB', (24, 16), 'red')
        exif = Image.Exif()
        exif[272] = 'Private camera'
        exif[274] = 6
        stream = BytesIO()
        picture.save(stream, 'JPEG', exif=exif)
        for tool in ['image-metadata', 'image-compressor']:
            go(tool)
            page.locator('#file').set_input_files({'name': 'private.jpg', 'mimeType': 'image/jpeg', 'buffer': stream.getvalue()})
            if tool == 'image-compressor':
                page.locator('#output').select_option('WEBP')
            run()
            expect(page.locator('#result-details')).to_contain_text('Private camera')
            with page.expect_download() as download:
                page.locator('#download').click()
            with Image.open(download.value.path()) as clean:
                assert not clean.getexif()
                assert clean.size == (16, 24)
                assert clean.format == ('JPEG' if tool == 'image-metadata' else 'WEBP')
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        print('PASS Pillow, metadata removal, orientation, compression, downloads, mobile tool', flush=True)
        # New pages are exercised through real workers and the browser UI.
        page.set_viewport_size({'width': 1440, 'height': 1100})
        go('password-generator')
        run()
        password = page.locator('#result-text').input_value()
        assert len(password) == 20
        assert any(c.isupper() for c in password) and any(c.isdigit() for c in password)
        expect(page.locator('#download')).to_be_hidden()
        page.locator('#clear').click()
        expect(page.locator('#result-text')).to_have_value('')
        go('uuid-generator')
        run()
        ids = page.locator('#result-text').input_value().splitlines()
        assert len(ids) == 5 and all(uuid.UUID(v).version == 4 for v in ids)
        expect(page.get_by_role('button', name='Copy one')).to_have_count(5)
        go('random-token')
        for mode in ['hex', 'urlsafe', 'base64']:
            page.locator('#mode').select_option(mode)
            run()
            expect(page.locator('#result-details')).to_contain_text('256 bits')
        print('PASS secure generators, UUID v4, token encodings, Clear', flush=True)

        cases = [
            ('json-validator', '{}', 'Valid JSON'),
            ('csv-json', 'name,age\nAnna,28', 'Anna'),
            ('text-cleaner', '  hello   world  ', 'hello world'),
            ('remove-duplicate-lines', 'a\nb\na', 'a\nb'),
            ('url-encoder', 'hello world &', 'hello%20world%20%26'),
            ('timestamp', '0', '1970-01-01'),
        ]
        for tool, value, expected in cases:
            go(tool)
            page.locator('#text').fill(value)
            run()
            assert expected in page.locator('#result-text').input_value(), tool
        go('text-diff')
        page.locator('#text').fill('old\n')
        page.locator('#modified').fill('new\n')
        run()
        assert '-old\n+new' in page.locator('#result-text').input_value()
        def segment(value): return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=')
        go('jwt-decoder')
        page.locator('#text').fill(segment({'alg':'none'}) + '.' + segment({'sub':'<script>alert(1)</script>', 'exp':0}) + '.')
        run()
        expect(page.locator('#result-details')).to_contain_text('Signature NOT verified')
        assert '<script>' in page.locator('#result-text').input_value()
        expect(page.locator('#download')).to_be_hidden()
        print('PASS JSON validator, CSV, text tools, URL encoding, timestamp, JWT', flush=True)

        for tool in ['image-resizer', 'image-converter']:
            go(tool)
            page.locator('#file').set_input_files({'name':'photo.jpg', 'mimeType':'image/jpeg', 'buffer':stream.getvalue()})
            expect(page.locator('#image-info')).to_contain_text('Private camera', timeout=180_000)
            if tool == 'image-resizer':
                page.get_by_role('button', name='50%', exact=True).click()
                page.locator('#output').select_option('PNG')
            else:
                page.locator('#output').select_option('BMP')
            run()
            with page.expect_download() as download:
                page.locator('#download').click()
            with Image.open(download.value.path()) as converted:
                assert converted.size == ((8,12) if tool == 'image-resizer' else (16,24))
                assert converted.format == ('PNG' if tool == 'image-resizer' else 'BMP')
        print('PASS metadata inspection, resize presets and BMP conversion', flush=True)

        go('qr-generator')
        qr_requests = len(requests)
        qr_value = 'https://example.com/Привет?x=42'
        page.locator('#text').fill(qr_value)
        run()
        with page.expect_download() as download:
            page.locator('#download').click()
        with Image.open(download.value.path()) as qr_image:
            decoded = zxingcpp.read_barcode(qr_image)
            assert decoded and decoded.text == qr_value
        with page.expect_download() as download:
            page.locator('#download-svg').click()
        svg = Path(download.value.path()).read_text()
        assert '<svg' in svg and '<path' in svg and qr_value not in svg
        assert not any('jsdelivr' in url for _, url in requests[qr_requests:])
        print('PASS independent QR decode, PNG/SVG downloads, no Python on QR page', flush=True)

        go('ip-calculator')
        page.locator('#text').fill('192.168.10.37/27')
        page.locator('#other').fill('192.168.10.40')
        run()
        assert '192.168.10.32/27' in page.locator('#result-text').input_value()
        page.locator('.language-switch').select_option('ru')
        expect(page.locator('#result-details')).to_contain_text('Содержит IP-адрес')
        expect(page.locator('#result-details')).to_contain_text('Да')
        page.locator('#mode').select_option('collapse')
        expect(page.locator('#other-field')).to_be_hidden()
        page.locator('#text').fill('10.0.0.0/25\n10.0.0.128/25')
        page.locator('button[type=submit]').click()
        expect(page.locator('#status')).to_contain_text('Готово.', timeout=180_000)
        expect(page.locator('#result-text')).to_have_value('10.0.0.0/24')
        page.locator('.language-switch').select_option('en')

        go('bitwise-calculator')
        page.locator('#width').select_option('64')
        page.locator('#text').fill('18446744073709551615')
        run()
        assert '0xFFFFFFFFFFFFFFFF' in page.locator('#result-text').input_value()
        page.locator('#width').select_option('8')
        page.locator('#text').fill('0xFF')
        page.locator('#mode').select_option('right')
        expect(page.locator('#shift-field')).to_be_visible()
        run()
        assert '0x7F' in page.locator('#result-text').input_value()
        page.locator('#mode').select_option('and')
        page.locator('#other').fill('0x0F')
        expect(page.locator('#shift-field')).to_be_hidden()
        run()
        assert '0x0F' in page.locator('#result-text').input_value()

        go('hex-viewer')
        page.locator('#text').fill('01 00 00 00')
        page.locator('#endian').select_option('big')
        run()
        expect(page.locator('#result-details')).to_contain_text('16777216')
        page.locator('#mode').select_option('file')
        expect(page.locator('#text-field')).to_be_hidden()
        # A whole-file read would fail; only Blob.slice(...).arrayBuffer() is allowed.
        page.evaluate("() => { File.prototype.arrayBuffer = () => { throw new Error('Whole-file read attempted'); }; }")
        page.locator('#file').set_input_files({'name':'bytes.bin', 'mimeType':'application/octet-stream', 'buffer': b'X' * 4096 + bytes([1,0,0,0])})
        page.locator('#offset').fill('4096')
        run()
        assert page.locator('#result-text').input_value().startswith('00001000  01 00 00 00')
        with page.expect_download() as download:
            page.locator('#download').click()
        assert Path(download.value.path()).read_text() == page.locator('#result-text').input_value()
        page.locator('#offset').fill('4100')
        page.locator('button[type=submit]').click()
        expect(page.locator('#status')).to_have_class('error')
        for route in ['ip-calculator', 'bitwise-calculator', 'hex-viewer']:
            go(route)
            page.locator('.language-switch').select_option('ru')
            page.set_viewport_size({'width': 320, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), route
            page.locator('.language-switch').select_option('en')
        page.set_viewport_size({'width': 1440, 'height': 1100})
        print('PASS CIDR merging, exact 64-bit arithmetic, file windows, endian decoding, RU and mobile', flush=True)

        # A >64 MiB file proves the hash path no longer uses the old full-file cap.
        go('file-hash')
        with tempfile.TemporaryDirectory() as directory:
            large = Path(directory) / 'large.bin'
            digest = hashlib.sha256()
            chunk = b'01234567' * (1024 * 512)
            with large.open('wb') as output:
                for _ in range(17):
                    output.write(chunk)
                    digest.update(chunk)
            page.locator('#file').set_input_files(str(large))
            run()
            expect(page.locator('#result-text')).to_have_value(digest.hexdigest())
        print('PASS 68 MiB streamed hash across 17 chunks', flush=True)
        go('hash')
        page.locator('#file').set_input_files({'name': 'a' , 'mimeType': 'text/plain', 'buffer': b'abc'})
        page.locator('button[type=submit]').click()
        page.locator('#cancel').click()
        expect(page.locator('#status')).to_contain_text('cancelled')
        run()
        print('PASS cancellation and engine restart', flush=True)
        assert not errors, errors
        assert all(method == 'GET' for method, _ in requests), requests
        assert not any('example.com' in url for _, url in requests)
        assert all(url.startswith((base, 'https://cdn.jsdelivr.net/pyodide/v0.29.3/full/', f'blob:http://127.0.0.1:{server.server_port}/')) for _, url in requests), requests
        print('PASS no page errors; network limited to static assets and runtime GET requests', flush=True)
        restricted = browser.new_context()
        restricted.add_init_script("Object.defineProperty(window, 'localStorage', {get() {throw new Error('Storage disabled')}})")
        restricted_page = restricted.new_page()
        restricted_page.goto(base)
        restricted_page.locator('.language-switch').select_option('ru')
        expect(restricted_page.locator('html')).to_have_attribute('lang', 'ru')
        restricted.close()
        print('PASS language switch with browser storage disabled', flush=True)
        browser.close()
finally:
    server.shutdown()
