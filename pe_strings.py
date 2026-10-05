"""Read-only PE string candidates. Candidates are not automatically CP2 input."""
import re
import struct
from text_extract import FULL_JP, readable


def candidates(data: bytes):
    if data[:2] != b"MZ":
        raise ValueError("not a PE file")
    pe = struct.unpack_from("<I", data, 0x3c)[0]
    if data[pe:pe+4] != b"PE\0\0":
        raise ValueError("missing PE signature")
    count = struct.unpack_from("<H", data, pe+6)[0]
    opt = struct.unpack_from("<H", data, pe+20)[0]
    results = []
    for i in range(count):
        p = pe+24+opt+40*i
        name = data[p:p+8].rstrip(b"\0").decode("ascii")
        size, offset = struct.unpack_from("<II", data, p+16)
        if name not in (".rdata", ".data"):
            continue
        block = data[offset:offset+size]
        for match in re.finditer(rb"[^\x00\x01-\x08\x0b-\x1f]{4,}\x00", block):
            raw = match.group()[:-1]
            try:
                source = raw.decode("cp932", errors="strict")
            except UnicodeDecodeError:
                continue
            if 2 <= len(FULL_JP.findall(source)) and len(source) <= 1000 and readable(source):
                results.append({"source": source, "byte_offset": offset+match.start(),
                                "byte_length": len(raw), "source_bytes_hex": raw.hex(),
                                "encoding": "cp932", "section": name,
                                "classification": "needs_review", "category": "executable_string_candidate",
                                "translatable": False})
        # UTF-16LE runs, aligned on the PE section's natural two-byte boundary.
        for parity in (0, 1):
            pos = parity
            while pos+2 <= len(block):
                end = pos
                while end+2 <= len(block) and block[end:end+2] != b"\0\0":
                    end += 2
                raw = block[pos:end]
                if 4 <= len(raw) <= 2000:
                    try:
                        source = raw.decode("utf-16le", errors="strict")
                    except UnicodeDecodeError:
                        source = ""
                    if readable(source) and len(FULL_JP.findall(source)) >= 2:
                        results.append({"source": source, "byte_offset": offset+pos,
                                        "byte_length": len(raw), "source_bytes_hex": raw.hex(),
                                        "encoding": "utf-16le", "section": name,
                                        "classification": "needs_review", "category": "executable_string_candidate",
                                        "translatable": False})
                pos = end+2
    unique = {(r["byte_offset"], r["encoding"]): r for r in results}
    return sorted(unique.values(), key=lambda r: (r["byte_offset"], r["encoding"]))


def resources(data: bytes):
    """Traverse the native resource directory without executing the PE."""
    pe = struct.unpack_from("<I", data, 0x3c)[0]
    count = struct.unpack_from("<H", data, pe+6)[0]
    opt = struct.unpack_from("<H", data, pe+20)[0]
    section_base = pe+24+opt
    sections = []
    for i in range(count):
        p = section_base+40*i
        virtual_size, rva, size, offset = struct.unpack_from("<4I", data, p+8)
        sections.append((rva, max(size, virtual_size), offset, size))
    def physical(rva, size=1):
        for start, span, offset, raw_size in sections:
            if start <= rva and rva+size <= start+raw_size:
                return offset+rva-start
        raise ValueError("resource RVA outside PE raw sections")
    magic = struct.unpack_from("<H", data, pe+24)[0]
    directory = pe+24+(96 if magic == 0x10b else 112)
    resource_rva, resource_size = struct.unpack_from("<II", data, directory+16)
    if not resource_rva or not resource_size:
        return []
    base = physical(resource_rva)
    result = []
    def walk(relative, path, ancestors):
        if relative in ancestors or len(path) > 4 or relative+16 > resource_size:
            raise ValueError("invalid resource directory nesting")
        p = base+relative
        named, ids = struct.unpack_from("<HH", data, p+12)
        for i in range(named+ids):
            label, target = struct.unpack_from("<II", data, p+16+i*8)
            if label & 0x80000000:
                np = base+(label & 0x7fffffff)
                length = struct.unpack_from("<H", data, np)[0]
                name = data[np+2:np+2+length*2].decode("utf-16le")
            else:
                name = label
            branch = path+[name]
            if target & 0x80000000:
                walk(target & 0x7fffffff, branch, ancestors|{relative})
            else:
                rva, size, codepage, _ = struct.unpack_from("<4I", data, base+target)
                offset = physical(rva, size)
                result.append({"resource_path": branch, "byte_offset": offset,
                               "size": size, "resource_codepage": codepage})
    walk(0, [], set())
    return result


def resource_strings(data: bytes, resource: dict):
    """Exact display fields from RT_STRING and standard/extended dialogs."""
    if resource["resource_path"][0] == 5:
        return dialog_strings(data, resource)
    if resource["resource_path"][0] == 4:
        return menu_strings(data, resource)
    if resource["resource_path"][0] != 6:
        return []
    start = resource["byte_offset"]
    end = start+resource["size"]
    p, rows = start, []
    for slot in range(16):
        if p+2 > end:
            raise ValueError("truncated RT_STRING table")
        length = struct.unpack_from("<H", data, p)[0]
        field = p
        p += 2
        raw = data[p:p+length*2]
        if p+len(raw) > end or len(raw) != length*2:
            raise ValueError("truncated RT_STRING value")
        source = raw.decode("utf-16le")
        if FULL_JP.search(source):
            rows.append({"source": source, "byte_offset": p, "byte_length": length*2,
                         "length_field_offset": field, "encoding": "utf-16le",
                         "resource_path": resource["resource_path"], "string_slot": slot,
                         "category": "native_ui_string", "classification": "resource_string",
                         "source_bytes_hex": raw.hex(), "translatable": False})
        p += length*2
    return rows


def unicode_field(data, offset, end):
    if offset+2 > end:
        raise ValueError("truncated resource field")
    first = struct.unpack_from("<H", data, offset)[0]
    if first == 0xffff:
        return None, offset+4
    p = offset
    while p+2 <= end:
        if data[p:p+2] == b"\0\0":
            return (offset, data[offset:p].decode("utf-16le")), p+2
        p += 2
    raise ValueError("unterminated resource Unicode string")


def native_row(data, resource, field, role):
    if field is None or not FULL_JP.search(field[1]):
        return None
    offset, source = field
    raw = data[offset:offset+len(source.encode('utf-16le'))]
    return {"source": source, "byte_offset": offset, "byte_length": len(raw),
            "encoding": "utf-16le", "resource_path": resource["resource_path"],
            "category": role, "classification": "resource_string",
            "source_bytes_hex": raw.hex(), "translatable": False}


def dialog_strings(data, resource):
    start = resource["byte_offset"]
    end = start+resource["size"]
    extended = data[start:start+4] == b"\x01\0\xff\xff"
    if extended:
        style = struct.unpack_from("<I", data, start+12)[0]
        controls = struct.unpack_from("<H", data, start+16)[0]
        p = start+26
    else:
        style = struct.unpack_from("<I", data, start)[0]
        controls = struct.unpack_from("<H", data, start+8)[0]
        p = start+18
    _, p = unicode_field(data, p, end)  # menu
    _, p = unicode_field(data, p, end)  # class
    title, p = unicode_field(data, p, end)
    rows = []
    row = native_row(data, resource, title, "native_dialog_title")
    if row:
        rows.append(row)
    if style & 0x40:  # DS_SETFONT: point size, optional weight/italic/charset, font
        p += 6 if extended else 2
        _, p = unicode_field(data, p, end)
    for i in range(controls):
        p = start+((p-start+3)//4)*4
        p += 24 if extended else 18
        _, p = unicode_field(data, p, end)  # control class or ordinal
        title, p = unicode_field(data, p, end)
        row = native_row(data, resource, title, "native_dialog_control")
        if row:
            row["control_index"] = i
            rows.append(row)
        if p+2 > end:
            raise ValueError("truncated dialog creation data")
        extra = struct.unpack_from("<H", data, p)[0]
        p += max(2, extra)  # creation-data size includes its size WORD
    if p > end:
        raise ValueError("dialog field past resource boundary")
    return rows


def menu_strings(data, resource):
    start, size = resource["byte_offset"], resource["size"]
    end = start+size
    version, extra = struct.unpack_from("<HH", data, start)
    # This title's menu is the classic version. Other layouts remain raw candidates.
    if version != 0:
        return []
    p = start+4+extra
    rows = []
    def level(p, depth=0):
        if depth > 20:
            raise ValueError("excessive menu depth")
        while p < end:
            flags = struct.unpack_from("<H", data, p)[0]
            p += 2
            popup = bool(flags & 0x10)
            if not popup:
                p += 2  # command ID
            text, p = unicode_field(data, p, end)
            row = native_row(data, resource, text, "native_menu_item")
            if row:
                rows.append(row)
            if popup:
                p = level(p, depth+1)
            if flags & 0x80:
                return p
        return p
    level(p)
    return rows
