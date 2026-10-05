# Nega0 Translation Images and Layout · 이미지·대사창·전투 화면

## PNG와 ORGN

게임의 PNG 일부는 IEND 뒤에 **14바이트 ORGN trailer**가 있다: `ORGN` 4바이트, little-endian signed x/y 각 4바이트, 마지막 2바이트. 이미지 편집기나 Pillow로 저장하면 이 부분이 사라질 수 있다. 원본 trailer를 그대로 보관하고 편집된 PNG의 IEND 뒤에 붙인다. 파일 끝의 IEND 문자열을 무조건 검색하기보다 PNG chunk를 길이대로 순회한다.

`unpack.py`의 PNG 검사는 chunk CRC, 크기·형식, trailer 구조를 확인한다. ORGN의 마지막 2바이트에 대해 새 알고리즘을 검증했다고 주장하지 않는다. 편집 전후 trailer byte-exact 보존이 현재 방법이다.

image_manifest의 ID, archive_chain, 원본 이름 bytes·해시로 이미지를 되찾는다. 편집 후 PNG/RGBA, dimensions, trailer, 저장 해시, 재포장 후 leaf를 검사한다. WAG 길이 변화는 위치 의존 XOR을 바꾸므로 변경한 PNG bytes만 원본 파일에 덮어쓰면 안 된다.

기존 이미지 작업은 7개 archive 계열의 검토용 PNG 54개 중 실제 수정 대상 47개였다. 전체 이미지 19,091개를 모두 다시 번역할 필요는 없다. 이 키트는 원본·편집 PNG나 번역 전문을 포함하지 않는다.

## 전투 제목 조각의 겹침

체인/스위치/앱 표시는 여러 글자 이미지 조각의 합성이다. 한 조각만 보고 가운데 정렬하면 다른 조각과 겹친다. 문제 대상은 `nega0::image::Data/btg.arc/00000_btg.wag::00003`, 512×512 atlas였다.

기존 수정은 글리프를 새로 그리거나 크기를 줄이지 않고, 7개 행의 글자 영역과 앱 조각을 옮겼다. 앱 조각은 x/y +2, 앞쪽 조각에는 suffix를 위한 4px 간격을 추가했다. 이 좌표는 기존 한국어 글리프에 대한 사례이며 새 번역 이미지의 보편 값이 아니다.

원본 위치와 픽셀 단위로 일치시키는 것보다 실제 체인, 스위치, 체인+스위치 조합에서 서로 안 겹치게 배치한다. 동일 글리프/크기 보존, 허용 사각형 밖 픽셀 불변, ORGN 보존을 자동으로 검사하고 실제 전투 화면은 별도로 확인한다.

## 창 확대와 전체화면

`native/fullscreen.c`는 게임의 800×600 렌더 버퍼를 유지하고 최종 출력에서 비율 유지 확대와 letterbox를 수행한다. Direct3D9 객체의 원래 주소·vtable 정체성 및 드라이버 내부 필드를 보존한다. 종료/Reset/Release 중 재진입과 임시 surface의 수명을 구분해야 한다.

메인 게임의 확인된 ScreenToClient 호출 VA `0x4398d0`, `0x43c711`과 ClientToScreen `0x43bf78`만 논리 좌표로 변환한다. 일반 Win32 확인창까지 같은 변환을 적용하면 버튼·창 위치가 어긋난다. `patch_executable.py`에 허용 목록이 있다.

`test_fullscreen.c`와 `fullscreen_mock.h`는 과거의 mock/숨김창 검증 소스다. 실제 GPU 경로는 테스트 환경에서 장치 생성 오류 `0x8876086a`로 확인되지 않았다. mock의 성공을 실제 GPU 화면 성공으로 확대하지 않는다. 새 작업에서 관련 코드를 바꾸지 않았다면 같은 환경 실패를 반복 실행할 필요는 없다.
