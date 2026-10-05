"""Nega0 serializers. Original bytes are immutable; callers save separate outputs."""
from __future__ import annotations
import binascii
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from formats import Archive, wag_key, wag_xor
from display_codec import encode_display

MARKER = b'\xef\xbb\xbf'


def crc(data: bytes) -> bytes:
    return struct.pack('>H', binascii.crc_hqx(data, 0))


def checked(data: bytes) -> bytes:
    return data + crc(data)


def encoded(text: str) -> bytes:
    return encode_display(text)


def xor53(data: bytes) -> bytes:
    return bytes(v ^ 0x53 for v in data)


def nori_layout(data: bytes) -> dict:
    if data[:8] != b'NORI\0\0\x01\0' or crc(data[:40]) != data[40:42]:
        raise ValueError('NORI header or CRC')
    lc, ls, gc, gs, vc, vs, cs, ps = struct.unpack_from('<8I', data, 8)
    at = 42
    blocks = []
    for count, size in [(lc, ls), (gc, gs), (vc, vs)]:
        block = data[at:at+size]
        decoded = bytearray(block)
        p = 0
        for _ in range(count):
            length = struct.unpack('<I', xor53(block[p+4:p+8]))[0]
            if p+8+length > size:
                raise ValueError('NORI symbol bounds')
            decoded[p+4:p+8+length] = xor53(block[p+4:p+8+length])
            p += 8+length
        if p != size or crc(decoded) != data[at+size:at+size+2]:
            raise ValueError('NORI symbol CRC/size')
        blocks.append((at, size))
        at += size+2
    code_at = at
    pool_at = code_at+cs+2
    if pool_at+ps+2 != len(data):
        raise ValueError('NORI total length')
    for at, size in [(code_at, cs), (pool_at, ps)]:
        if crc(data[at:at+size]) != data[at+size:at+size+2]:
            raise ValueError('NORI code/pool CRC')
    return {'code_at': code_at, 'code_size': cs, 'pool_at': pool_at, 'pool_size': ps}


def inject_nori(data: bytes, records: list[dict], translations: dict[str, str]):
    layout = nori_layout(data)
    pool_at = layout['pool_at']
    pool = bytearray(data[pool_at:-2])
    prefix = bytearray(data[:pool_at-2])
    changes = {}
    groups = {}
    for r in records:
        t = r['target']; p = t['operand_offset']
        typ, size, ptr = struct.unpack_from('<HHI', data, p)
        if typ != 5 or size != t['byte_length'] or ptr != t['pool_relative_offset']:
            raise ValueError('NORI source operand mismatch: '+r['id'])
        raw = xor53(data[pool_at+ptr:pool_at+ptr+size])
        if raw.hex() != t['source_bytes_hex']:
            raise ValueError('NORI source bytes mismatch: '+r['id'])
        text = translations[r['id']]
        changes[p] = (raw if text == r['source'] else encoded(text), r)
        meta = r.get('context_meta', {})
        if 'message_metadata_offset' in meta:
            cmd = p - 16 - 8*meta['line_index']
            groups[cmd] = meta['message_metadata_offset'] - pool_at
    applied = {}
    touched_fields = []

    def point(p, raw, offset):
        if not 0 < len(raw) < 0x8000 or offset > 0xffffffff:
            raise ValueError('NORI field overflow')
        struct.pack_into('<HI', prefix, p+2, len(raw), offset)
        touched_fields.append((p+2, p+8))
        if p in changes:
            applied[changes[p][1]['id']] = {'byte_offset': pool_at+offset, 'byte_length': len(raw), 'operand_offset': p}

    grouped = set()
    for cmd, meta_offset in sorted(groups.items()):
        opcode, argc, result = struct.unpack_from('<HHi', data, cmd)
        typ, flags, original_meta = struct.unpack_from('<HHI', data, cmd+8)
        if opcode not in (1, 60) or result != argc-1 or typ != 3 or original_meta != meta_offset:
            raise ValueError('NORI message layout')
        positions = [cmd+16+8*i for i in range(argc-1)]
        segments = []
        expected = meta_offset+8
        for p in positions:
            typ, size, ptr = struct.unpack_from('<HHI', data, p)
            if typ != 5 or ptr != expected or ptr+size > layout['pool_size']:
                raise ValueError('NORI message contiguity')
            expected += size
            original = xor53(data[pool_at+ptr:pool_at+ptr+size])
            segments.append(changes[p][0] if p in changes else original)
        new_meta = len(pool)
        pool.extend(data[pool_at+meta_offset:pool_at+meta_offset+8])
        struct.pack_into('<I', prefix, cmd+12, new_meta)
        touched_fields.append((cmd+12, cmd+16))
        for p, raw in zip(positions, segments):
            point(p, raw, len(pool)); pool.extend(xor53(raw)); grouped.add(p)
    for p, (raw, _) in sorted(changes.items()):
        if p not in grouped:
            point(p, raw, len(pool)); pool.extend(xor53(raw))
    struct.pack_into('<I', prefix, 36, len(pool))
    prefix[40:42] = crc(prefix[:40])
    code_at = layout['code_at']
    result = bytes(prefix) + crc(prefix[code_at:]) + checked(pool)
    # Only listed scalar operands/header and the pool may change.
    expected_prefix = bytearray(data[:pool_at-2])
    for start, end in touched_fields + [(36, 42)]:
        expected_prefix[start:end] = prefix[start:end]
    if expected_prefix != prefix or result[pool_at:pool_at+layout['pool_size']] != data[pool_at:-2]:
        raise ValueError('NORI non-target bytes changed')
    nori_layout(result)
    if len(applied) != len(records):
        raise ValueError('NORI accounting')
    return result, applied


def inject_miko(name: str, data: bytes, replacements: dict[int, bytes]) -> bytes:
    archive = Archive(Path(name), data)
    if archive.kind != 'MIKO' or set(replacements)-set(range(len(archive.entries))):
        raise ValueError('MIKO replacement index')
    cadr = struct.unpack_from('<Q', data, 26)[0]
    entries = sorted(archive.entries, key=lambda e: e.container_offset)
    out = bytearray(data[:entries[0].container_offset])
    cursor = entries[0].container_offset
    for e in entries:
        if e.container_offset != cursor:
            raise ValueError('MIKO non-contiguous DATA layout')
        old_header = data[cursor:cursor+30]
        old_payload = archive.read(e)
        if checked(old_header[:28]) != old_header or crc(old_payload) != data[cursor+30+e.size:cursor+32+e.size]:
            raise ValueError('MIKO DATA CRC')
        cp = cadr+4+12*e.index
        if crc(data[cp:cp+10]) != data[cp+10:cp+12]:
            raise ValueError('MIKO address CRC')
        new_offset = len(out)
        payload = replacements.get(e.index, old_payload)
        header = bytearray(old_header[:28])
        struct.pack_into('<I', header, 24, len(payload))
        out.extend(checked(header)); out.extend(checked(payload))
        struct.pack_into('<Q', out, cp+2, new_offset)
        out[cp+10:cp+12] = crc(out[cp:cp+10])
        cursor += e.container_size+2
    if cursor != len(data):
        raise ValueError('MIKO unknown trailing structure')
    saved = Archive(Path(name), bytes(out))
    for old, new in zip(archive.entries, saved.entries):
        if old.name_raw != new.name_raw or saved.read(new) != replacements.get(old.index, archive.read(old)):
            raise ValueError('MIKO saved entry mismatch')
    return bytes(out)


def wag_layout(name: str, data: bytes):
    """Validate stored CRCs before decrypting, retaining logical chunk bytes."""
    archive = Archive(Path(name), data)
    if archive.kind != 'WAG':
        raise ValueError('WAG signature')
    first = archive.entries[0].container_offset
    if first < 76 or crc(data[:first-2]) != data[first-2:first]:
        raise ValueError('WAG header CRC')
    logical = []
    for entry in archive.entries:
        start = entry.container_offset
        if crc(data[start:start+8]) != data[start+8:start+10]:
            raise ValueError(f'WAG DSET CRC: {entry.index}')
        cursor = start+10
        chunks = []
        for chunk in entry.chunks:
            size = chunk['size']
            if cursor != chunk['offset'] or crc(data[cursor:cursor+8]) != data[cursor+8:cursor+10]:
                raise ValueError(f'WAG chunk header CRC: {entry.index}')
            body = cursor+10
            tag = chunk['tag']
            if tag == 'PICT':
                if size < 6 or crc(data[body:body+4]) != data[body+4:body+6]:
                    raise ValueError(f'WAG PICT flags CRC: {entry.index}')
                flags = wag_xor(data[body:body+4], body, archive.key)
                payload = wag_xor(data[body+6:body+size], body+6, archive.key)
                chunks.append((tag, flags, payload))
            elif tag == 'FTAG':
                if crc(data[body:body+size-2]) != data[body+size-2:body+size]:
                    raise ValueError(f'WAG FTAG CRC: {entry.index}')
                chunks.append((tag, wag_xor(data[body:body+size-2], body, archive.key)))
            else:
                raise ValueError(f'WAG unsupported chunk: {tag}')
            cursor += 10+size
        if cursor != start+entry.container_size or sum(c[0] == 'PICT' for c in chunks) != 1:
            raise ValueError(f'WAG entry layout: {entry.index}')
        logical.append(chunks)
    return archive, logical


def inject_wag(name: str, data: bytes, replacements: dict[int, bytes]) -> bytes:
    archive, logical = wag_layout(name, data)
    count = len(archive.entries)
    if set(replacements)-set(range(count)):
        raise ValueError('WAG replacement index')
    name_key = wag_key(Path(name).name.lower().encode('cp932'))
    index_at = 0x200+sum(name_key)
    for _ in range(2):
        for value in name_key:
            index_at ^= value
            index_at = ((index_at >> 1) | ((index_at & 1) << 31)) & 0xffffffff
    index_at = index_at % 0x401+0x4a
    index_key = bytes((count+(name_key[(i+1) % len(name_key)] ^
                        (name_key[i % len(name_key)]+i))) & 255 for i in range(count*4))
    first = archive.entries[0].container_offset
    if index_at+count*4 > first-2:
        raise ValueError('WAG index bounds')
    out = bytearray(data[:first])
    offsets = []

    def encrypted(raw):
        return wag_xor(raw, len(out), archive.key)

    for i, chunks in enumerate(logical):
        offsets.append(len(out))
        out.extend(checked(encrypted(b'DSET'+struct.pack('<I', len(chunks)))))
        for chunk in chunks:
            tag = chunk[0]
            if tag == 'PICT':
                flags, old_payload = chunk[1:]
                payload = replacements.get(i, old_payload)
                size = 6+len(payload)
                out.extend(checked(encrypted(b'PICT'+struct.pack('<I', size))))
                out.extend(checked(encrypted(flags)))
                out.extend(encrypted(payload))
            else:
                value = chunk[1]
                out.extend(checked(encrypted(b'FTAG'+struct.pack('<I', len(value)+2))))
                out.extend(checked(encrypted(value)))
    if len(out) > 0xffffffff:
        raise ValueError('WAG size overflow')
    new_index = struct.pack(f'<{count}I', *offsets)
    out[index_at:index_at+count*4] = wag_xor(new_index, index_at, index_key)
    out[first-2:first] = crc(out[:first-2])
    saved, reread = wag_layout(name, bytes(out))
    for i, (old, new) in enumerate(zip(logical, reread)):
        expected = [(c[0], c[1], replacements.get(i, c[2])) if c[0] == 'PICT' else c for c in old]
        if new != expected or saved.entries[i].name_raw != archive.entries[i].name_raw:
            raise ValueError(f'WAG saved logical bytes mismatch: {i}')
    return bytes(out)
