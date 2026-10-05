# Nega0 Text Reinsertion · 번역문 재삽입과 리팩 입력 연결

## 언팩에서 보관할 자료

제공된 언팩 도구는 `--sample`과 `--full`을 지원한다. 자체 언팩 도구를 사용해도 된다. 재포장에 필요한 원본 위치·이름 bytes·해시를 보관하는 것이 핵심이다. 원본 게임과 출력 폴더를 섞지 않는다.

주요 출력은 `source_manifest.json`(전체 원본 파일 해시), `entry_manifest.jsonl`(중첩 엔트리), `image_manifest.jsonl`, `text_inventory.jsonl`(전체 후보), `translation_input.jsonl`(번역 대상), `review_candidates.jsonl`, `unpack_report.json`이다. ID는 문자열 내용이 아닌 원위치에 연결한다. 같은 원문이 여러 위치에 있으면 별도 레코드로 유지한다.

`target.archive_chain`의 `entry_index`, `original_name_bytes_hex`, 해시는 재삽입의 근거다. 검색용 경로의 `/`와 게임 원본 파일명 바이트의 구분자를 혼동하지 않는다. `review_required:true`는 미분류·검토 항목이 있다는 상태이며, 추출 자체가 실패했다는 의미가 아니다.

기존 전체 결과의 참고 수량: 번역 후보 80,351, 전체 문자열 목록 99,515, 이미지 19,091. 판본·범위별로 달라질 수 있다. 이미 완료된 전체 추출을 새 AI가 다시 실행할 필요는 없다.

## 변경 문자열의 연결

원본 문자열·주소·bytes·해시와 변경 문자열을 연결한다. 제공된 추출 JSONL의 경우 `id`, `source_sha256`을 사용하며 해시는 원문을 UTF-8로 인코딩한 bytes에 대해 계산한다. 변경 결과에는 동일 ID·원문 해시와 `translation`을 연결하면 된다. 자체 형식을 쓰면 동일한 의미의 정보를 연결하는 어댑터를 만든다. 보호 토큰의 존재뿐 아니라 순서·문법·필수 구분자까지 확인한다.

대사·나레이션·선택지·표시 이름·UI·기술명은 제작자가 선택한 범위에 따라 다룬다. 표시 문자열과 내부 조회 키를 구별해야 한다. BINF의 문자열이라고 해서 모두 화면 표시용인 것은 아니다.

표시 인코딩 생성 예:

```powershell
python repack/prepare_display_mapping.py --translations "D:\Nega0Work\translated.jsonl" --inventory "D:\Nega0Work\unpacked\text_inventory.jsonl" --output repack
```

이 명령은 `repack/display_mapping.json`과 `repack/native/display_mapping.h`를 한 쌍으로 만든다. 선택적으로 `--overrides <JSON>`을 받아 `items[].replacement`도 문자 집합에 포함한다. 번역·축약이 바뀌면 매핑과 DLL, 재주입 결과를 함께 갱신한다.

## 리팩 API와 필요한 입력

이 키트는 구조별 재주입 함수를 제공한다. 아래 API에 제작자의 변경 문자열과 원위치 정보를 연결해 리팩 도구를 구성할 수 있다. 모든 입력 결합·번역 검증·파일 저장을 한 번에 처리하는 완성 빌더는 포함하지 않는다.

```python
import sys
sys.path.insert(0, 'repack')
from display_codec import load_mapping
from reinject import inject_nori, inject_miko, inject_wag
from binf_codec import inject_binf

load_mapping('repack/display_mapping.json')
# records: 해당 원본 leaf의 위치 레코드만, translations: {id: 변경 문자열}
# original_leaf: 원본 manifest 해시로 확인한 bytes
# new_leaf, applied = inject_nori(original_leaf, records, translations)
# new_leaf, applied = inject_binf('ItemData.bin', original_leaf, records, translations)
# wrapped = inject_miko('rio.arc', original_archive, {entry_index: new_leaf})
```

리팩 도구에서 처리할 의존 관계:

1. 원본 파일 SHA-256, 추출 ID·원문 해시와 변경 문자열의 누락·중복을 대조한다.
2. 중첩 archive_chain으로 leaf를 찾아 원본 이름 바이트·엔트리 해시를 대조한다.
3. 대상 레코드를 leaf별로 묶고 `inject_nori` 또는 `inject_binf`에 전달한다. 필드가 아닌 추출 오탐을 제외한다.
4. 변경한 leaf부터 바깥쪽까지 `inject_wag` / `inject_miko`로 다시 포장한다. 원본 아카이브의 이름을 정확히 전달한다.
5. 별도 출력 경로에 저장하고 재읽기해 번역 bytes·CRC·비대상 원본 bytes를 확인한다.
6. `입력 번역 수 = 적용 수 + 실패 수 + 명시한 제외 수`를 기록한다. 기존 작업은 80,350 적용 + 필드 오탐 1 보존이었다. 실패를 제외로 숨기지 않는다.

`inject_*`는 구조·원본 필드 bytes를 검증한다. 입력 전체의 원문 해시, 보호 토큰, 중복 ID는 호출하는 도구에서 확인한다.

### 확인된 BINF 오탐

`nega0::Data/dc.arc[0]::text@00001bf9`는 길이 필드 offset 7157, 데이터 offset 7161, 길이 3으로 추출됐지만 실제 문자열 필드가 아니다. 원본 bytes `b95842`, 원문 해시 `c71588276e48e56e6e1f94a469610312f6bbfdf7b7afca90241e1d643f8c8c47`이다. 행 CRC와 다음 숫자 필드 경계를 가로지른다. 타입 파서로 제외하고 숫자 필드는 보존하며 CRC는 변경한 행에 맞춰 다시 계산한다. 오탐 범위의 CRC 바이트까지 원본으로 강제로 고정하면 오히려 파일을 깨뜨린다.

## 파일 검사로 확정할 수 없는 증상

자동 검사 후 사용자가 대사·백로그·선택지·전투·세이브·로드·전체화면과 보고된 크래시 장면을 확인한다. 시스템 로케일·실행 방법·EXE 해시·패치 버전·직전 대사·오류 번호 또는 조용한 종료 여부를 함께 기록한다. 전체 플레이를 수행하지 않았으면 완료했다고 쓰지 않는다.
