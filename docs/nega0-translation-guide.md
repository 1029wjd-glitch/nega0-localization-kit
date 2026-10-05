# Nega0 Translation Guide (ネガゼロ / 네가제로)

This guide is for people who want to translate Nega0, extract its scenario scripts or create a Nega0 Korean patch. It connects the existing tools and technical notes without requiring a particular translation workflow.

네가제로 번역을 시작할 때 필요한 스크립트 추출·번역문 재삽입·한글패치 제작 자료의 안내입니다. 이미 추출한 자료가 있다면 원위치와 해시를 재사용하고 필요한 기능부터 읽습니다.

ネガゼロの翻訳を始めるための資料案内です。スクリプト抽出と翻訳テキストの再挿入に関するコード・形式資料へリンクしています。翻訳方法や使用ツールは自由に選べます。

## Extracting Nega0 Scenario Scripts · 스크립트와 일본어 텍스트 추출

지원 기준은 NegaZero.exe 1.0.1.0입니다. 먼저 [버전 프로필](version-profile.json)을 확인합니다. Python 3.10 이상에서 저장소 루트를 작업 폴더로 사용합니다.

```powershell
python -m pip install -r requirements.txt
python unpack.py --sample --game "D:\Games\Nega 0" --output "D:\Nega0Work\sample"
```

[unpack.py](../unpack.py)는 원본을 읽어 별도 출력 폴더에 추출합니다. `--output`은 새 폴더여야 하며 게임 폴더와 겹치면 안 됩니다. 표본을 확인한 뒤 필요하면 `--sample` 대신 `--full`로 범위를 넓힙니다.

Nega0의 MIKO 아카이브와 중첩 엔트리를 [formats.py](../formats.py)로 읽고, [text_extract.py](../text_extract.py)로 NORI 시나리오와 BINF 테이블의 일본어 문자열 후보를 찾습니다. [Nega0 script format](formats.md)에서 원문 바이트·문자열 풀·명령·CRC 구조를 확인합니다. 휴리스틱 후보에는 검토가 필요한 항목이 포함될 수 있으며 모든 VM 명령이 해석된 것은 아닙니다.

| 추출 결과 | Nega0 번역에서의 용도 |
|---|---|
| `translation_input.jsonl` | 번역 후보의 ID·원문·해시·원위치 연결 |
| `text_inventory.jsonl` | 제외 문자열과 내부 키도 포함하는 검토용 목록 |
| `source_manifest.json` | 원본 파일과 해시 |
| `entry_manifest.jsonl` | 중첩 엔트리와 원본 이름 바이트 |
| `image_manifest.jsonl` | 이미지 위치·크기·관련 자료 |
| `review_candidates.jsonl`, `unpack_report.json` | 미분류 후보와 추출 결과·실패 확인 |

## Translating Nega0 Text · 번역 방식과 구조 보존

번역은 제작자가 사용하는 도구나 수작업으로 진행합니다. 이 저장소는 번역 모델이나 단계 이름을 요구하지 않습니다. 원문과 번역문의 연결에는 ID와 `source_sha256`을 유지합니다. 같은 문장이 반복되어도 각 원위치를 따로 연결합니다.

텍스트에 포함된 변수·제어문자와 내부 조회 키를 보존합니다. 표시 이름과 조회 키를 구별하고, BINF 후보를 실제 구조 필드와 대조합니다. 일부 이름 필드의 12 UTF-16 코드 단위 한도는 대사 전체의 한도가 아닙니다. 상세 입력 계약은 [재삽입 연결](repacking.md)에 있습니다.

## Reinserting Translated Text into Nega0 · 번역 적용과 리팩

[reinject.py](../repack/reinject.py)의 `inject_nori`, `inject_miko`, `inject_wag`와 [binf_codec.py](../repack/binf_codec.py)의 `inject_binf`는 제작자의 재삽입 도구에서 호출하는 함수입니다. 제공된 추출 결과를 다른 형식으로 변환해도 원본 엔트리·이름 bytes·주소·해시 연결을 유지해야 합니다.

NORI의 여러 줄 대사는 메시지 메타데이터와 연속된 줄을 함께 재배치해야 백로그가 유지됩니다. MIKO 주소·CRC와 WAG 위치 의존 XOR도 파일 크기 변경에 맞춰 갱신합니다. [repacking.md](repacking.md)의 함수 연결 예와 [formats.md](formats.md)의 보존 조건을 먼저 확인합니다. 완성된 전체 패치 빌더가 포함됐다고 가정하지 않습니다.

## Creating a Nega0 Korean Patch · 한글 표시와 패치 제작

한글 번역문 저장에는 [CP932 표시 매핑과 폰트](display.md)를 연결합니다. 매핑 생성 결과와 네이티브 DLL의 문자표가 일치해야 합니다. 이미지 변경 시에는 [PNG ORGN 보존과 화면 배치](images-and-screen.md)를 확인합니다.

[installer.md](installer.md)는 게임 폴더 선택, 대상 해시 검사, 델타 적용, 원본 복원과 실패 복구를 설명합니다. [적용·복원 프로그램 소스](../repack/installer/Engine.cs)를 제작자의 패키지에 연결할 수 있습니다. 자신의 번역·이미지·매핑 결과와 패치 payload 준비는 별도 작업입니다.

## Known Issues and Status of Nega0 Translation

기존 제작에서 추출·텍스트 재삽입·패키지 적용과 원본 복원 검사가 통과했습니다. 공개 소스의 합성 검사 9개와 네이티브 DLL·설치 프로그램 컴파일도 확인했습니다. 사용자는 2026-10-05 한국어 로케일의 기존 종료 장면을 수정 후 정상 통과했다고 보고했습니다.

한국어 Windows에서 원본 일본어 정렬 순서를 시스템 로케일로 검색하면, 존재하는 이미지 파일을 찾지 못해 종료할 수 있습니다. [Nega0 Korean locale crash 분석](locale-crash.md)에 재현 근거와 제한된 수정 위치가 있습니다.

전체 루트·모든 전투·모든 환경의 플레이 확인은 완료되지 않았습니다. 지원 EXE와 다른 판본에는 주소를 그대로 적용하지 않습니다. 정확한 확인 범위와 남은 항목은 [validation.md](validation.md)를 읽습니다.
