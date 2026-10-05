"""Synthetic fixtures only: no game bytes, dialogue, or artwork."""
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'repack')]
from formats import Archive, wag_key, wag_xor
from reinject import crc, checked, xor53, inject_nori, nori_layout, inject_miko, inject_wag
from binf_codec import schema_for, ror1, parse_binf, inject_binf
import display_codec
from prepare_display_mapping import generate

def nori_fixture():
    first, second = b'one', b'two'
    pool = b'METADATA'+xor53(first+second)
    code = struct.pack('<HHi',1,3,2)+struct.pack('<HHI',3,0,0)
    code += struct.pack('<HHI',5,len(first),8)+struct.pack('<HHI',5,len(second),8+len(first))
    header = b'NORI\0\0\x01\0'+struct.pack('<8I',0,0,0,0,0,0,len(code),len(pool))
    data = checked(header)+checked(b'')*3+checked(code)+checked(pool)
    layout = nori_layout(data)
    record = {'id':'synthetic-line', 'source':'one', 'target':{
        'operand_offset':layout['code_at']+16, 'byte_length':len(first),
        'pool_relative_offset':8, 'source_bytes_hex':first.hex()},
        'context_meta':{'message_metadata_offset':layout['pool_at'], 'line_index':0}}
    return data, record

def binf_fixture():
    body, checksum = bytearray(), bytearray()
    for i,spec in enumerate(schema_for('ItemData.bin')):
        if isinstance(spec,int):
            value = bytes(spec); body.extend(value); checksum.extend(value)
        else:
            raw = b'KEY' if i==1 else b'Display'
            size = struct.pack('<I',len(raw))
            body.extend(size+ror1(raw+b'\0')); checksum.extend(size+raw+b'\0')
    data = b'BINF\x01\0\0\0'+struct.pack('<I',1)+bytes(20)+body+crc(checksum)
    fields = parse_binf('ItemData.bin', data)[0]['fields']
    def record(index):
        f = fields[index]
        return {'id':'synthetic-field', 'source':f['raw'].decode('ascii'), 'target':{
            'length_field_offset':f['offset'], 'byte_offset':f['byte_offset'],
            'source_bytes_hex':f['raw'].hex()}}
    return bytes(data), record

def miko_fixture():
    out = bytearray(192)
    out[:4] = b'MIKO'
    struct.pack_into('<H',out,10,0x1001)
    struct.pack_into('<I',out,16,2)
    out[22:26]=b'DFNM'; struct.pack_into('<Q',out,26,80)
    out[36:40]=b'NDIX'; out[76:80]=b'CTIF'; out[80:84]=b'CADR'
    for i,(name, payload) in enumerate([(b'a.bin',b'AAA'),(b'b.bin',b'BBBB')]):
        at = 128+i*16
        struct.pack_into('<I',out,42+i*8,at)
        struct.pack_into('<H',out,at,0x1001); struct.pack_into('<H',out,at+6,len(name))
        out[at+10:at+10+len(name)] = bytes(b^0x56 for b in name)
        addr = 84+i*12
        struct.pack_into('<Q',out,addr+2,len(out)); out[addr+10:addr+12]=crc(out[addr:addr+10])
        header = bytearray(28); header[:4]=b'DATA'; struct.pack_into('<I',header,24,len(payload))
        out.extend(checked(header)+checked(payload))
    return bytes(out)

def wag_fixture():
    name = 'fixture.wag'; title = b'synthetic'; count = 2
    nk = wag_key(name.encode('cp932')); key = wag_key(title)
    pos = 0x200+sum(nk)
    for _ in range(2):
        for v in nk:
            pos ^= v; pos=((pos>>1)|((pos&1)<<31))&0xffffffff
    pos=pos%0x401+0x4a
    ik=bytes((count+(nk[(i+1)%len(nk)]^(nk[i%len(nk)]+i)))&255 for i in range(count*4))
    out=bytearray(1536); out[:4]=b'WAG@'; struct.pack_into('<H',out,4,0x300)
    out[6:6+len(title)]=title; struct.pack_into('<I',out,70,count)
    offsets=[]
    def enc(raw): return wag_xor(raw,len(out),key)
    for label, payload in [(b'a.png',b'synthetic-image-A'),(b'b.png',b'synthetic-image-B')]:
        offsets.append(len(out))
        out.extend(checked(enc(b'DSET'+struct.pack('<I',2))))
        out.extend(checked(enc(b'PICT'+struct.pack('<I',6+len(payload)))))
        out.extend(checked(enc(bytes(4)))); out.extend(enc(payload))
        out.extend(checked(enc(b'FTAG'+struct.pack('<I',len(label)+2))))
        out.extend(checked(enc(label)))
    out[pos:pos+count*4]=wag_xor(struct.pack('<2I',*offsets),pos,ik)
    out[1534:1536]=crc(out[:1534])
    return name,bytes(out)

class FormatTests(unittest.TestCase):
    def tearDown(self):
        display_codec.TO_SLOT.clear(); display_codec.FROM_SLOT.clear()

    def test_nori_message_group_and_neighbor(self):
        original, r = nori_fixture()
        out, applied=inject_nori(original,[r],{r['id']:'expanded first line'})
        layout=nori_layout(out); old=nori_layout(original)
        self.assertEqual(out[layout['pool_at']:layout['pool_at']+old['pool_size']],original[old['pool_at']:-2])
        p=r['target']['operand_offset']
        _,length,ptr=struct.unpack_from('<HHI',out,p)
        _,nlength,nptr=struct.unpack_from('<HHI',out,p+8)
        self.assertEqual(nptr,ptr+length)
        self.assertEqual(xor53(out[layout['pool_at']+nptr:layout['pool_at']+nptr+nlength]),b'two')
        self.assertEqual(set(applied),{r['id']})
        self.assertEqual(struct.unpack_from('<I',out,layout['code_at']+12)[0],old['pool_size'])

    def test_nori_crc_rejects_corruption(self):
        data,_=nori_fixture()
        with self.assertRaises(ValueError): nori_layout(data[:-1]+bytes([data[-1]^1]))

    def test_binf_capacity_and_preservation(self):
        data,record=binf_fixture(); r=record(2)
        out,_=inject_binf('ItemData.bin',data,[r],{r['id']:'ABCDEFGHIJKL'})
        rows=parse_binf('ItemData.bin',out)
        self.assertEqual(rows[0]['fields'][1]['raw'],b'KEY')
        self.assertEqual(rows[0]['fields'][2]['raw'],b'ABCDEFGHIJKL')
        with self.assertRaisesRegex(ValueError,'capacity'):
            inject_binf('ItemData.bin',data,[r],{r['id']:'ABCDEFGHIJKLM'})

    def test_binf_internal_key_rejected(self):
        data,record=binf_fixture(); r=record(1)
        with self.assertRaisesRegex(ValueError,'internal key'):
            inject_binf('ItemData.bin',data,[r],{r['id']:'NEW'})

    def test_miko_preserves_other_payload_and_names(self):
        data=miko_fixture(); old=Archive(Path('fixture.arc'),data)
        out=inject_miko('fixture.arc',data,{0:b'longer synthetic value'})
        new=Archive(Path('fixture.arc'),out)
        self.assertEqual(new.read(new.entries[0]),b'longer synthetic value')
        self.assertEqual(new.read(new.entries[1]),old.read(old.entries[1]))
        self.assertEqual([e.name_raw for e in old.entries],[e.name_raw for e in new.entries])
        damaged=bytearray(data); damaged[-1]^=1
        with self.assertRaisesRegex(ValueError,'CRC'): inject_miko('fixture.arc',bytes(damaged),{0:b'new'})

    def test_wag_reencrypts_following_chunks(self):
        name,data=wag_fixture(); old=Archive(Path(name),data)
        out=inject_wag(name,data,{0:b'a longer replacement image fixture'})
        new=Archive(Path(name),out)
        self.assertNotEqual(old.entries[1].container_offset,new.entries[1].container_offset)
        self.assertEqual(new.read(new.entries[0]),b'a longer replacement image fixture')
        self.assertEqual(new.read(new.entries[1]),old.read(old.entries[1]))
        self.assertEqual([e.name_raw for e in old.entries],[e.name_raw for e in new.entries])

    def mapping_case(self, folder, translation='한글 test', source='original'):
        t=folder/'translated.jsonl'; inv=folder/'inventory.jsonl'
        t.write_text(json.dumps({'id':'synthetic','translation':translation})+'\n',encoding='utf-8')
        inv.write_text(json.dumps({'id':'synthetic','source':source,'target':{'archive_chain':[]}})+'\n',encoding='utf-8')
        return generate(t,inv,folder/'out')

    def test_mapping_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp); data=self.mapping_case(p)
            display_codec.load_mapping(p/'out/display_mapping.json')
            self.assertEqual(len(data['characters']),2)
            self.assertEqual(display_codec.decode_display(display_codec.encode_display('한글 test')),'한글 test')
            self.assertEqual(display_codec.encode_display('日本語'),'日本語'.encode('cp932'))
            with self.assertRaises(ValueError): display_codec.encode_display('bad\0')
            with self.assertRaises(ValueError): display_codec.encode_display('\ue000')

    def test_mapping_rejects_source_collision_and_non_bmp(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            with self.assertRaisesRegex(ValueError,'reserved slot'): self.mapping_case(p,source='\ue000')
            with self.assertRaises(ValueError): self.mapping_case(p,translation='\U0001f600')
            with self.assertRaises(ValueError): self.mapping_case(p,translation='bad\0')

    @unittest.skipUnless(sys.platform=='win32','MSDelta is a Windows API')
    def test_msdelta_roundtrip(self):
        from msdelta import create, invoke
        original=b'synthetic old contents'*20; target=b'synthetic new contents'*30
        self.assertEqual(invoke(original,create(original,target),False),target)
        self.assertEqual(invoke(b'',create(b'',target),False),target)

if __name__=='__main__': unittest.main()
