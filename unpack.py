"""Standalone read-only unpacker for Nega0, with a bounded sample mode."""
from __future__ import annotations

import argparse
import html
import io
import json
import re
import struct
import sys
import zlib
from collections import Counter
from pathlib import Path
from urllib.parse import quote

from formats import Archive, sha256
from text_extract import nori, binf, protection
from pe_strings import candidates, resources, resource_strings

ROOT = Path(__file__).resolve().parent
DEFAULT_GAME = Path(r"C:\Program Files (x86)\Will\Nega 0")
# Small representatives: normal scenes, locals/choices, tutorials, battle subtitles,
# table names/descriptions, UI atlases, PNG effects and a character/background WAG.
SAMPLE = {
    "rio.arc": {"0000.bin", "0100.bin", "0100_02.bin", "BTLTutorial.bin", "STSTutorial.bin", "main.bin"},
    "bscp.arc": {"002a_BTVoice.bin"},
    "dc.arc": {"CharDefines.bin", "CharProfile.bin", "Skill002a.bin", "SkillExp002a.bin", "ItemData.bin", "ItemExp.bin"},
    "gd.arc": {"Title.wag", "StatusInfo.wag", "StatusCharaName.wag", "StatusWindow.wag", "ControlGuide.png"},
    "wnd.arc": {"dialog.wag"},
    "btg.arc": {"ic.wag"},
    "btf.arc": {"fb01_01.wag"},
    "ef.arc": {"AuraRing_W_101.png"},
    "besg.arc": {"AuraRing_B_001.png"},
    "bg0000.wag": None,
    "bu0000.wag": None,
}


def dump(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8", newline="\n")


def file_hash(path: Path):
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4*1024*1024):
            h.update(chunk)
    return h.hexdigest()


def safe_name(name: str) -> str:
    base = name.replace("\\", "/").split("/")[-1]
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base).strip(" .")
    return (base or "unnamed")[:150]


def validate_png(data: bytes) -> dict:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("decoded image is not a PNG")
    p, chunks = 8, []
    info = None
    while p+12 <= len(data):
        size = struct.unpack_from(">I", data, p)[0]
        end = p+12+size
        if end > len(data):
            raise ValueError("truncated PNG chunk")
        tag = data[p+4:p+8]
        stored_crc = struct.unpack_from(">I", data, p+8+size)[0]
        if zlib.crc32(data[p+4:p+8+size]) != stored_crc:
            raise ValueError(f"PNG CRC mismatch: {tag!r}")
        chunks.append(tag.decode("ascii"))
        if tag == b"IHDR":
            width, height, depth, color = struct.unpack_from(">IIBB", data, p+8)
            if not 0 < width <= 100_000 or not 0 < height <= 100_000:
                raise ValueError("invalid PNG dimensions")
            info = {"width": width, "height": height, "bit_depth": depth,
                    "color_type": color, "has_alpha": color in (4, 6)}
        p = end
        if tag == b"IEND":
            if info is None or "IDAT" not in chunks:
                raise ValueError("PNG end/chunk reconciliation failed")
            trailer = data[p:]
            # Xuse PNGs can carry ORGN + signed x/y + a checksum after IEND.
            # Keep these original bytes in the exported file and in the manifest.
            if trailer:
                if len(trailer) != 14 or trailer[:4] != b"ORGN":
                    raise ValueError("unrecognized PNG trailer; raw payload needs review")
                x, y = struct.unpack_from("<ii", trailer, 4)
                info.update(origin_x=x, origin_y=y, png_trailer_hex=trailer.hex(),
                            png_trailer_offset=p)
            else:
                info["png_trailer_hex"] = ""
            info["has_alpha"] = info["has_alpha"] or "tRNS" in chunks
            info["png_crc_valid"] = True
            return info
    raise ValueError("missing PNG IEND")


def gallery(output: Path, images: list[dict]):
    items = [{"path": quote(row["output_path"], safe="/"), "id": row["id"],
              "name": row["original_name"], "group": row["group"],
              "w": row["width"], "h": row["height"], "priority": row["priority"]}
             for row in images]
    encoded = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    page = '''<!doctype html><html lang="ko"><meta charset="utf-8">
<title>Nega0 이미지 목록</title><style>
body{font:16px system-ui;margin:24px;background:#161b22;color:#eee}input,select,button{font:inherit;padding:10px;margin:8px}
#grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}article{background:#242c38;padding:12px;border-radius:8px}
img{width:100%;height:220px;object-fit:contain;background:repeating-conic-gradient(#aaa 0% 25%,#ddd 0% 50%) 50% / 20px 20px}
small{display:block;overflow-wrap:anywhere;margin-top:6px}a{color:#9ddaff}header{position:sticky;top:0;background:#161b22;padding:8px;z-index:1}
</style><h1>Nega0 이미지 목록</h1><p>이미지 안의 일본어 포함 여부는 아직 분류하지 않았습니다. UI 우선 보기와 파일명 검색으로 원본 PNG를 찾을 수 있습니다. 여러 버튼이 한 이미지에 들어 있는 경우도 있습니다.</p>
<header><input id="query" placeholder="Title, Status, 이름 등 검색"><select id="filter"><option value="all">모든 이미지</option><option value="ui">UI 후보 우선</option></select><span id="count"></span></header>
<div id="grid"></div><button id="more">다음 100장 보기</button><script>
const items=__ITEMS__;let selected=[],shown=0;
function update(){let q=document.querySelector('#query').value.toLowerCase(),f=document.querySelector('#filter').value;selected=items.filter(x=>(f==='all'||x.priority==='ui')&&(x.name+' '+x.group+' '+x.id).toLowerCase().includes(q));shown=0;document.querySelector('#grid').replaceChildren();more();}
function more(){let grid=document.querySelector('#grid');for(let x of selected.slice(shown,shown+100)){let a=document.createElement('article'),link=document.createElement('a'),img=document.createElement('img');link.href=x.path;link.target='_blank';img.src=x.path;img.loading='lazy';link.append(img);a.append(link);for(let t of [x.id,x.group,x.name,`${x.w} × ${x.h}`]){let s=document.createElement('small');s.textContent=t;a.append(s);}grid.append(a);}shown=Math.min(shown+100,selected.length);document.querySelector('#count').textContent=`${selected.length}장 중 ${shown}장 표시`;document.querySelector('#more').hidden=shown===selected.length;}
document.querySelector('#query').addEventListener('input',update);document.querySelector('#filter').addEventListener('change',update);document.querySelector('#more').addEventListener('click',more);update();
</script></html>'''.replace("__ITEMS__", encoded)
    (output/"이미지목록.html").write_text(page, encoding="utf-8", newline="\n")


class Extractor:
    def __init__(self, game: Path, output: Path, sample: bool):
        self.game, self.output, self.sample = game.resolve(), output.resolve(), sample
        if self.output.is_relative_to(self.game) or self.game.is_relative_to(self.output):
            raise ValueError("output must be separate from the installed game")
        if self.output.exists() and any(self.output.iterdir()):
            raise ValueError("output folder is not empty; choose a new folder to preserve previous results")
        self.output.mkdir(parents=True, exist_ok=True)
        self.errors, self.images, self.archives, self.tables = [], [], [], []
        self.sources, self.opaque, self.excluded = [], [], []
        self.ids, self.text_counts = set(), Counter()
        self.text_count = self.translation_count = self.raw_count = self.selected_count = 0
        self.top_success = self.top_failed = self.native_resource_count = 0
        self.handles = {}
        for name in ("entry_manifest", "image_manifest", "text_inventory", "translation_input", "review_candidates"):
            self.handles[name] = (output/(name+".jsonl")).open("w", encoding="utf-8", newline="\n")

    def line(self, name, record):
        self.handles[name].write(json.dumps(record, ensure_ascii=False, separators=(",", ":"))+"\n")

    def write(self, relative: str, data: bytes):
        dest = self.output / relative
        if not dest.resolve().is_relative_to(self.output):
            raise ValueError("unsafe output path")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        digest = sha256(data)
        if file_hash(dest) != digest:
            raise ValueError("saved file hash mismatch")
        return digest

    def text(self, data: bytes, name: str, chain: list[dict], output_path: str):
        if name.lower().endswith(".debug"):
            self.excluded.append({"path": output_path, "reason": "debug duplicate of compiled .bin"})
            return
        if data[:4] == b"NORI":
            rows, report = nori(data)
        elif data[:4] == b"BINF":
            rows, report = binf(data, name)
        else:
            self.opaque.append({"path": output_path, "signature_hex": data[:16].hex(),
                                "reason": "raw extracted; no display-string rule verified"})
            return
        self.tables.append({"path": output_path, **report})
        display = []
        for row in rows:
            row_id = "nega0::" + "::".join(f"{c['archive']}[{c['entry_index']}]" for c in chain)
            row_id += f"::text@{row['byte_offset']:08x}"
            # Repeated storage can be referenced from different code operands.
            if "operand_offset" in row:
                row_id += f"::operand@{row['operand_offset']:08x}"
            if row_id in self.ids:
                raise ValueError("duplicate text ID")
            self.ids.add(row_id)
            loc = {k: row[k] for k in ("byte_offset", "byte_length", "length_field_offset", "operand_offset",
                   "pointer_field_offset", "pool_relative_offset", "encoding", "storage_transform",
                   "source_bytes_hex", "source_bytes_sha256", "cp932_roundtrip") if k in row}
            translatable = row["classification"] in ("display_operand", "length_prefixed_table_string")
            context_meta = row.get("context", {})
            context_lines = context_meta.get("message_lines", context_meta.get("choices", []))
            record = {"id": row_id, "source": row["source"], "source_sha256": sha256(row["source"].encode("utf-8")),
                      "category": row["category"], "format": report["format"], "classification": row["classification"],
                      "translatable": translatable,
                      "target": {"file": output_path, "archive_chain": chain, **loc},
                      "context": context_lines, "context_meta": context_meta,
                      "file": name, "speaker": row.get("speaker", ""),
                      **protection(row["source"])}
            self.line("text_inventory", record)
            self.text_count += 1
            self.text_counts[row["classification"]] += 1
            if translatable:
                self.line("translation_input", record)
                self.translation_count += 1
            elif row["classification"] == "needs_review":
                self.line("review_candidates", record)
            if row["classification"] != "exclude":
                display.append(f"[{row_id}]\n{row['source']}\n")
        if display:
            self.write("text_views/"+output_path.replace("raw/", "", 1)+".txt",
                       "\n".join(display).encode("utf-8-sig"))

    def process(self, arc: Archive, entry, chain: list[dict], group: str, depth=0):
        if depth > 5:
            raise ValueError("excessive archive nesting")
        loc = {"archive": group, **entry.locator()}
        chain = [*chain, loc]
        data = arc.read(entry)
        relative = f"raw/{group}/{entry.index:05d}_{safe_name(entry.name)}"
        image_data = data
        if image_data[:6] == b"NG\r\n\x1a\n":
            image_data = b"\x89P"+image_data
        is_png = image_data.startswith(b"\x89PNG\r\n\x1a\n")
        if is_png:
            relative = f"images/{group}/{entry.index:05d}_{safe_name(entry.name)}"
            if not relative.lower().endswith(".png"):
                relative += ".png"
            info = validate_png(image_data)
            self.write(relative, image_data)
            record = {"id": f"nega0::image::{group}::{entry.index:05d}", "output_path": relative,
                      "original_name": entry.name, "group": group, "source_payload_sha256": sha256(data),
                      "png_sha256": sha256(image_data), "archive_chain": chain,
                      "japanese_text_status": "not_classified", "ocr_performed": False,
                      "priority": "ui" if re.search(r"(?i)gd\.arc|wnd\.arc|title|status|system|menu|help|ス[テタ]|ヘルプ", group+entry.name) else "other",
                      **info}
            self.images.append(record)
            self.line("image_manifest", record)
        else:
            self.write(relative, data)
        self.raw_count += 1
        self.line("entry_manifest", {"output_path": relative, "source_payload_sha256": sha256(data),
                                     "size": len(data), "archive_chain": chain,
                                     "image": is_png, "transform": "wag-xor" if arc.key else "none"})
        if data[:4] in (b"WAG@", b"MIKO"):
            nested = Archive(Path(safe_name(entry.name)), data)
            children = nested.entries
            if self.sample:
                indices = {0, len(children)-1}
                if entry.name == "StatusInfo.wag":
                    indices.add(1)
                children = [e for e in children if e.index in indices]
            for child in children:
                try:
                    self.process(nested, child, chain, f"{group}/{entry.index:05d}_{safe_name(entry.name)}", depth+1)
                except Exception as exc:
                    self.errors.append({"archive": group, "entry": child.index, "parent": entry.name, "reason": str(exc)})
        elif not is_png and Path(entry.name).suffix.lower() in (".bin", ".debug", ".var"):
            self.text(data, safe_name(entry.name), chain, relative)

    def executable_candidates(self):
        for name in ("NegaZero.exe", "NegaZero.dll"):
            data = (self.game/name).read_bytes()
            self.sources.append({"path": name, "size": len(data), "sha256": sha256(data), "role": "read-only PE string candidates"})
            rows = candidates(data)
            native_resources = resources(data)
            native_text = []
            for resource in native_resources:
                native_text.extend(resource_strings(data, resource))
            rows.extend(native_text)
            if self.sample:
                # Only counts and up to ten candidates; no claim of full PE extraction.
                rows = rows[:10]+native_text[:5]
                selected_images = [r for r in native_resources if r['resource_path'][0] == 2][:1]
                selected_images += [r for r in native_resources if r['resource_path'] == ['DATA', '__GDF_THUMBNAIL', 1041]]
            else:
                selected_images = native_resources
                for resource in native_resources:
                    parts = [safe_name(str(x)) for x in resource["resource_path"]]
                    relative = f"raw/native_resources/{name}/"+"_".join(parts)+".bin"
                    offset, size = resource["byte_offset"], resource["size"]
                    payload = data[offset:offset+size]
                    self.write(relative, payload)
                    self.line("entry_manifest", {"output_path": relative,
                              "source_payload_sha256": sha256(payload), "size": len(payload),
                              "native_source_file": name, **resource})
                    self.native_resource_count += 1
            for resource in selected_images:
                self.native_image(data, name, resource)
            for row in rows:
                source = row.pop("source")
                record = {"id": f"nega0::{name}::{row['encoding']}@{row['byte_offset']:08x}",
                          "source": source, "source_sha256": sha256(source.encode("utf-8")),
                          "category": row.pop("category"), "classification": row.pop("classification"),
                          "translatable": False, "target": {"file": name, **row}, **protection(source)}
                if record['classification'] == 'resource_string':
                    record['protected_tokens'].extend(re.findall(r'&[A-Za-z]',source))
                self.line("review_candidates", record)
                self.text_counts["pe_review_candidate"] += 1
            dump(self.output/"native_resource_inventory"/(name+".json"),
                 {"file": name, "resources": native_resources, "native_string_count": len(native_text),
                 "dialog_menu_binary_preserved": not self.sample})

    def native_image(self, data, name, resource):
        offset, size = resource['byte_offset'], resource['size']
        payload = data[offset:offset+size]
        converted = False
        if payload.startswith(b'\x89PNG\r\n\x1a\n'):
            png = payload
        elif resource['resource_path'][0] == 2:
            # RT_BITMAP stores a DIB without the fourteen-byte BMP file header.
            from PIL import Image
            dib_size = struct.unpack_from('<I',payload)[0]
            if dib_size < 40:
                raise ValueError('unsupported native DIB header')
            bpp = struct.unpack_from('<H',payload,14)[0]
            compression = struct.unpack_from('<I',payload,16)[0]
            colors = struct.unpack_from('<I',payload,32)[0]
            palette = colors or ((1<<bpp) if bpp <= 8 else 0)
            pixels = 14+dib_size+palette*4+(12 if compression == 3 and dib_size == 40 else 0)
            bmp = b'BM'+struct.pack('<IHHI',len(payload)+14,0,0,pixels)+payload
            image = Image.open(io.BytesIO(bmp))
            image.load()
            stream = io.BytesIO()
            image.save(stream,format='PNG')
            png = stream.getvalue()
            converted = True
        else:
            return
        info = validate_png(png)
        label = '_'.join(safe_name(str(x)) for x in resource['resource_path'])
        path = f'images/native_resources/{name}/{label}.png'
        self.write(path,png)
        record = {'id':f'nega0::native_image::{name}::{label}','output_path':path,
                  'original_name':label,'group':f'native_resources/{name}',
                  'source_payload_sha256':sha256(payload),'png_sha256':sha256(png),
                  'native_source_file':name,'native_resource':resource,
                  'dib_converted_to_png':converted,'japanese_text_status':'not_classified',
                  'ocr_performed':False,'priority':'ui',**info}
        self.images.append(record)
        self.line('image_manifest',record)

    def run(self):
        try:
            for path in sorted((self.game/"Data").iterdir()):
                if path.suffix.lower() not in (".arc", ".wag"):
                    self.excluded.append({"path": "Data/"+path.name, "reason": "audio/video or auxiliary container; outside text/image unpack"})
                    continue
                if path.name.lower() == "btlse.arc":
                    self.excluded.append({"path": "Data/"+path.name, "reason": "audio only"})
                    continue
                if self.sample and path.name not in SAMPLE:
                    continue
                group = "Data/"+path.name
                arc = Archive(path)
                self.archives.append({"path": group, "format": arc.kind, "entries": len(arc.entries), "duplicate_names": arc.duplicate_names})
                selected = arc.entries
                if self.sample:
                    names = SAMPLE[path.name]
                    if names is None:
                        selected = arc.entries[:1]
                    else:
                        selected = [e for e in arc.entries if e.name in names]
                        missing = names - {e.name for e in selected}
                        if missing:
                            raise ValueError(f"missing sample entries in {path.name}: {sorted(missing)}")
                self.selected_count += len(selected)
                # Whole archive hashes belong to the user's full run. Sample hashes
                # are per payload and do not read gigabytes of unrelated assets.
                source = {"path": group, "size": path.stat().st_size, "mtime_ns": path.stat().st_mtime_ns}
                if not self.sample:
                    source["sha256"] = file_hash(path)
                self.sources.append(source)
                print(f"Extracting {path.name}: {len(selected)} selected", flush=True)
                for entry in selected:
                    try:
                        self.process(arc, entry, [], group)
                        self.top_success += 1
                    except Exception as exc:
                        self.top_failed += 1
                        self.errors.append({"archive": group, "entry": entry.index, "name": entry.name, "reason": str(exc)})
            self.executable_candidates()
        except Exception as exc:
            self.errors.append({"phase": "archive", "reason": str(exc)})
        finally:
            for handle in self.handles.values():
                handle.close()
        # Independently re-read JSONL and reconcile source hashes, IDs and counts.
        ids, read_count = set(), 0
        for line in (self.output/"text_inventory.jsonl").read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record["id"] in ids or not record["source"] or not record["target"]:
                self.errors.append({"phase": "verification", "id": record["id"], "reason": "invalid record or duplicate ID"})
            if record["source_sha256"] != sha256(record["source"].encode("utf-8")):
                self.errors.append({"phase": "verification", "id": record["id"], "reason": "source hash mismatch"})
            if (record['protected_tokens'] != protection(record['source'])['protected_tokens']
                    or record['structural_counts'] != protection(record['source'])['structural_counts']):
                self.errors.append({'phase':'verification','id':record['id'],'reason':'protected token/structure mismatch'})
            ids.add(record["id"])
            read_count += 1
        if read_count != self.text_count:
            self.errors.append({"phase": "verification", "reason": "record count mismatch"})
        review_count = self.text_counts["needs_review"]
        report = {"game": "Nega0", "source_root": str(self.game), "mode": "sample" if self.sample else "full",
                  "full_extraction_completed": not self.sample and not self.errors,
                  "unpack_completed": not self.sample and not self.errors,
                  "review_required": True, "review_reason": "Image Japanese/OCR and unknown display opcodes require scope review; unpack success is separate from translation-scope review.",
                  "selected_top_level_entries": self.selected_count, "extracted_entries_including_nested": self.raw_count,
                  "top_level_success": self.top_success, "top_level_failed": self.top_failed,
                  "native_resource_entries": self.native_resource_count,
                  "images": len(self.images), "text_inventory_records": self.text_count,
                  "translation_input_records": self.translation_count, "text_classification_counts": dict(self.text_counts),
                  "unclassified_nori_strings": review_count, "extraction_errors": len(self.errors),
                  "checks": {"archive_bounds": True, "original_name_bytes_preserved": True,
                             "png_crc_and_dimensions": True, "save_reread_sha256": True,
                             "unique_text_ids": len(ids) == read_count,
                             "text_count_reconciled": read_count == self.text_count,
                             "protected_tokens_and_structural_counts": True,
                             "top_level_count_reconciled": self.selected_count == self.top_success+self.top_failed,
                             "text_accounting": self.text_count == sum(self.text_counts[k] for k in ("exclude", "display_operand", "length_prefixed_table_string", "needs_review"))},
                  "archives": self.archives, "tables": self.tables,
                  "opaque_assets": self.opaque, "excluded": self.excluded, "errors": self.errors,
                  "ocr_performed": False, "game_launch_performed": False,
                  "reinsertion_implemented": False}
        dump(self.output/"source_manifest.json", {"source_root": str(self.game), "files": self.sources})
        dump(self.output/"unpack_report.json", report)
        gallery(self.output, self.images)
        print(json.dumps({"mode": report["mode"], "entries": self.raw_count,
                          "images": len(self.images), "texts": self.text_count,
                          "translation_records": self.translation_count,
                          "errors": len(self.errors), "review": review_count}, ensure_ascii=True))
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--sample", action="store_true")
    mode.add_argument("--full", action="store_true")
    parser.add_argument("--game", type=Path, default=DEFAULT_GAME)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or ROOT/("samples" if args.sample else "unpacked")
    try:
        report = Extractor(args.game, output, args.sample).run()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 1 if report["extraction_errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
