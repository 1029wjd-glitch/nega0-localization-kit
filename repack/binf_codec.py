"""BINF typed rows, based on the original executable's row readers.

CRC covers raw numeric/length bytes and ROL1-decoded strings including NUL.
The 32-byte header is raw; every row ends with a big-endian CRC16.
"""
import struct
from pathlib import Path

from reinject import crc, encoded


def schema_for(name):
    name = Path(name).name
    if name == 'CharDefines.bin':
        return [2]+[('s', c) for c in [24, 32, 24, 24]+[32]*7]+[4]+[('s', c) for c in [32]*4+[48]*3+[32]*3]+[4]
    if name == 'CharProfile.bin':
        return [('s', 32), ('count', 2)]
    if name == 'ItemExp.bin' or name.startswith('SkillExp'):
        return [('s', 48), 2]+[('s', 590)]*4
    if name == 'ItemData.bin':
        return [2, ('s', 32), ('s', 26), 4]+[4, 2]*3
    if name.startswith('Skill') and not name.startswith('SkillDeck'):
        return [2, ('s', 32), ('s', 26), 4, 2]+[4]*4+[2]*6+[4]+[4, 2]*2+[4, 2, 2]
    raise ValueError('unsupported BINF schema: '+name)


def rol1(data):
    return bytes(((v << 1) | (v >> 7)) & 255 for v in data)


def ror1(data):
    return bytes(((v >> 1) | (v << 7)) & 255 for v in data)


def parse_binf(name, data):
    if len(data) < 32 or data[:8] != b'BINF\x01\0\0\0':
        raise ValueError('BINF header')
    count = struct.unpack_from('<I', data, 8)[0]
    schema = schema_for(name)
    rows = []
    p = 32
    for row_index in range(count):
        start = p
        checksum = bytearray()
        fields = []
        specs = list(schema)
        field_index = 0
        while field_index < len(specs):
            spec = specs[field_index]
            at = p
            if isinstance(spec, int) or spec[0] == 'count':
                size = spec if isinstance(spec, int) else spec[1]
                raw = data[p:p+size]
                if len(raw) != size:
                    raise ValueError('BINF numeric bounds')
                p += size
                checksum.extend(raw)
                fields.append({'kind': 'numeric', 'offset': at, 'stored': raw})
                if not isinstance(spec, int):
                    descriptions = struct.unpack('<H', raw)[0]
                    if descriptions > 1024:
                        raise ValueError('BINF profile description count')
                    specs.extend([('s', 1024)]*descriptions)
            else:
                if p+4 > len(data):
                    raise ValueError('BINF string length bounds')
                length = struct.unpack_from('<I', data, p)[0]
                checksum.extend(data[p:p+4])
                p += 4
                if length > 30000 or p+length+(length > 0) > len(data):
                    raise ValueError('BINF string bounds')
                raw = rol1(data[p:p+length+1]) if length else b''
                if length and (raw[-1] != 0 or b'\0' in raw[:-1]):
                    raise ValueError('BINF string terminator')
                checksum.extend(raw)
                p += len(raw)
                fields.append({'kind': 'string', 'offset': at, 'byte_offset': at+4,
                               'raw': raw[:-1] if length else b'', 'stored': data[at:p],
                               'capacity_bytes': spec[1], 'field_index': field_index})
            field_index += 1
        if crc(checksum) != data[p:p+2]:
            raise ValueError(f'BINF row CRC: {Path(name).name} row={row_index} offset={p:#x}')
        p += 2
        rows.append({'index': row_index, 'offset': start, 'end': p, 'fields': fields})
    if p != len(data):
        raise ValueError('BINF trailing bytes')
    return rows


def inject_binf(name, data, records, translations):
    rows = parse_binf(name, data)
    changes = {r['target']['length_field_offset']: r for r in records}
    if len(changes) != len(records):
        raise ValueError('duplicate BINF translation locator')
    out = bytearray(data[:32])
    applied = {}
    for row in rows:
        checksum = bytearray()
        for field in row['fields']:
            r = changes.get(field['offset'])
            if r is None:
                out.extend(field['stored'])
                checksum.extend(field['stored'] if field['kind'] == 'numeric' else
                                field['stored'][:4]+(field['raw']+b'\0' if field['raw'] else b''))
                continue
            target = r['target']
            if field['kind'] != 'string' or field['byte_offset'] != target['byte_offset'] or field['raw'].hex() != target['source_bytes_hex']:
                raise ValueError('BINF source field mismatch: '+r['id'])
            # Internal row keys stay original; only actual display fields may change.
            key_index = 1 if Path(name).name == 'CharDefines.bin' or Path(name).name == 'ItemData.bin' or Path(name).name.startswith('Skill') and not Path(name).name.startswith('SkillExp') else 0
            text = translations[r['id']]
            if field['field_index'] == key_index and text != r['source']:
                raise ValueError('BINF internal key translation: '+r['id'])
            raw = field['raw'] if text == r['source'] else encoded(text)
            units = len(text.encode('utf-16le'))//2
            capacity = field['capacity_bytes']//2
            if Path(name).name == 'CharProfile.bin' and field['field_index'] >= 2:
                capacity = min(capacity, 286)  # First description copied into 0x23c bytes.
            if units+1 > capacity or len(raw)+1 > 2048:
                raise ValueError(f'BINF display capacity: {r["id"]} units={units} capacity={capacity-1} bytes={len(raw)}')
            at = len(out)
            length = struct.pack('<I', len(raw))
            out.extend(length+ror1(raw+b'\0'))
            checksum.extend(length+raw+b'\0')
            applied[r['id']] = {'byte_offset': at+4, 'byte_length': len(raw), 'row_index': row['index'], 'field_index': field['field_index']}
        out.extend(crc(checksum))
    if len(applied) != len(records):
        missing = [r['id'] for r in records if r['id'] not in applied]
        raise ValueError('BINF targets outside typed fields: '+', '.join(missing))
    saved = parse_binf(name, bytes(out))
    for old_row, new_row in zip(rows, saved):
        for old, new in zip(old_row['fields'], new_row['fields']):
            r = changes.get(old['offset'])
            if r is None and new['stored'] != old['stored']:
                raise ValueError('BINF non-target field changed')
            if r is not None:
                text = translations[r['id']]
                expected = old['raw'] if text == r['source'] else encoded(text)
                if new['raw'] != expected:
                    raise ValueError('BINF saved translation mismatch')
    return bytes(out), applied
