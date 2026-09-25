"""File checksums, including legacy interoperability algorithms."""
import hashlib

ALGORITHMS = {"sha256", "sha384", "sha512", "sha1", "md5"}


def calculate_hash(data: bytes, algorithm: str = "sha256") -> str:
    if algorithm not in ALGORITHMS:
        raise ValueError("Choose a supported hash algorithm.")
    return hashlib.new(algorithm, data, usedforsecurity=False).hexdigest()


_active_hash = None


def stream_hash(operation, data=b'', algorithm='sha256'):
    """One bounded-memory stream per worker; chunk acknowledgement provides backpressure."""
    global _active_hash
    if operation == 'hash-start':
        if algorithm not in ALGORITHMS:
            raise ValueError('Choose a supported hash algorithm.')
        _active_hash = hashlib.new(algorithm, usedforsecurity=False)
        return {'details': ['Hash stream started.']}
    if _active_hash is None:
        raise ValueError('Start a hash stream first.')
    if operation == 'hash-chunk':
        if len(data) > 4 * 1024 * 1024:
            raise ValueError('Hash chunks must be at most 4 MiB.')
        _active_hash.update(data)
        return {}
    if operation == 'hash-finish':
        result = _active_hash.hexdigest()
        _active_hash = None
        return {'text': result, 'extension': 'txt'}
    raise ValueError('Unknown hash stream operation.')
