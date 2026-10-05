"""Change only normal dialogue/name top margins in the verified DTFA skin."""
import struct
from reinject import crc

SOURCE = {'path': 'Data/skin.bin', 'size': 31403,
          'sha256': '7fcb933dd6b1bdb71638d2e3d3db94620f695495832b8dda823f81ab4e06ad65'}


def parse(data):
    assert data[:8] == b'DTFA\0\0\x02\0' and crc(data[:8]) == data[8:10]
    p, stack, rows = 10, [], []
    while p < len(data):
        start = p
        assert data[p:p+4] == b'DATA' and crc(data[p:p+10]) == data[p+10:p+12]
        opcode, count = struct.unpack_from('<IH', data, p+4)
        assert opcode in (0, 1, 2, 3)
        p += 12
        operands = []
        for _ in range(count):
            _, length, kind = struct.unpack_from('<HHI', data, p)
            assert crc(data[p:p+8]) == data[p+8:p+10]
            raw = data[p+10:p+10+length]
            assert len(raw) == length and crc(raw) == data[p+10+length:p+12+length]
            decoded = bytes(v ^ 0x73 for v in raw)
            assert decoded.endswith(b'\0')
            operands.append({'offset': p, 'length': length, 'kind': kind,
                             'value': decoded[:-1].decode('cp932')})
            p += 12+length
        values = [r['value'] for r in operands]
        rows.append({'offset': start, 'opcode': opcode, 'scope': tuple(stack), 'operands': operands})
        if opcode == 1:
            stack.append('/'.join(values))
        elif opcode == 2:
            assert stack and count == 0
            stack.pop()
        elif opcode == 3:
            assert not stack and count == 0 and p == len(data)
    assert p == len(data) and not stack
    return rows


def adjust(data):
    before = parse(data)
    output = bytearray(data)
    changes = []
    allowed = set()
    for window, old, new in [('MessageWindow', '20', '17'), ('NameWindow', '6', '3')]:
        rows = [r for r in before if r['scope'] == ('Skin/Normal', window, 'Text')
                and r['opcode'] == 0 and r['operands'][0]['value'] == 'AreaMargin']
        assert len(rows) == 1
        operand = rows[0]['operands'][2]
        assert operand['value'] == old and operand['kind'] == 2
        raw = bytes(v ^ 0x73 for v in (new+'\0').encode('ascii'))
        assert len(raw) == operand['length']
        at = operand['offset']+10
        output[at:at+len(raw)+2] = raw+crc(raw)
        allowed.update(range(at, at+len(raw)+2))
        changes.append({'scope': list(rows[0]['scope']), 'command': 'AreaMargin',
                        'argument': 'top', 'old': int(old), 'new': int(new),
                        'pixel_shift_y': -3, 'operand_offset': operand['offset']})
    output = bytes(output)
    after = parse(output)
    assert len(output) == len(data) and len(before) == len(after)
    assert all(a == b or i in allowed for i, (a, b) in enumerate(zip(data, output)))
    changed_operands = {c['operand_offset'] for c in changes}
    for a, b in zip(before, after):
        if not any(o['offset'] in changed_operands for o in a['operands']):
            assert a == b
        else:
            assert a['scope'] == b['scope'] and a['opcode'] == b['opcode']
            for x, y in zip(a['operands'], b['operands']):
                if x['offset'] not in changed_operands:
                    assert x == y
    return output, {'all_passed': True, 'changes': changes, 'command_count': len(before),
                    'crc_and_structure_valid': True, 'outside_target_bytes_exact': True,
                    'background_positions_unchanged': True, 'font_and_line_spacing_unchanged': True,
                    'battle_and_debug_skins_unchanged': True, 'size_preserved': True}


def build(source):
    source.files[SOURCE['path']] = SOURCE
    original = source.read(SOURCE['path'])
    output, report = adjust(original)
    return output, report
