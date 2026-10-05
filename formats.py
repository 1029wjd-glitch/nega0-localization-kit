"""Read-only Nega0 resource readers, based on GARbro's Xuse handlers.

See THIRD_PARTY_NOTICES.md for the original MIT notices and sources.
Output names are deliberately separate from the original archive name bytes.
"""
from __future__ import annotations

import hashlib
import io
import struct
from dataclasses import dataclass
from pathlib import Path


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_at(stream, offset: int, length: int) -> bytes:
    if offset < 0 or length < 0:
        raise ValueError("negative byte range")
    stream.seek(offset)
    data = stream.read(length)
    if len(data) != length:
        raise ValueError(f"truncated range at {offset:#x}, length {length}")
    return data


def signed(value: int) -> int:
    return value if value < 128 else value - 256


def wag_key(keyword: bytes) -> bytes:
    if not keyword:
        raise ValueError("empty WAG keyword")
    h = 0
    for i, value in enumerate(keyword):
        h = ((signed(value) + i) ^ h) + len(keyword)
    size = (h & 255) + 64
    h += sum(map(signed, keyword))
    key = bytearray(size)
    key[1] = (h >> 8) & 255
    h &= 15
    key[0], key[2], key[3] = h, 0x46, 0x88
    for i in range(4, size - 1):
        h += ((signed(keyword[i % len(keyword)]) ^ h) + i) & 255
        key[i] = h & 255
    return bytes(key)


def wag_xor(data: bytes, offset: int, key: bytes) -> bytes:
    period = len(key) - 1
    if period < 1:
        raise ValueError("invalid WAG key")
    # NumPy is optional; the portable path uses exactly the same byte schedule.
    try:
        import numpy as np
    except ImportError:
        return bytes(v ^ key[(offset + i) % period] for i, v in enumerate(data))
    mask = key[offset % period : period] + key[: offset % period]
    repeated = (mask * (len(data) // period + 1))[:len(data)]
    return np.bitwise_xor(np.frombuffer(data, dtype=np.uint8),
                          np.frombuffer(repeated, dtype=np.uint8)).tobytes()


@dataclass
class Entry:
    index: int
    name_raw: bytes
    offset: int
    size: int
    container_offset: int
    container_size: int
    chunks: list[dict]

    @property
    def name(self) -> str:
        return self.name_raw.decode("cp932", errors="strict")

    def locator(self) -> dict:
        return {"entry_index": self.index, "original_name": self.name,
                "original_name_bytes_hex": self.name_raw.hex(),
                "original_name_sha256": sha256(self.name_raw),
                "offset": self.offset, "size": self.size,
                "container_offset": self.container_offset,
                "container_size": self.container_size, "chunks": self.chunks}


class Archive:
    def __init__(self, path: Path, data: bytes | None = None):
        self.path = Path(path)
        self.data = data
        self.file_size = len(data) if data is not None else self.path.stat().st_size
        self.key = None
        with self.open() as stream:
            header = read_at(stream, 0, min(0x4a, self.file_size))
            if header[:4] == b"MIKO":
                self.kind = "MIKO"
                self.entries = self._miko(stream, header)
            elif header[:4] == b"WAG@":
                self.kind = "WAG"
                self.entries = self._wag(stream, header)
            else:
                raise ValueError(f"unsupported archive signature {header[:8]!r}")
        names = [e.name for e in self.entries]
        if len(names) != len(set(names)):
            # Raw names are preserved; index-based output names avoid collisions.
            self.duplicate_names = len(names) - len(set(names))
        else:
            self.duplicate_names = 0

    def open(self):
        return io.BytesIO(self.data) if self.data is not None else self.path.open("rb")

    def _check(self, offset, size):
        if offset < 0 or size < 0 or offset + size > self.file_size:
            raise ValueError(f"entry outside archive: {offset}, {size}")

    def _miko(self, stream, header):
        if struct.unpack_from("<H", header, 10)[0] != 0x1001:
            raise ValueError("unsupported MIKO version")
        if struct.unpack_from("<I", header, 12)[0] & 15:
            raise ValueError("unsupported MIKO mode")
        count = struct.unpack_from("<I", header, 16)[0]
        if not 0 < count < 1_000_000 or header[22:26] != b"DFNM" or header[36:40] != b"NDIX":
            raise ValueError("invalid MIKO directory")
        cadr = struct.unpack_from("<Q", header, 26)[0]
        if read_at(stream, 44 + 16 * count, 4) != b"CTIF" or read_at(stream, cadr, 4) != b"CADR":
            raise ValueError("invalid MIKO table markers")
        ndix = read_at(stream, 42, count * 8)
        addresses = read_at(stream, cadr + 6, count * 12)
        entries = []
        for i in range(count):
            name_offset = struct.unpack_from("<I", ndix, i * 8)[0]
            nh = read_at(stream, name_offset, 10)
            if struct.unpack_from("<H", nh)[0] != 0x1001:
                raise ValueError("invalid MIKO name marker")
            name_size = struct.unpack_from("<H", nh, 6)[0]
            name = bytes(v ^ 0x56 for v in read_at(stream, name_offset + 10, name_size))
            data_offset = struct.unpack_from("<Q", addresses, i * 12)[0]
            dh = read_at(stream, data_offset, 30)
            if dh[:4] != b"DATA":
                raise ValueError("invalid MIKO DATA marker")
            size = struct.unpack_from("<I", dh, 24)[0]
            self._check(data_offset + 30, size)
            entries.append(Entry(i, name, data_offset + 30, size,
                                 data_offset, size + 30, []))
        return entries

    def _wag(self, stream, header):
        version = struct.unpack_from("<H", header, 4)[0]
        if version != 0x300:
            raise ValueError(f"unsupported WAG version {version:#x}")
        self.title = header[6:70].split(b"\0", 1)[0]
        count = struct.unpack_from("<I", header, 70)[0]
        if not 0 < count < 1_000_000:
            raise ValueError("invalid WAG count")
        name_key = wag_key(self.path.name.lower().encode("cp932"))
        pos = 0x200 + sum(name_key)
        for _ in range(2):
            for value in name_key:
                pos ^= value
                pos = ((pos >> 1) | ((pos & 1) << 31)) & 0xffffffff
        pos = pos % 0x401 + 0x4a
        index_key = bytes((count + (name_key[(i+1) % len(name_key)] ^
                                   (name_key[i % len(name_key)] + i))) & 255
                          for i in range(count * 4))
        index = wag_xor(read_at(stream, pos, count * 4), pos, index_key)
        offsets = list(struct.unpack(f"<{count}I", index)) + [self.file_size]
        if any(a >= b for a, b in zip(offsets, offsets[1:])):
            raise ValueError("WAG entry offsets are not strictly increasing")
        self.key = wag_key(self.title)
        def decoded(offset, size):
            self._check(offset, size)
            return wag_xor(read_at(stream, offset, size), offset, self.key)
        entries = []
        for i, (start, end) in enumerate(zip(offsets, offsets[1:])):
            eh = decoded(start, 8)
            if eh[:4] != b"DSET":
                raise ValueError(f"missing DSET in entry {i}")
            chunk_count = struct.unpack_from("<I", eh, 4)[0]
            if chunk_count > 100_000:
                raise ValueError("excessive WAG chunk count")
            cursor = start + 10
            name = None
            picture = None
            chunks = []
            for j in range(chunk_count):
                ch = decoded(cursor, 8)
                tag = ch[:4]
                size = struct.unpack_from("<I", ch, 4)[0]
                if size < 2 or cursor + 10 + size > end:
                    raise ValueError(f"invalid WAG chunk {i}:{j}")
                chunks.append({"tag": tag.decode("ascii"), "offset": cursor, "size": size})
                if tag == b"PICT" and picture is None:
                    picture = (cursor + 16, size - 6)
                elif tag == b"FTAG" and name is None:
                    name = decoded(cursor + 10, size - 2)
                cursor += 10 + size
            if picture is None:
                picture = (start, end - start)
            entries.append(Entry(i, name or f"{self.path.stem}#{i:04d}".encode("ascii"),
                                 *picture, start, end-start, chunks))
        return entries

    def read(self, entry: Entry) -> bytes:
        with self.open() as stream:
            data = read_at(stream, entry.offset, entry.size)
        return wag_xor(data, entry.offset, self.key) if self.key else data
