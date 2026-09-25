"""Cryptographic generators; never fall back to a non-cryptographic RNG."""
import base64
import math
from itertools import combinations
import secrets
import string
import uuid


def integer(options, key, default, low, high):
    try:
        value = int(options.get(key, default))
    except (ValueError, TypeError) as exc:
        raise ValueError(f'{key} must be an integer.') from exc
    if not low <= value <= high:
        raise ValueError(f'{key} must be between {low} and {high}.')
    return value


def run(tool, options):
    if tool == 'password-generator':
        length = integer(options, 'length', 20, 4, 256)
        groups = [chars for key, chars in [('uppercase', string.ascii_uppercase),
                  ('lowercase', string.ascii_lowercase), ('numbers', string.digits),
                  ('symbols', '!@#$%^&*()-_=+[]{}:,.?')] if options.get(key, True)]
        if options.get('avoid_similar', False):
            groups = [''.join(c for c in group if c not in 'Il1O0o') for group in groups]
        if not groups:
            raise ValueError('Select at least one character group.')
        alphabet = ''.join(groups)
        # Count valid strings by inclusion-exclusion for the selected disjoint groups.
        possibilities = 0
        for count in range(len(groups) + 1):
            for excluded in combinations(groups, count):
                possibilities += (-1) ** count * (len(alphabet) - sum(map(len, excluded))) ** length
        entropy = math.log2(possibilities)
        strength = 'Very strong' if entropy >= 100 else 'Strong' if entropy >= 80 else 'Moderate' if entropy >= 60 else 'Low'
        while True:
            password = ''.join(secrets.choice(alphabet) for _ in range(length))
            if all(any(c in group for c in password) for group in groups):
                return {'text': password, 'details': [f'{length} characters · cryptographic randomness',
                        f'Estimated strength: {strength} · {entropy:.1f} bits of generation entropy',
                        'Strength depends on length, selected groups, and how the password is stored.'], 'sensitive': True}
    if tool == 'uuid-generator':
        count = integer(options, 'amount', 5, 1, 1000)
        values = [str(uuid.uuid4()) for _ in range(count)]
        return {'text': '\n'.join(values), 'items': values, 'extension': 'txt', 'details': [f'{count} UUID v4 values']}
    if tool == 'random-token':
        count = integer(options, 'bytes', 32, 1, 1024)
        mode = options.get('mode', 'urlsafe')
        if mode == 'hex':
            value = secrets.token_hex(count)
        elif mode == 'urlsafe':
            value = secrets.token_urlsafe(count)
        elif mode == 'base64':
            value = base64.b64encode(secrets.token_bytes(count)).decode('ascii')
        else:
            raise ValueError('Choose a supported token encoding.')
        return {'text': value, 'details': [f'Entropy: {count * 8} bits · {count} random bytes'], 'sensitive': True}
    raise ValueError('Unknown generator.')
