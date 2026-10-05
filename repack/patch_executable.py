"""Redirect display conversion/font imports to a sidecar DLL.

The original import descriptors remain intact. A new section contains a new
import descriptor/IAT. Display call/load references are redirected. Optional
local execution adds a cdecl adapter in verified zero padding of .text and
redirects the single disc-search call; the original search remains available.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

import pefile

ORIGINAL_SHA256 = 'e51c64bbd3b0584b15d8bb11cad4ea1c107d43b24fda7a2171d49bde9a86dfa1'


def align(n, unit):
    return (n+unit-1)//unit*unit


def patch(data: bytes, require_game_hash=True, local_execution=False):
    if require_game_hash and hashlib.sha256(data).hexdigest() != ORIGINAL_SHA256:
        raise ValueError('unsupported executable SHA-256')
    pe = pefile.PE(data=data)
    if pe.FILE_HEADER.Machine != 0x14c or pe.OPTIONAL_HEADER.DATA_DIRECTORY[5].Size:
        raise ValueError('only the verified fixed-base x86 image is supported')
    base = pe.OPTIONAL_HEADER.ImageBase
    section_header = pe.sections[-1].get_file_offset()+40
    if section_header+40 > pe.OPTIONAL_HEADER.SizeOfHeaders or any(data[section_header:section_header+40]):
        raise ValueError('no empty section header slot')
    va = align(max(s.VirtualAddress+max(s.Misc_VirtualSize,s.SizeOfRawData) for s in pe.sections),pe.OPTIONAL_HEADER.SectionAlignment)
    raw_at = align(len(data),pe.OPTIONAL_HEADER.FileAlignment)
    old_descriptors = [data[d.struct.get_file_offset():d.struct.get_file_offset()+20] for d in pe.DIRECTORY_ENTRY_IMPORT]
    blob = bytearray(b''.join(old_descriptors)+bytes(40))
    wanted_imports = [b'MultiByteToWideChar', b'CreateFontW', b'WideCharToMultiByte', b'OutputDebugStringW', b'GetCharABCWidthsW', b'Direct3DCreate9', b'ScreenToClient', b'ClientToScreen', b'IsDBCSLeadByte']
    exports = [b'Nega'+name for name in wanted_imports]
    if local_execution:
        if not require_game_hash:
            raise ValueError('local execution requires verified game executable')
        exports.append(b'NegaFindLocalGameDisc')
    if require_game_hash:
        exports.append(b'NegaLoadEsoTexture')
    ilt = len(blob); blob.extend(bytes(4*(len(exports)+1)))
    iat = len(blob); blob.extend(bytes(4*(len(exports)+1)))
    dll = len(blob); blob.extend(b'Nega0Korean.dll\0')
    for n, name in enumerate(exports):
        if len(blob)%2: blob.append(0)
        hint = len(blob); blob.extend(b'\0\0'+name+b'\0')
        struct.pack_into('<I',blob,ilt+4*n,va+hint)
        struct.pack_into('<I',blob,iat+4*n,va+hint)
    struct.pack_into('<5I',blob,len(old_descriptors)*20,va+ilt,0,0,va+dll,va+iat)
    out = bytearray(data+bytes(raw_at-len(data)))
    patches=[]
    for n, wanted in enumerate(wanted_imports):
        matches=[i for d in pe.DIRECTORY_ENTRY_IMPORT for i in d.imports if i.name==wanted]
        if len(matches)!=1: raise ValueError('import missing or ambiguous')
        old = struct.pack('<I',matches[0].address)
        new = struct.pack('<I',base+va+iat+4*n)
        found=[]
        skipped=[]
        # Only the confirmed main-game mouse poll/warp calls use logical
        # coordinates. Native dialog placement keeps the real Win32 APIs.
        game_mouse_calls = {b'ScreenToClient': {0x4398d0, 0x43c711},
                            b'ClientToScreen': {0x43bf78}}
        allowed = game_mouse_calls.get(wanted) if require_game_hash else None
        for sec in pe.sections:
            if not sec.Characteristics & 0x20000000: continue
            start=sec.PointerToRawData; end=start+sec.SizeOfRawData; p=start
            while True:
                p=data.find(old,p,end)
                if p<0: break
                opcode=data[p-2:p]
                if opcode not in (b'\xff\x15',b'\xff\x25') and not (opcode[0]==0x8b and opcode[1]&0xc7==5):
                    raise ValueError('unexpected IAT reference instruction at '+hex(p))
                call_va=base+pe.get_rva_from_offset(p-2)
                if allowed is not None and call_va not in allowed:
                    skipped.append(p)
                else:
                    out[p:p+4]=new; found.append(p)
                p+=4
        if not found: raise ValueError('no import references')
        if allowed is not None and {base+pe.get_rva_from_offset(p-2) for p in found}!=allowed:
            raise ValueError('verified main mouse calls missing')
        record={'import':wanted.decode(),'old_iat':matches[0].address,'new_iat':base+va+iat+4*n,'file_offsets':found}
        if skipped: record['native_ui_file_offsets_preserved']=skipped
        patches.append(record)
    local_report = None
    text_section = next(s for s in pe.sections if s.Name.rstrip(b'\0')==b'.text')
    within = align(text_section.Misc_VirtualSize,4)
    if local_execution:
        # cdecl(root, label) -> cdecl(root, label, game's Voice directory buffer).
        thunk = b'\x68'+struct.pack('<I',0x722d58)+b'\xff\x74\x24\x0c'*2
        thunk += b'\xff\x15'+struct.pack('<I',base+va+iat+4*exports.index(b'NegaFindLocalGameDisc'))
        thunk += b'\x83\xc4\x0c\xc3'
        # Use verified zero padding in the existing read/execute .text section.
        # The new import data section retains read/write permissions only.
        text_sections = [s for s in pe.sections if s.Name.rstrip(b'\0')==b'.text']
        if len(text_sections)!=1:
            raise ValueError('text section missing or ambiguous')
        text_section = text_sections[0]
        within = align(text_section.Misc_VirtualSize,4)
        thunk_at = text_section.PointerToRawData+within
        if within+len(thunk)>text_section.SizeOfRawData or any(data[thunk_at:thunk_at+len(thunk)]):
            raise ValueError('no verified zero text padding for local execution thunk')
        thunk_rva = text_section.VirtualAddress+within
        out[thunk_at:thunk_at+len(thunk)] = thunk
        struct.pack_into('<I',out,text_section.get_file_offset()+8,within+len(thunk))
        call_va = 0x43a7ce
        call_at = pe.get_offset_from_rva(call_va-base)
        old_call = b'\xe8'+struct.pack('<i',0x4f5720-(call_va+5))
        if data[call_at:call_at+5] != old_call:
            raise ValueError('disc search call signature mismatch')
        new_call = b'\xe8'+struct.pack('<i',base+thunk_rva-(call_va+5))
        out[call_at:call_at+5] = new_call
        local_report = {'original_search_preserved': True, 'call_va': call_va,
                        'old_call_hex': old_call.hex(), 'new_call_hex': new_call.hex(),
                        'thunk_va': base+thunk_rva, 'thunk_hex': thunk.hex(),
                        'thunk_file_offset': thunk_at, 'thunk_in_verified_zero_text_padding': True,
                        'voice_directory_va': 0x722d58, 'full_local_assets_required': 119,
                        'incomplete_installation_uses_original_disc_search': True}
        within=align(within+len(thunk),4)
    archive_locale_report=[]
    if require_game_hash:
        # MIKO's NDIX is stored in Japanese collation order. Its binary search
        # must use that same locale, irrespective of the user's system locale.
        # Other CompareStringW sites build runtime containers, so keep them.
        push_va=0x4170ed
        at=pe.get_offset_from_rva(push_va-base)
        old=b'\x68'+struct.pack('<I',0x800)
        following=b'\xff\x15'+struct.pack('<I',0x67313c)
        if data[at:at+5]!=old or data[at+5:at+11]!=following:
            raise ValueError('MIKO filename binary search locale signature mismatch')
        new=b'\x68'+struct.pack('<I',0x411)
        out[at:at+5]=new
        archive_locale_report.append({'push_va':push_va,'call_va':push_va+5,
            'file_offset':at,'old_hex':old.hex(),'new_hex':new.hex(),
            'original_lcid':0x800,'lcid':0x411,'flags':1,
            'scope':'MIKO NDIX filename binary search only'})
    texture_report=[]
    if require_game_hash:
        # A tail jump keeps the original cdecl stack and return value intact.
        thunk=b'\xff\x25'+struct.pack('<I',base+va+iat+4*exports.index(b'NegaLoadEsoTexture'))
        thunk_at=text_section.PointerToRawData+within
        if within+len(thunk)>text_section.SizeOfRawData or any(data[thunk_at:thunk_at+len(thunk)]):
            raise ValueError('no verified zero padding for texture diagnostic thunk')
        out[thunk_at:thunk_at+len(thunk)]=thunk
        thunk_va=base+text_section.VirtualAddress+within
        struct.pack_into('<I',out,text_section.get_file_offset()+8,within+len(thunk))
        for call_va in (0x5df9bd,0x5e92c9):
            call_at=pe.get_offset_from_rva(call_va-base)
            old_call=b'\xe8'+struct.pack('<i',0x5ebbc0-(call_va+5))
            if data[call_at:call_at+5]!=old_call:
                raise ValueError('texture diagnostic call signature mismatch')
            new_call=b'\xe8'+struct.pack('<i',thunk_va-(call_va+5))
            out[call_at:call_at+5]=new_call
            texture_report.append({'call_va':call_va,'thunk_va':thunk_va,'thunk_file_offset':thunk_at,
                                   'thunk_hex':thunk.hex(),'original_target':0x5ebbc0})
    raw_size=align(len(blob),pe.OPTIONAL_HEADER.FileAlignment)
    out.extend(blob); out.extend(bytes(raw_size-len(blob)))
    struct.pack_into('<8s6I2HI',out,section_header,b'.ngko\0\0\0',len(blob),va,raw_size,raw_at,0,0,0,0,0xc0000040)
    struct.pack_into('<H',out,pe.FILE_HEADER.get_file_offset()+2,pe.FILE_HEADER.NumberOfSections+1)
    opt=pe.OPTIONAL_HEADER.get_file_offset()
    struct.pack_into('<I',out,opt+56,align(va+len(blob),pe.OPTIONAL_HEADER.SectionAlignment))
    struct.pack_into('<I',out,opt+8,pe.OPTIONAL_HEADER.SizeOfInitializedData+raw_size)
    struct.pack_into('<II',out,pe.OPTIONAL_HEADER.DATA_DIRECTORY[1].get_file_offset(),va,(len(old_descriptors)+2)*20)
    struct.pack_into('<II',out,pe.OPTIONAL_HEADER.DATA_DIRECTORY[11].get_file_offset(),0,0)
    struct.pack_into('<I',out,opt+64,0)
    parsed=pefile.PE(data=bytes(out))
    extra=parsed.DIRECTORY_ENTRY_IMPORT[-1]
    if extra.dll!=b'Nega0Korean.dll' or [i.name for i in extra.imports]!=exports:
        raise ValueError('saved import verification failed')
    struct.pack_into('<I',out,opt+64,parsed.generate_checksum())
    return bytes(out), {'source_sha256':hashlib.sha256(data).hexdigest(),'output_sha256':hashlib.sha256(out).hexdigest(),'redirects':patches,'new_section_rva':va,'local_execution':local_report,'texture_diagnostics':texture_report,'archive_search_locale':archive_locale_report}


if __name__=='__main__':
    src,dst=map(Path,sys.argv[1:3])
    if src.resolve() == dst.resolve() or dst.exists():
        raise ValueError('output must be a new separate file')
    out,report=patch(src.read_bytes())
    dst.parent.mkdir(parents=True,exist_ok=True); dst.write_bytes(out)
    dst.with_suffix('.patch.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'redirects':{p['import']:len(p['file_offsets']) for p in report['redirects']},'output_bytes':len(out)}))
