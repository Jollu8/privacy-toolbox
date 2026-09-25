"""CSV conversion, percent encoding, timestamps and unverified JWT inspection."""
import base64
import binascii
import csv
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO
from urllib.parse import quote, unquote
from json_tool import parse_json

csv.field_size_limit(8 * 1024 * 1024)

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def run(tool, options):
    text = options.get('text', '')
    if tool == 'csv-json':
        if options.get('mode', 'csv-json') == 'csv-json':
            try:
                rows = list(csv.reader(StringIO(text.removeprefix('\ufeff'), newline=''), strict=True))
            except csv.Error as exc:
                raise ValueError(f'Invalid CSV: {exc}') from exc
            if not rows:
                return {'text': '[]', 'extension': 'json'}
            keys = rows[0]
            if not keys or any(not key.strip() for key in keys) or len(set(keys)) != len(keys):
                raise ValueError('CSV headers must be non-empty and unique.')
            result = []
            for number, row in enumerate(rows[1:], 2):
                if len(row) != len(keys):
                    raise ValueError(f'CSV record {number} has {len(row)} fields; expected {len(keys)}.')
                result.append(dict(zip(keys, row)))
            return {'text': json.dumps(result, ensure_ascii=False, indent=2), 'extension': 'json'}
        values = parse_json(text)
        if not isinstance(values, list) or any(not isinstance(row, dict) for row in values):
            raise ValueError('Use a JSON array of objects.')
        keys = list(dict.fromkeys(key for row in values for key in row))
        if values and not keys:
            raise ValueError('Objects must contain at least one field.')
        result = StringIO(newline='')
        writer = csv.writer(result, lineterminator='\r\n')
        def cell(value):
            if isinstance(value, (dict, list)):
                raise ValueError('CSV fields must be scalar values, not nested arrays or objects.')
            value = '' if value is None else str(value).lower() if isinstance(value, bool) else str(value)
            if options.get('safe_export', True) and (value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n'))):
                value = "'" + value
            return value
        if keys:
            writer.writerow([cell(key) for key in keys])
        for row in values:
            writer.writerow([cell(row.get(key)) for key in keys])
        return {'text': result.getvalue(), 'extension': 'csv', 'details': ['Missing/null fields become empty CSV fields.']}
    if tool == 'url-encoder':
        if options.get('mode', 'encode') == 'encode':
            safe = ":/?#[]@!$&'()*+,;=" if options.get('scope') == 'full' else ''
            return {'text': quote(text, safe=safe), 'extension': 'txt'}
        if re.search(r'%(?![0-9a-fA-F]{2})', text):
            raise ValueError('Invalid percent escape. Use two hexadecimal digits after %.')
        try:
            return {'text': unquote(text, encoding='utf-8', errors='strict'), 'extension': 'txt'}
        except UnicodeDecodeError as exc:
            raise ValueError('Percent-encoded bytes are not valid UTF-8.') from exc
    if tool == 'timestamp':
        try:
            if options.get('mode', 'unix') == 'unix':
                value = Decimal(text.strip())
                if not value.is_finite():
                    raise ValueError('Enter a finite timestamp.')
                microseconds = value * (1000 if options.get('unit') == 'milliseconds' else 1_000_000)
                if microseconds != microseconds.to_integral_value():
                    raise ValueError('Timestamp supports precision up to one microsecond.')
                date = EPOCH + timedelta(microseconds=int(microseconds))
            else:
                date = datetime.fromisoformat(text.strip().replace('Z', '+00:00'))
                if date.tzinfo is None:
                    date = date.replace(tzinfo=timezone.utc)
                date = date.astimezone(timezone.utc)
        except (ValueError, OverflowError, InvalidOperation) as exc:
            raise ValueError('Enter a timestamp in the selected unit or an ISO 8601 date (years 1–9999).') from exc
        delta = date - EPOCH
        micros = (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds
        seconds = format(Decimal(micros) / 1_000_000, 'f')
        milliseconds = format(Decimal(micros) / 1000, 'f')
        iso = date.isoformat().replace('+00:00', 'Z')
        return {'text': f'UTC: {iso}\nISO 8601: {iso}\nUnix seconds: {seconds}\nUnix milliseconds: {milliseconds}',
                'iso': iso, 'extension': 'txt'}
    if tool == 'jwt-decoder':
        parts = text.strip().split('.')
        if len(parts) != 3:
            raise ValueError('Expected three JWT segments. Encrypted JWE is not supported.')
        def decode(segment):
            if not segment or not re.fullmatch(r'[A-Za-z0-9_-]+', segment):
                raise ValueError('Invalid JWT base64url segment.')
            try:
                value = parse_json(base64.b64decode(segment + '=' * (-len(segment) % 4), altchars=b'-_', validate=True).decode('utf-8'))
            except (binascii.Error, UnicodeDecodeError) as exc:
                raise ValueError('JWT contains invalid base64url or UTF-8.') from exc
            if not isinstance(value, dict):
                raise ValueError('JWT header and payload must be JSON objects.')
            return value
        header, payload = decode(parts[0]), decode(parts[1])
        if parts[2] and not re.fullmatch(r'[A-Za-z0-9_-]+', parts[2]):
            raise ValueError('Invalid JWT signature encoding.')
        details = ['Signature NOT verified. All claims below are untrusted.']
        for key, name in [('iat', 'Issued at'), ('exp', 'Expires at'), ('nbf', 'Not before')]:
            if key in payload:
                try:
                    value = payload[key]
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        raise ValueError()
                    date = EPOCH + timedelta(seconds=value)
                    details.append(f'{name} (unverified): {date.isoformat()}')
                except (ValueError, OverflowError):
                    details.append(f'{name}: invalid date claim')
        for key in ['iss', 'aud']:
            if key in payload:
                details.append(f'{key} (unverified): {json.dumps(payload[key], ensure_ascii=False)}')
        return {'text': 'Header\n' + json.dumps(header, indent=2, ensure_ascii=False) + '\n\nPayload\n' + json.dumps(payload, indent=2, ensure_ascii=False),
                'details': details, 'sensitive': True}
    raise ValueError('Unknown data tool.')
