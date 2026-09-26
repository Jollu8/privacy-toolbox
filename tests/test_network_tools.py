import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from dispatch import dispatch, execute_tool


def call(tool, data=b'', **options):
    return json.loads(dispatch(tool, options, data))


class NetworkToolsTests(unittest.TestCase):
    def test_ipv4_normalization_membership_and_overlap(self):
        fields = call('ip-calculator', text='192.168.10.37/27', other='192.168.10.40')['fields']
        self.assertEqual(fields['Network'], '192.168.10.32/27')
        self.assertEqual(fields['Netmask'], '255.255.255.224')
        self.assertEqual(fields['Broadcast address'], '192.168.10.63')
        self.assertEqual(fields['Host addresses'], '30')
        self.assertTrue(fields['Contains IP address'])
        self.assertFalse(call('ip-calculator', text='192.168.10.37/27', other='192.168.10.64')['fields']['Contains IP address'])
        self.assertTrue(call('ip-calculator', text='192.168.10.37/27', other='192.168.10.32/28')['fields']['Contains compared network'])
        self.assertTrue(call('ip-calculator', text='192.168.10.37/27', other='192.168.10.0/24')['fields']['Networks overlap'])

    def test_large_ipv6_and_point_to_point_ranges(self):
        fields = call('ip-calculator', text='::/0')['fields']
        self.assertEqual(fields['Total addresses'], str(2**128))
        self.assertEqual(fields['Host addresses'], str(2**128-1))
        self.assertNotIn('Broadcast address', fields)
        for value, count in [('10.0.0.0/31','2'),('10.0.0.1/32','1'),('2001:db8::/127','2'),('2001:db8::1/128','1')]:
            self.assertEqual(call('ip-calculator', text=value)['fields']['Host addresses'], count)

    def test_merge_and_invalid_networks(self):
        result = call('ip-calculator', mode='collapse', text='10.0.0.0/25\n10.0.0.128/25\n10.0.0.1/32\n10.0.2.0/24')
        self.assertEqual(result['text'], '10.0.0.0/24\n10.0.2.0/24')
        for options in [dict(text='bad'),dict(text='10.0.0.0/24',other='::1'),dict(mode='collapse',text='10.0.0.0/24\n::/64'),dict(mode='collapse',text='::/64\n'*1025)]:
            with self.assertRaises(ValueError): call('ip-calculator', **options)

    def test_exact_64_bit_numbers(self):
        fields = call('bitwise-calculator', width='64', text='18446744073709551615')['fields']
        self.assertEqual(fields['HEX'], '0xFFFFFFFFFFFFFFFF')
        self.assertEqual(fields['DEC (signed)'], '-1')
        self.assertEqual(fields['DEC (unsigned)'], '18446744073709551615')
        self.assertEqual(call('bitwise-calculator', width=64, text='-9223372036854775808')['fields']['HEX'], '0x8000000000000000')

    def test_masks_shifts_and_ranges(self):
        for mode, expected in [('and','0x0F'),('or','0xFF'),('xor','0xF0'),('not','0x00'),('left','0xFE'),('right','0x7F'),('arithmetic','0xFF')]:
            self.assertEqual(call('bitwise-calculator',width=8,text='0xFF',other='15',mode=mode,shift=1)['fields']['HEX'], expected)
        self.assertEqual(call('bitwise-calculator',width=8,text='0010')['fields']['DEC (unsigned)'], '10')
        for options in [dict(text='256',width=8),dict(text='-129',width=8),dict(text='0x1',mode='left',shift=8,width=8),dict(text='0b12'),dict(text='1',width=12)]:
            with self.assertRaises(ValueError): call('bitwise-calculator', **options)

    def test_hex_endian_and_ascii(self):
        result = call('hex-viewer', text='01 00 00 00 FF 41 42 43', width=4)
        self.assertEqual(result['fields']['DEC (unsigned)'], '1')
        self.assertEqual(result['fields']['Reversed bytes'], '00 00 00 01')
        self.assertIn('|.....ABC|', result['text'])
        self.assertEqual(call('hex-viewer',text='01 00 00 00',endian='big')['fields']['DEC (unsigned)'], '16777216')
        self.assertEqual(call('hex-viewer',text='FF',width=1)['fields']['DEC (signed)'], '-1')
        self.assertIn('Word decoding',call('hex-viewer',text='FF',width=8)['fields'])
        self.assertTrue(call('hex-viewer',text='AA BB CC',offset=1)['text'].startswith('00000001  BB CC'))

    def test_file_window_and_invalid_hex(self):
        result = call('hex-viewer', data=b'\x01\x00\x00\x00',mode='file',offset=65536,total_size=65540)
        self.assertTrue(result['text'].startswith('00010000'))
        self.assertEqual(result['fields']['Total bytes'],'65540')
        for options in [dict(text='A'),dict(text='GG'),dict(text=''),dict(text='00',offset=1),dict(text='00'*4097),dict(text='00',width=3)]:
            with self.assertRaises(ValueError): call('hex-viewer', **options)
        error = json.loads(execute_tool('hex-viewer', {'text':'GG'}))
        self.assertFalse(error['success'])
        self.assertEqual(error['error']['code'],'INVALID_INPUT')
