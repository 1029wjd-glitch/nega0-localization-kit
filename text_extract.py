"""Typed Nega0 string extraction; executable/binary guesses remain review candidates.

NORI: XOR 0x53 string operands, with untouched code and per-block checksums.
BINF: length-prefixed CP932 strings stored with an eight-bit rotate right by one.
"""
from __future__ import annotations

import re
import struct
from collections import Counter
from formats import sha256

JP = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uff66-\uff9d]")
FULL_JP = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
ASSET = re.compile(r"(?i)\.(?:bin|png|wag|vgs|kta|ogg|wav|eso|bmp|mpg|avi)(?:$|[|;])")
TOKEN = re.compile(r"<[^<>\r\n]+>|\\(?:[A-Za-z]+(?:\[[^\]]*\])?)|%[-+0-9.]*[sdif]|\$\{[^}]+\}")


def readable(value: str) -> bool:
    return bool(value) and all(ord(c) >= 32 or c in "\r\n\t" for c in value)


def protection(source: str) -> dict:
    tokens = TOKEN.findall(source)
    # Main dialogue quotes are display grammar; keep their positions explicit.
    if source.startswith("「"):
        tokens.insert(0, "「")
    if source.endswith("」"):
        tokens.append("」")
    return {"protected_tokens": tokens,
            "structural_counts": {"newline": source.count("\n"),
                                  "literal:\r": source.count("\r"),
                                  "literal:\t": source.count("\t")}}


def nori(data: bytes) -> tuple[list[dict], dict]:
    if len(data) < 48 or data[:8] != b"NORI\0\0\x01\0":
        raise ValueError("unsupported NORI header")
    label_count, label_size = struct.unpack_from("<II", data, 8)
    global_count, global_size, local_count, local_size = struct.unpack_from("<4I", data, 16)
    code_size, pool_size = struct.unpack_from("<II", data, 32)
    code_start = 48 + label_size + global_size + local_size
    pool_start = code_start + code_size + 2
    if pool_start + pool_size + 2 != len(data):
        raise ValueError("NORI block size reconciliation failed")
    pool = bytes(v ^ 0x53 for v in data[pool_start:pool_start+pool_size])
    labels = []
    p = 42
    for _ in range(label_count):
        address = struct.unpack_from("<I", data, p)[0]
        length = struct.unpack("<I", bytes(v ^ 0x53 for v in data[p+4:p+8]))[0]
        if p + 8 + length > 42 + label_size:
            raise ValueError("NORI label outside table")
        raw = bytes(v ^ 0x53 for v in data[p+8:p+8+length])
        labels.append({"address": address, "label": raw.decode("cp932")})
        p += 8 + length
    if p != 42 + label_size:
        raise ValueError("NORI label count reconciliation failed")

    refs = {}
    # Operand slots are two-byte aligned. Read only confirmed type 5 fields.
    for p in range(code_start, code_start+code_size-7, 2):
        typ, length, offset = struct.unpack_from("<HHI", data, p)
        if typ != 5 or not 0 < length < 0x8000 or offset + length > pool_size:
            continue
        raw = pool[offset:offset+length]
        try:
            source = raw.decode("cp932", errors="strict")
        except UnicodeDecodeError:
            continue
        if not readable(source):
            continue
        if source.encode("cp932") != raw:
            # CP932 has aliases; retain bytes and flag rather than normalize.
            cp932_roundtrip = False
        else:
            cp932_roundtrip = True
        refs[p] = {"source": source, "source_bytes_hex": raw.hex(),
                   "source_bytes_sha256": sha256(raw), "byte_offset": pool_start+offset,
                   "byte_length": length, "operand_offset": p,
                   "length_field_offset": p+2, "pointer_field_offset": p+4,
                   "pool_relative_offset": offset, "encoding": "cp932",
                   "storage_transform": "xor-53", "cp932_roundtrip": cp932_roundtrip,
                   "category": "unclassified_string", "classification": "needs_review"}

    # Message opcodes 1 and 60: metadata pointer + contiguous display strings.
    # This deliberately does not guess expression opcodes or their argument counts.
    message_count = 0
    covered = set()
    for p in range(code_start, code_start+code_size-15, 2):
        opcode, argc, result = struct.unpack_from("<HHi", data, p)
        if opcode not in (1, 60) or not 2 <= argc <= 100 or result != argc-1:
            continue
        if p + 8 + 8*argc > code_start + code_size:
            continue
        first_type, flags, meta = struct.unpack_from("<HHI", data, p+8)
        if first_type != 3 or flags not in (0, 1) or meta+8 > pool_size:
            continue
        operands = [p+16+i*8 for i in range(argc-1)]
        if any(q not in refs for q in operands):
            continue
        expected = meta+8
        for q in operands:
            if refs[q]["pool_relative_offset"] != expected:
                break
            expected += refs[q]["byte_length"]
        else:
            # Metadata numbers themselves are stored without XOR.
            sequence, voice = struct.unpack_from("<II", data, pool_start+meta)
            context = [refs[q]["source"] for q in operands]
            for index, q in enumerate(operands):
                if q in covered:
                    raise ValueError("overlapping NORI message operands")
                covered.add(q)
                speaker = opcode == 60 and flags == 1 and index == 0
                refs[q].update(category="speaker_name" if speaker else "scenario_text",
                               classification="display_operand", command_offset=p,
                               opcode=opcode, argument_index=index+1,
                               message_sequence=sequence, voice_id=voice,
                               speaker=context[0] if opcode == 60 and flags == 1 else "",
                               context={"message_lines": context,
                                        "line_index": index, "message_metadata_offset": pool_start+meta})
            message_count += 1
    for p, ref in refs.items():
        if p in covered:
            continue
        # Simple string-bearing instructions confirmed in the representative samples.
        op, argc, _ = struct.unpack_from("<HHi", data, p-8)
        if op in (55, 185) and argc == 1:
            ref.update(category="chapter_title" if op == 55 else "ui_notification", classification="display_operand",
                       command_offset=p-8, opcode=op, argument_index=0)
        elif (ASSET.search(ref["source"]) or not JP.search(ref["source"])
              or ref["source"] in {x["label"] for x in labels}
              or ref["source"].lower().startswith(("rn:", "root."))
              or op in (12, 23, 199) and argc <= 100):
            ref.update(category="internal_identifier", classification="exclude")
        # Battle subtitle opcode 59; later arguments need their own group header.
        elif op == 59 and 1 <= argc <= 100:
            positions = [p+i*8 for i in range(argc)]
            if all(q in refs for q in positions):
                for i, q in enumerate(positions):
                    refs[q].update(category="battle_text", classification="display_operand",
                                   command_offset=p-8, opcode=59, argument_index=i)
    # Known call/label instructions contain identifiers, including Japanese names.
    for p in range(code_start, code_start+code_size-15, 2):
        op, argc, _ = struct.unpack_from("<HHi", data, p)
        if op not in (12, 23, 199) or not 1 <= argc <= 100 or p+8+argc*8 > code_start+code_size:
            continue
        for i in range(argc):
            q = p+8+i*8
            if q in refs and refs[q]["classification"] == "needs_review":
                refs[q].update(category="internal_identifier", classification="exclude")
    # Opcode 100 presents an array of choice labels without message metadata.
    for p in range(code_start, code_start+code_size-15, 2):
        opcode, argc, _ = struct.unpack_from("<HHi", data, p)
        if opcode != 100 or not 1 <= argc <= 100 or p+8+argc*8 > code_start+code_size:
            continue
        positions = [p+8+i*8 for i in range(argc)]
        if all(q in refs for q in positions):
            for i, q in enumerate(positions):
                refs[q].update(category="choice", classification="display_operand",
                               command_offset=p, opcode=100, argument_index=i,
                               context={"choices": [refs[q]["source"] for q in positions]})
    return sorted(refs.values(), key=lambda r: r["operand_offset"]), {
        "format": "NORI", "label_count": label_count, "code_offset": code_start,
        "global_count": global_count, "global_size": global_size,
        "local_count": local_count, "local_size": local_size,
        "code_size": code_size, "pool_offset": pool_start, "pool_size": pool_size,
        "message_count": message_count, "labels": labels,
        "block_checksums_hex": {"header": data[40:42].hex(),
                                "labels": data[42+label_size:44+label_size].hex(),
                                "code": data[pool_start-2:pool_start].hex(),
                                "strings": data[-2:].hex()},
        "counts": dict(Counter(r["classification"] for r in refs.values())),
        "unknown_opcode_strings_are_review_candidates": True}


def binf(data: bytes, name: str) -> tuple[list[dict], dict]:
    if len(data) < 32 or data[:8] != b"BINF\x01\0\0\0":
        raise ValueError("unsupported BINF header")
    row_count = struct.unpack_from("<I", data, 8)[0]
    refs = []
    occupied_end = 32
    all_strings = 0
    for p in range(32, len(data)-4):
        if p < occupied_end:
            continue
        length = struct.unpack_from("<I", data, p)[0]
        if not 1 <= length <= 65535 or p+4+length >= len(data) or data[p+4+length] != 0:
            continue
        stored = data[p+4:p+4+length]
        raw = bytes(((v << 1) | (v >> 7)) & 255 for v in stored)
        try:
            source = raw.decode("cp932", errors="strict")
        except UnicodeDecodeError:
            continue
        if not readable(source):
            continue
        occupied_end = p+4+length+1
        all_strings += 1
        if not FULL_JP.search(source) and not (len(source) >= 2 and JP.search(source)):
            continue
        category = "table_text"
        if name.startswith("SkillExp") or name == "ItemExp.bin":
            category = "skill_description" if name.startswith("Skill") else "item_description"
        elif name.startswith("Skill") and not name.startswith("SkillDeck"):
            category = "skill_name"
        elif name == "ItemData.bin":
            category = "item_name"
        elif name == "CharProfile.bin":
            category = "character_profile"
        elif name == "CharDefines.bin":
            category = "character_display_name"
        classification = "exclude" if ASSET.search(source) else "length_prefixed_table_string"
        refs.append({"source": source, "source_bytes_hex": raw.hex(),
                     "source_bytes_sha256": sha256(raw), "byte_offset": p+4,
                     "byte_length": length, "length_field_offset": p,
                     "encoding": "cp932", "storage_transform": "ror-1",
                     "category": category, "classification": classification,
                     "cp932_roundtrip": source.encode("cp932") == raw})
    return refs, {"format": "BINF", "declared_rows": row_count,
                  "all_length_prefixed_strings": all_strings,
                  "japanese_strings": len(refs),
                  "row_schema_fully_parsed": False,
                  "rule": "u32 byte length + ROR1 CP932 bytes + NUL; non-overlapping spans"}
