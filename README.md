# Nega0 / NegaZero / ネガゼロ · 네가제로 언팩·리팩 및 한글화 기술 자료

네가제로(Nega0 / NegaZero) 한글패치를 새로 제작하는 사람과 그 작업을 돕는 AI를 위한 **분석 기록과 재사용 가능한 소스 코드**입니다. MIKO/WAG 아카이브, NORI/BINF 문자열 재주입, CP932 기반 한글 표시, 한국어 로케일 호환성, 적용·복원 프로그램의 구현을 모았습니다.

**Nega0, NegaZero, Nega Zero, ネガゼロ, 네가제로**의 언팩(unpack / extract), 리팩(repack / rebuild), 텍스트 재삽입(text reinjection), 한글화(Korean localization / Korean translation patch)를 위한 기술 자료입니다. `.arc` MIKO, `.wag` WAG@, NORI script, BINF table, PNG ORGN trailer를 다룹니다.

## English overview — resource unpacking and repacking

This repository documents **Nega0 / NegaZero / ネガゼロ** resource formats and provides reusable Python unpacking/repacking code, text reinjection helpers, and Windows Korean localization runtime sources. It covers MIKO `.arc` archives, WAG@ `.wag` image containers, NORI script string pools, BINF typed text tables, CRC16 updates, positional XOR encoding, PNG ORGN origin trailers, CP932 private-use character mapping, font metrics, and Japanese filename collation on Korean Windows.

For **Nega0 archive extraction**, start with [formats.py](formats.py), [unpack.py](unpack.py), and the [format reference](docs/formats.md). For **NegaZero archive rebuilding and translated text insertion**, use [reinject.py](repack/reinject.py), [binf_codec.py](repack/binf_codec.py), and the [repacking input contract](docs/repacking.md). For **Korean locale crashes caused by archive filename binary search**, see the [collation diagnosis and fix](docs/locale-crash.md). Most detailed notes are in Korean; code identifiers, format signatures, offsets and the [version profile](docs/version-profile.json) are directly inspectable.

The verified executable is **NegaZero.exe 1.0.1.0 (x86 PE32)**. Check its SHA-256 before reusing executable offsets. Game assets, translated dialogue and ready-made patch binaries are not included. The techniques can be connected to your own translation workflow.

## 기능별 검색어와 자료

| 필요한 기능 / 검색에 사용할 표현 | 바로 읽을 자료 |
|---|---|
| Nega0 unpack, NegaZero extraction, 네가제로 언팩, ネガゼロ 展開 | [언팩 도구](unpack.py), [MIKO/WAG 파일 형식](docs/formats.md) |
| Nega0 repack, MIKO archive rebuild, WAG repacking, 네가제로 리팩 | [리팩 함수](repack/reinject.py), [입력 연결](docs/repacking.md) |
| NORI script text extraction, string pool relocation, backlog corruption | [문자열 추출](text_extract.py), [대사 그룹 재배치](repack/reinject.py) |
| BINF text reinjection, row CRC16, fixed UTF-16 buffer, skill name limit | [타입별 BINF 파서와 재삽입](repack/binf_codec.py) |
| CP932 Korean patch, private-use mapping, DBCS lead byte, font alignment | [한글 인코딩·폰트 처리](docs/display.md) |
| PNG ORGN trailer, WAG image replacement, sprite origin | [이미지 보존과 재포장](docs/images-and-screen.md) |
| NegaZero Korean locale crash, MIKO binary search, CompareStringW collation | [원인 분석과 검색 재현](docs/locale-crash.md) |

**AI에게는 저장소 주소와 함께 [AI_START.md](AI_START.md)를 먼저 읽도록 알려주세요.** 처음부터 파일 형식을 다시 추측하지 않고, 확인된 코드와 실패 사례를 출발점으로 사용할 수 있습니다.

이 저장소에는 게임 본체·원본 리소스·번역 대사·편집 이미지·완성 패치가 들어 있지 않습니다. 소유한 게임과 자신의 번역·이미지 결과를 입력으로 사용합니다. 설치 후 바로 적용하는 완성 패치 프로그램이 아니라 제작용 기술 키트입니다.

## 먼저 읽을 자료

| 작업 | 문서 / 코드 |
|---|---|
| AI 작업 시작, 확인 순서와 금지할 추측 | [AI_START.md](AI_START.md) |
| 언팩 결과를 자신의 리팩 도구에 연결 | [언팩·리팩 연결](docs/repacking.md) |
| 파일 형식, 바이트·CRC·원위치 | [파일 형식](docs/formats.md), [formats.py](formats.py), [reinject.py](repack/reinject.py), [binf_codec.py](repack/binf_codec.py) |
| 한글 인코딩·폰트·줄 간격 | [한글 표시](docs/display.md), [표시 매핑 생성기](repack/prepare_display_mapping.py) |
| 한국어 환경의 특정 장면 종료 | [로케일 오류 분석](docs/locale-crash.md), [검색 재현 도구](repack/verify_archive_locale.py) |
| 이미지·ORGN·전투 조각 겹침 | [이미지와 화면](docs/images-and-screen.md) |
| 설치 폴더 선택·적용·복원·델타 | [배포 프로그램](docs/installer.md), [C# 구현](repack/installer/Engine.cs) |
| 확인된 사실과 남은 검증 | [검증 범위](docs/validation.md), [버전 프로필](docs/version-profile.json) |

## 빠른 시작

Python 3.10 이상에서 저장소 루트를 작업 폴더로 사용합니다. 전체 추출에는 디스크 공간이 많이 필요합니다. 먼저 작은 표본을 확인하세요.

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python unpack.py --sample --game "D:\Games\Nega 0" --output "D:\Nega0Work\sample"
```

표본 확인 후 필요한 범위의 전체 데이터를 추출할 수 있습니다. `--output`은 새 폴더여야 하며 게임 폴더와 겹치면 안 됩니다.

```powershell
python unpack.py --full --game "D:\Games\Nega 0" --output "D:\Nega0Work\unpacked"
```

`unpack.py`가 만드는 `translation_input.jsonl`과 `text_inventory.jsonl`은 서로 용도가 다릅니다. 전자는 번역 후보, 후자는 제외 문자열과 내부 키도 포함하는 검토용 목록입니다. 사용하는 번역 방식은 자유롭게 선택할 수 있습니다. 재삽입할 때에는 추출 원위치의 ID·원본 바이트·해시와 변경 문자열의 연결을 유지하세요.

## 기준과 현재 상태

- 원본 **NegaZero.exe 1.0.1.0**, x86 PE32, SHA-256 `e51c64bbd3b0584b15d8bb11cad4ea1c107d43b24fda7a2171d49bde9a86dfa1` 기준입니다. 다른 파일에 실행파일 주소를 그대로 적용하지 마세요.
- 이 키트는 **2026-10-05, 파일명 정렬 수정이 포함된 기술 소스**를 정리한 자료입니다. 공개용으로 매핑 입력·출력 경로와 의존성을 분리했습니다.
- 기존 제작에서 파일 구조·재주입·적용·복원 자동 검사가 통과했습니다. **2026-10-05 사용자가 한국어 로케일의 기존 문제 장면을 실제 플레이에서 이상 없이 통과했다고 확인**했습니다. 전체 플레이 완료나 모든 환경 호환성을 의미하지 않습니다.
- 기존 전체 추출은 80,351개 번역 후보를 추출했으며, 재삽입에서 필드가 아닌 오탐 1개를 보존하고 80,350개를 적용했습니다. 다른 판본이나 범위에서 이 수량을 강제로 맞추지 마세요.

## 라이선스와 출처

이 저장소의 자체 코드와 문서는 [MIT](LICENSE)입니다. GARbro에서 참고한 아카이브 알고리즘의 저작권·허가 고지는 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)에 보존했습니다. 게임 자료와 외부 폰트·라이브러리의 권리는 각각의 권리자 및 라이선스를 따릅니다. 게임·폰트 바이너리는 포함하지 않습니다.
