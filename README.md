# Nega0 (ネガゼロ / 네가제로) Translation Tools

Tools and technical documentation for **Nega0 translation**, including Nega0 script extraction, translated text reinsertion and Korean patch creation. The game is also referred to as NegaZero or Nega Zero.

이 저장소는 **Nega0(네가제로 / ネガゼロ) 번역과 한글패치 제작**을 위한 기술 자료입니다. 네가제로 스크립트 추출, 번역문 재삽입, 한글 표시와 한국어 로케일 문제 해결에 필요한 분석 기록과 소스 코드를 제공합니다.

ネガゼロの翻訳・韓国語パッチ制作に向けた技術資料です。Nega0のスクリプト抽出、翻訳テキストの再挿入、文字表示とロケールの問題を扱います。

## What is this repository? · Nega0 번역에 어떻게 도움이 되나요?

If you want to translate Nega0 or create a Nega0 Korean patch, start with the [Nega0 translation guide](docs/nega0-translation-guide.md). It connects text extraction, your own translation method, text reinsertion and patch packaging to the relevant implementation and known issues.

**Nega0 한글패치를 새로 제작하는 사람과 그 작업을 돕는 AI**가 파일 형식을 처음부터 다시 추측하지 않도록 정리한 제작용 자료입니다. 자동 번역 서비스나 바로 설치하는 완성 한글패치가 아닙니다. 게임 본체·원본 리소스·번역 대사·편집 이미지·폰트·완성 패치 바이너리는 포함하지 않습니다.

## Nega0 Translation Workflow · 기술 자료 활용 순서

다음은 기능을 연결하는 예시입니다. 번역 도구·모델·수작업 여부와 제작자의 작업 절차는 자유롭게 선택합니다.

1. **Extract Nega0 files and scenario text.** [unpack.py](unpack.py)로 작은 표본을 확인하고, 필요한 데이터를 추출합니다. [Nega0 파일 형식](docs/formats.md)에서 MIKO/WAG 아카이브와 NORI/BINF 문자열 구조를 확인합니다.
2. **Translate Nega0 text using your own method.** 원위치 ID·원문 해시와 번역문 연결을 유지하고 제어문자·내부 조회 키를 보존합니다. 추출 후보 중 구조 필드가 아닌 항목은 구별합니다.
3. **Reinsert translated text into Nega0.** [재삽입 입력 연결](docs/repacking.md), [reinject.py](repack/reinject.py), [binf_codec.py](repack/binf_codec.py)로 길이·포인터·CRC와 비대상 데이터를 보존합니다. 제공된 리팩 함수는 제작자의 도구에 연결하는 API이며 완성된 일괄 빌더는 아닙니다.
4. **Prepare Korean display and a Nega0 translation patch.** [한글 인코딩·폰트](docs/display.md), [이미지 처리](docs/images-and-screen.md), [적용·복원 프로그램](docs/installer.md)을 필요한 범위에서 연결합니다.
5. **Validate and play-test the translated game.** [알려진 로케일 오류](docs/locale-crash.md)와 [검증 범위](docs/validation.md)를 읽고 구조 검사와 실제 플레이 확인을 구별합니다.

## Nega0 Translation Documentation

| 필요한 작업 | 문서 / 코드 |
|---|---|
| Nega0 번역 시작과 스크립트 추출 | [Nega0 Translation Guide](docs/nega0-translation-guide.md), [unpack.py](unpack.py), [text_extract.py](text_extract.py) |
| AI가 먼저 읽을 기술 자료 안내 | [AI_START.md](AI_START.md) |
| Nega0 script format / archive extraction | [Nega0 파일 형식](docs/formats.md), [formats.py](formats.py) |
| Nega0 text reinsertion / archive repacking | [재삽입 입력 연결](docs/repacking.md), [reinject.py](repack/reinject.py), [binf_codec.py](repack/binf_codec.py) |
| Nega0 Korean text / font compatibility | [한글 표시](docs/display.md), [표시 매핑 생성기](repack/prepare_display_mapping.py) |
| Nega0 Korean patch creation / restore | [배포 프로그램](docs/installer.md), [C# 구현](repack/installer/Engine.cs) |
| Known issues with Nega0 translation | [한국어 로케일 종료 원인](docs/locale-crash.md), [이미지·화면](docs/images-and-screen.md) |
| 지원 판본·확인된 결과·남은 검증 | [버전 프로필](docs/version-profile.json), [검증 범위](docs/validation.md) |

## Nega0 Translation FAQ

### 네가제로 한글패치를 만들고 싶은데 이 자료를 쓸 수 있나요?

네. Nega0 번역에 필요한 스크립트 추출과 번역 적용, 한글 표시, 패치 적용·원본 복원 구현을 참고할 수 있습니다. 소유한 게임 데이터와 자신의 번역 결과가 필요하며, 사용하는 번역 절차는 이 저장소가 지정하지 않습니다.

### How do I extract Nega0 scripts?

Use [unpack.py](unpack.py) with `--sample` first. It records archive entry locations and extracts candidate Japanese text from NORI scenario scripts and supported BINF tables. See the [Nega0 script extraction guide](docs/nega0-translation-guide.md) for outputs, source hashes and review limits. The parser is not a complete specification of every script instruction.

### Can I use this repository to translate Nega0 into another language?

The Nega0 archive and script references can inform other translation projects. The display mapping, font runtime and observed gameplay results concern Korean text. Compatibility with other languages must be checked separately; the code is not advertised as a general visual novel translation framework.

### Is this a finished Nega0 Korean patch?

No. This is a source and documentation kit for making a Nega0 translation patch. Existing extraction, reinsertion, packaging checks and a user-confirmed Korean-locale scene are documented in [validation.md](docs/validation.md). All routes, scenes and environments have not been play-tested.

### Can GARbro alone make a Nega0 translation patch?

This kit credits GARbro archive algorithms in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Archive extraction alone does not rebuild translated NORI/BINF text, update pointers and CRCs, or provide Korean text rendering. The Nega0-specific reinsertion and display documentation covers those additional requirements.

## Extracting Nega0 Scenario Scripts · 네가제로 스크립트 추출

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

## Nega0 Translation Status · 확인된 범위와 남은 검증

- 원본 **NegaZero.exe 1.0.1.0**, x86 PE32, SHA-256 `e51c64bbd3b0584b15d8bb11cad4ea1c107d43b24fda7a2171d49bde9a86dfa1` 기준입니다. 다른 파일에 실행파일 주소를 그대로 적용하지 마세요.
- 이 키트는 **2026-10-05, 파일명 정렬 수정이 포함된 기술 소스**를 정리한 자료입니다. 공개용으로 매핑 입력·출력 경로와 의존성을 분리했습니다.
- 기존 제작에서 파일 구조·재주입·적용·복원 자동 검사가 통과했습니다. **2026-10-05 사용자가 한국어 로케일의 기존 문제 장면을 실제 플레이에서 이상 없이 통과했다고 확인**했습니다. 전체 플레이 완료나 모든 환경 호환성을 의미하지 않습니다.
- 기존 전체 추출은 80,351개 번역 후보를 추출했으며, 재삽입에서 필드가 아닌 오탐 1개를 보존하고 80,350개를 적용했습니다. 다른 판본이나 범위에서 이 수량을 강제로 맞추지 마세요.

## 라이선스와 출처

이 저장소의 자체 코드와 문서는 [MIT](LICENSE)입니다. GARbro에서 참고한 아카이브 알고리즘의 저작권·허가 고지는 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)에 보존했습니다. 게임 자료와 외부 폰트·라이브러리의 권리는 각각의 권리자 및 라이선스를 따릅니다. 게임·폰트 바이너리는 포함하지 않습니다.
