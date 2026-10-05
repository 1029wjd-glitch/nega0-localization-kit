# 파일 형식: 구현을 읽기 위한 지도

확인한 Nega0 1.0.1.0 자료의 구조다. 아래 내용은 모든 Xuse 게임의 규격을 주장하지 않는다. 숫자 오프셋은 달리 표시하지 않으면 파일 내부 상대 위치다. 재주입의 권위 있는 구현은 `repack/reinject.py`, `repack/binf_codec.py`다.

## MIKO 아카이브

- `MIKO` 서명, offset 10의 uint16 버전 `0x1001`, offset 12의 모드 하위 4비트는 0, offset 16의 uint32 엔트리 수.
- offset 22 `DFNM`, 26의 uint64 CADR 주소, 36 `NDIX`. NDIX는 42에서 시작하는 8바이트 레코드이며 첫 uint32가 이름 블록 주소다.
- 이름 블록은 uint16 `0x1001`, +6의 uint16 이름 길이, +10부터 CP932 이름 바이트 XOR `0x56`이다. raw 이름과 표시용 정규화 경로를 따로 보관한다.
- `CADR` 뒤 +4부터 12바이트 주소 레코드. 레코드 +2의 uint64 DATA 주소, 마지막 2바이트 CRC.
- `DATA` 헤더 30바이트, +24의 uint32 payload 길이. 헤더 처음 28바이트 CRC 2바이트와 payload 뒤 CRC 2바이트를 보존/갱신한다.
- CRC는 `binascii.crc_hqx(data, 0)`의 **빅엔디언 uint16**이다.

`inject_miko`는 연속 DATA 배치를 확인하고 길이가 바뀐 하위 파일과 후속 주소·CRC를 재작성한다. 다른 엔트리 payload와 이름 바이트는 재읽기로 비교한다. NDIX를 현재 시스템 정렬로 재정렬하지 않는다. [로케일 문제](locale-crash.md)의 직접 원인이 된다.

## WAG@ v3 이미지 컨테이너

- `WAG@`, uint16 버전 `0x300`, 6:70의 title, offset 70의 uint32 개수.
- **아카이브 파일명 소문자의 CP932 bytes**가 index key/위치 생성에 쓰인다. payload key는 title로 만든다. 파일 이름을 임의로 바꿔 파서에 전달하면 안 된다.
- `wag_key`는 signed-byte 산술이 중요하다. `wag_xor(data, absolute_offset, key)`는 `len(key)-1` 주기의 위치 의존 XOR이다.
- DSET에는 PICT/FTAG chunk가 있다. PICT flags 4바이트 + CRC 2바이트 + PNG, FTAG에는 원본 이름이 있다.
- CRC는 복호화한 논리 데이터가 아닌 **저장된 암호화 바이트**에 적용한다. PICT flags CRC와 각 chunk/header CRC를 구별한다.
- 이미지 길이가 달라지면 뒤쪽 chunk의 위치가 변하므로 수정하지 않은 논리 데이터도 새 위치로 재인코딩한다. `inject_wag`는 FTAG·flags·비대상 payload의 논리적 동일성을 확인한다.

## NORI 시나리오

`NORI\0\0\x01\0`로 시작한다. 헤더 40바이트 + CRC 2바이트. offset 8부터 8개의 uint32가 label/global/local의 개수·크기, code 크기, pool 크기를 나타낸다. 각 symbol/code/pool 블록 뒤에 CRC가 붙는다. symbol CRC는 코드에 정의한 XOR 해제 범위를 따른다.

문자열은 CP932 표시 bytes XOR `0x53`. code operand는 `<HHI>`의 type/length/pool-relative-pointer이며 문자열 type은 5다. 제어 필드와 출력 문자열을 구별한다. 추출기는 알려진 opcode와 휴리스틱에 기반하며 전체 VM 명세가 아니다.

특히 대사 opcode 1/60은 첫 operand가 8바이트 message metadata를 가리키고, 뒤의 줄들이 **같은 metadata 직후 연속**으로 저장된다. 백로그는 이 연속성을 사용한다. 일부 줄만 번역하더라도 metadata와 번역하지 않은 인접 줄까지 묶어 새 pool 끝에 추가하고 각 pointer를 갱신해야 한다. 원래 pool은 유지한다.

`inject_nori`는 operand/type/source bytes 일치, metadata와 줄 연속성, non-target code 보존, CRC, 적용 수량을 검사한다. 빈 문자열과 0x8000바이트 이상 필드는 거부한다. 일반 대사 밖의 명령은 별도 구조를 확인한다.

## BINF 테이블

`BINF\x01\0\0\0`, 헤더 32바이트, offset 8의 uint32 행 수. 테이블별 schema에 따라 숫자와 문자열 필드가 섞인다. 문자열 저장은 uint32 byte length + ROR1(CP932 bytes + NUL), 단 길이 0은 NUL도 없다. 행 CRC는 raw 숫자/길이와 **ROL1 복원 문자열 + NUL**을 합쳐 계산한다.

`schema_for`는 CharDefines, CharProfile, ItemExp, SkillExp*, ItemData, Skill* 일부를 지원한다. SkillDeck은 제외한다. 숫자·내부 키는 보존한다. 모든 문자열 필드를 표시 필드로 간주하지 않는다.

schema의 capacity는 엔진의 UTF-16 버퍼 바이트 수다. 26바이트 버퍼는 종료 NUL을 제외하면 **12 UTF-16 코드 단위**까지다. CharProfile 설명에는 0x23c바이트의 첫 복사 대상도 적용한다. 시각적 글자 폭과 별개의 제한이다. `inject_binf`는 capacity, 내부 key, row CRC, 비대상 필드와 저장 후 결과를 확인한다.

## DTFA skin

`Data/skin.bin`: `DTFA\0\0\x02\0` + CRC, DATA command와 XOR `0x73` 문자열 operand의 중첩 scope 구조다. `adjust_text_position.py`는 검증된 Normal MessageWindow/Text의 top margin 20→17, NameWindow/Text 6→3만 바꾸고 CRC를 갱신한다. 다른 창의 좌표에 일괄 적용하지 않는다. 현재 parser는 assert를 사용하므로 검증 시 Python `-O`를 쓰지 않는다.
