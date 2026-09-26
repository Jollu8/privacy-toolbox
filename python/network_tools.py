"""Local network and fixed-width binary utilities; no socket or shell access."""
import ipaddress
import re


def integer(value, minimum, maximum, message):
    try:
        parsed = int(str(value), 10)
    except (ValueError, TypeError):
        raise ValueError(message) from None
    if not minimum <= parsed <= maximum:
        raise ValueError(message)
    return parsed


def network_tools(options):
    text = options.get('text', '').strip()
    mode = options.get('mode', 'inspect')
    if mode == 'collapse':
        lines = text.splitlines()
        if not 1 <= len(lines) <= 1024:
            raise ValueError('Enter between 1 and 1024 networks, one per line.')
        try:
            networks = [ipaddress.ip_network(line.strip(), strict=False) for line in lines]
            if len({n.version for n in networks}) != 1:
                raise ValueError()
        except ValueError:
            raise ValueError('Enter valid networks of the same IP version.') from None
        values = [str(n) for n in ipaddress.collapse_addresses(networks)]
        return {'text': '\n'.join(values), 'fields': {'Input networks': str(len(lines)), 'Merged networks': str(len(values))}}
    if mode != 'inspect':
        raise ValueError('Choose a supported network operation.')
    try:
        interface = ipaddress.ip_interface(text)
    except ValueError:
        raise ValueError('Enter a valid IPv4 or IPv6 address with an optional prefix.') from None
    network = interface.network
    first, last = int(network.network_address), int(network.broadcast_address)
    # Match ipaddress.hosts() without ever enumerating a large IPv6 network.
    if network.version == 4 and network.prefixlen < 31:
        first += 1
        last -= 1
    elif network.version == 6 and network.prefixlen < 127:
        first += 1
    address = ipaddress.IPv4Address if network.version == 4 else ipaddress.IPv6Address
    fields = {'IP version': f'IPv{network.version}', 'IP address': str(interface.ip),
              'Network': str(network), 'Netmask': str(network.netmask),
              'Host mask': str(network.hostmask), 'Total addresses': str(network.num_addresses),
              'First host': str(address(first)), 'Last host': str(address(last)),
              'Host addresses': str(last - first + 1)}
    if network.version == 4:
        fields['Broadcast address'] = str(network.broadcast_address)
    other = options.get('other', '').strip()
    if other:
        try:
            if '/' in other:
                peer = ipaddress.ip_network(other, strict=False)
                if peer.version != network.version:
                    raise ValueError()
                fields['Networks overlap'] = network.overlaps(peer)
                fields['Contains compared network'] = peer.subnet_of(network)
            else:
                peer = ipaddress.ip_address(other)
                if peer.version != network.version:
                    raise ValueError()
                fields['Contains IP address'] = peer in network
        except ValueError:
            raise ValueError('The comparison must be a valid IP or network of the same version.') from None
    return {'text': '\n'.join(f'{key}: {value}' for key, value in fields.items()), 'fields': fields}


def bitwise(options):
    width = integer(options.get('width', 32), 8, 64, 'Choose 8, 16, 32, or 64 bits.')
    if width not in {8, 16, 32, 64}:
        raise ValueError('Choose 8, 16, 32, or 64 bits.')
    mask = (1 << width) - 1

    def operand(value):
        value = str(value).strip()
        if len(value) > 128 or not re.fullmatch(r'[+-]?(?:0[xX][0-9a-fA-F]+|0[bB][01]+|0[oO][0-7]+|[0-9]+)', value):
            raise ValueError('Use decimal integers or 0x, 0b, 0o prefixes.')
        digits = value.lstrip('+-').lower()
        number = int(value, 0 if digits.startswith(('0x', '0b', '0o')) else 10)
        if not -(1 << (width - 1)) <= number <= mask:
            raise ValueError('An operand does not fit the selected bit width.')
        return number & mask

    a = operand(options.get('text', ''))
    mode = options.get('mode', 'convert')
    if mode in {'and', 'or', 'xor'}:
        b = operand(options.get('other', ''))
        result = {'and': a & b, 'or': a | b, 'xor': a ^ b}[mode]
    elif mode in {'left', 'right', 'arithmetic'}:
        shift = integer(options.get('shift', 1), 0, width - 1, 'Shift must be between zero and bit width minus one.')
        signed = a - (1 << width) if a & (1 << (width - 1)) else a
        result = (a << shift if mode == 'left' else signed >> shift if mode == 'arithmetic' else a >> shift) & mask
    elif mode == 'not':
        result = (~a) & mask
    elif mode == 'convert':
        result = a
    else:
        raise ValueError('Choose a supported bitwise operation.')
    fields = {'HEX': f'0x{result:0{width // 4}X}', 'DEC (unsigned)': str(result),
              'DEC (signed)': str(result - (1 << width) if result & (1 << (width - 1)) else result),
              'BIN': f'{result:0{width}b}', 'OCT': f'0o{result:o}'}
    return {'text': '\n'.join(f'{key}: {value}' for key, value in fields.items()), 'fields': fields}


def hex_view(options, data):
    mode = options.get('mode', 'hex')
    offset = integer(options.get('offset', 0), 0, 2**53 - 1, 'Enter a non-negative safe integer offset.')
    width = integer(options.get('width', 4), 1, 8, 'Choose a word size of 1, 2, 4, or 8 bytes.')
    if width not in {1, 2, 4, 8}:
        raise ValueError('Choose a word size of 1, 2, 4, or 8 bytes.')
    endian = options.get('endian', 'little')
    if endian not in {'little', 'big'}:
        raise ValueError('Choose little-endian or big-endian.')
    if mode == 'hex':
        text = options.get('text', '')
        compact = re.sub(r'\s', '', text)
        if len(compact) > 8192:
            raise ValueError('Paste at most 4096 bytes of hexadecimal input.')
        if len(compact) % 2 or not re.fullmatch('[0-9a-fA-F]*', compact):
            raise ValueError('Enter complete hexadecimal byte pairs, for example 01 00 FF.')
        source = bytes.fromhex(compact)
        total = len(source)
        data = source[offset:offset + 4096]
    elif mode == 'file':
        # The browser transfers only the selected window, never the full file.
        total = integer(options.get('total_size', len(data)), 0, 2**53 - 1, 'Invalid file size.')
        if len(data) > 4096 or len(data) != min(4096, max(0, total - offset)):
            raise ValueError('Invalid hex preview window.')
    else:
        raise ValueError('Choose hexadecimal input or a file.')
    if not total or offset >= total:
        raise ValueError('The offset must point to a byte in non-empty input.')
    rows = []
    for start in range(0, len(data), 16):
        chunk = data[start:start + 16]
        hexes = ' '.join(f'{byte:02X}' for byte in chunk)
        ascii_text = ''.join(chr(byte) if 32 <= byte <= 126 else '.' for byte in chunk)
        rows.append(f'{offset + start:08X}  {hexes:<47}  |{ascii_text}|')
    fields = {'Total bytes': str(total), 'Offset': str(offset), 'Displayed bytes': str(len(data))}
    if len(data) >= width:
        word = data[:width]
        fields.update({'Selected bytes': word.hex(' ').upper(), 'Byte order': endian + '-endian',
                       'DEC (unsigned)': str(int.from_bytes(word, endian)),
                       'DEC (signed)': str(int.from_bytes(word, endian, signed=True)),
                       'Reversed bytes': word[::-1].hex(' ').upper()})
    else:
        fields['Word decoding'] = 'Not enough bytes for the selected word size.'
    return {'text': '\n'.join(rows), 'fields': fields, 'extension': 'txt'}


def run(action, options, data=b''):
    if action == 'ip-calculator':
        return network_tools(options)
    if action == 'bitwise-calculator':
        return bitwise(options)
    if action == 'hex-viewer':
        return hex_view(options, data)
    raise ValueError('Unknown network tool.')
