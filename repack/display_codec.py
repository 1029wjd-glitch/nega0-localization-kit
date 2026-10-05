"""CP932-compatible display bytes; byte-oriented engine splitting remains valid.

Only unused CP932 private-use character slots are mapped. Original Japanese
identifiers, resource paths, punctuation and all ordinary CP932 bytes stay intact.
"""
import json
from pathlib import Path

TO_SLOT = {}
FROM_SLOT = {}

def load_mapping(path=None):
    """Explicitly load the exact mapping used to build the runtime DLL."""
    data = json.loads(Path(path or Path(__file__).parent/'display_mapping.json').read_text(encoding='utf-8'))
    if data.get('format') != 'cp932-private-display-v1':
        raise ValueError('unsupported display mapping')
    rows = data['characters']
    if len(rows) > 1880:
        raise ValueError('display slot capacity')
    table = {}
    for i, r in enumerate(rows):
        c, slot = chr(r['unicode']), chr(r['slot'])
        if r['slot'] != 0xe000+i or c in table or ord(c) > 0xffff or c == '\0':
            raise ValueError('invalid display mapping entry')
        if slot.encode('cp932').hex() != r['bytes_hex']:
            raise ValueError('display mapping byte mismatch')
        table[c] = slot
    TO_SLOT.clear(); TO_SLOT.update(table)
    FROM_SLOT.clear(); FROM_SLOT.update({v:k for k,v in table.items()})
    return data


def encode_display(text):
    if '\0' in text:
        raise ValueError('embedded NUL in display text')
    if any(c in FROM_SLOT for c in text):
        raise ValueError('literal reserved display slot')
    return ''.join(TO_SLOT.get(c, c) for c in text).encode('cp932')


def decode_display(raw):
    # Retain the decoder for the previously delivered UTF-8 probe/candidate.
    if raw.startswith(b'\xef\xbb\xbf'):
        return raw[3:].decode('utf-8')
    return ''.join(FROM_SLOT.get(c, c) for c in raw.decode('cp932'))
