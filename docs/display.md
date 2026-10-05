# 한글 표시: 저장 bytes와 화면 글리프를 분리하기

## CP932 사설 영역 매핑

게임은 CP932 한/두 바이트 단위로 문자열을 나눈다. 단순히 UTF-8 문자열을 넣고 최종 변환 API만 교체하면 백로그·줄 분할·제어문 처리에서 문제가 생긴다. 현재 방식은 CP932에 정확하게 왕복되지 않는 한글 등을 사설 영역 U+E000부터 연속 배정하고, 화면 변환 단계에서 원래 Unicode로 되돌리는 것이다.

최대 1,880 슬롯, CP932 lead byte F0..F9를 사용한다. 원본의 일본어·기호·파일명 bytes는 유지한다. 원본 전체 문자열 목록과 내부 경로에 해당 사설 슬롯이 이미 사용되지 않았는지 검사해야 한다. 표본만 검사한 매핑을 전체판에 재사용하지 않는다.

`prepare_display_mapping.py`는 번역 문자열의 코드포인트를 정렬해 JSON과 C header를 동시에 만든다. NUL·비 BMP·슬롯 충돌·용량 초과를 거부한다. 번역을 바꾸면 슬롯 번호가 바뀔 수 있으므로 재주입과 DLL을 같은 매핑에서 다시 빌드한다. 이전 빌드의 DLL과 새 아카이브를 섞지 않는다. 기존 제작에서 매핑 문자 수는 1,415였지만 새 번역에서 달라진다.

공개용 `display_codec.py`는 개인 매핑 파일을 import 시 자동 로드하지 않는다. **한글을 인코딩하기 전에 `load_mapping(path)`를 호출**한다. 매핑되지 않은 한글은 CP932 인코딩 오류로 멈춘다. CP932에 직접 들어가는 문자만 사용할 때에는 매핑 없이 저수준 형식 테스트가 가능하다.

## 런타임 DLL

`native/korean.c`는 MultiByteToWideChar/WideCharToMultiByte, CreateFontW, GetCharABCWidthsW 등의 표시 경로를 연결한다. `NegaIsDBCSLeadByte`는 시스템 ACP 대신 `IsDBCSLeadByteEx(932, value)`를 사용한다. CP932 디코딩과 바이트 분할의 기준을 맞추기 위해서다.

폰트는 DLL 옆 `Nega0Korean.ttf`를 FR_PRIVATE로 등록하며, 현재 구현의 family 이름은 Noto Sans KR이다. 다른 폰트를 쓰면 family, glyph coverage, metrics를 함께 수정·검사한다. [font_source.json](../repack/native/font_source.json)은 사용했던 외부 원본 URL과 SHA-256 기록이다. 해당 URL은 branch가 변경될 수 있으므로 내려받은 파일이 기록 해시와 다르면 자동으로 같은 것으로 취급하지 않는다. 폰트는 이 저장소에 포함하지 않으며 배포 시 해당 OFL 고지를 포함한다.

### 빌드

Visual Studio의 **x86 Native Tools Command Prompt**에서 실행한다. x64 DLL은 x86 게임에 로드되지 않는다.

```bat
cd repack\native
build.cmd
```

먼저 Python 매핑 생성기로 `display_mapping.h`를 만들어야 한다. `build.cmd`는 C 컴파일러와 Windows SDK가 준비된 환경을 요구한다. 빌드된 DLL과 자신의 폰트는 패치 결과 EXE 옆에 배치한다.

```powershell
python repack/patch_executable.py "D:\Games\Nega 0\NegaZero.exe" "D:\Nega0Work\build\NegaZero.exe"
```

이 CLI는 원본을 읽고 **새 출력 파일**만 만든다. 원본 SHA가 다르면 실패한다. 원본 import descriptor를 유지하고 .ngko 데이터 section을 추가해 확인된 호출을 DLL로 연결한다. 현재 CLI는 한글 표시 외에 전체화면·로케일·진단 연결도 포함한다. 각 기능을 독립적으로 끄는 범용 옵션 UI는 제공하지 않는다. 기존 `patch(..., require_game_hash=False)`는 합성 PE 실험용이며 실제 게임에서 해시 검사를 건너뛰는 용도로 쓰지 않는다.

## 폰트 크기와 배치에서 배운 점

원본 크기를 완전히 따라가기보다 대사·백로그·메뉴의 가독성과 정렬을 확인한다. 기존 글꼴 교체에서 음수 높이 -24는 약 35px cell을 만들어 버튼 글자와 줄이 밀렸다. 양수 cell 높이로 조정하고 대사 전용 요청 24→26, 대사 공백 폭 +2 등으로 구분했다. 메뉴의 일본어까지 일괄 확대하면 위치가 어긋날 수 있다.

현재 값은 해당 폰트·800×600 UI에서 고른 값이다. 다른 폰트나 UI에서 고정 규칙으로 복사하지 않는다. 이름 1줄, 긴 대사 3줄, 백로그, 확인/취소 버튼, 전투 UI를 각각 확인한다. 파일 검사만으로 시각적 성공을 선언하지 않는다.
