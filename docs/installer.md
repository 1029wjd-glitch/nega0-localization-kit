# Nega0 Korean Patch Creation · 적용·복원 프로그램과 델타

사용자는 설치된 게임 폴더를 선택해 한글패치 적용 또는 원본 복원을 수행한다. `repack/installer`는 C# .NET Framework 4의 x86 WinForms 구현이다. 게임 설치기·공식 업데이트·번역 결과 생성기는 포함하지 않는다.

```powershell
powershell -ExecutionPolicy Bypass -File repack/installer/build.ps1
```

이 명령의 ExecutionPolicy는 해당 프로세스에만 적용한다. 소스의 빌드 스크립트를 검토한 뒤 실행한다. Windows의 Framework 컴파일러와 System.Windows.Forms, Drawing, Web.Extensions를 사용한다. 출력은 `repack/dist/Nega0_KoreanPatch`이며 **별도로 만들어야 하는 manifest.json과 payload 없이는 적용할 수 없다.**

## manifest 계약

`Engine.cs`의 Manifest/Entry/Guard가 실제 계약이다. `manifest_version=1`, `patch_id="nega0-ko"`, `patch_version`, `display_name`, `description`, `files`, `guards`를 사용한다. 각 files 항목:

| 키 | 의미 |
|---|---|
| path / action | 게임 기준 상대 경로 / replace 또는 add |
| source_sha256 / source_size | replace의 정확한 원본. add는 null / 0 |
| target_sha256 / target_size | 적용 후 파일 |
| payload / payload_sha256 / payload_size | 패키지 안 델타 파일 이름·해시·크기 |

guards는 변경하지 않지만 판본 확인에 필요한 파일의 path/sha256이다. 기존 패키지는 NegaZero.dll을 사용했다. 파일은 최대 32개, 개별 target은 최대 256MiB로 제한돼 있다. 배포 자료를 만들 때 이 한도를 확인한다.

## 한 파일에 델타 하나를 쓰는 이유

MSDelta는 특정 원본 bytes에서 특정 결과 bytes를 만드는 차분이다. 원본 검사, 결과 검사, 백업, 복원을 **파일 단위**로 관리하면 실패 원인을 분리하기 쉽다. 기존 패키지는 아카이브·EXE·skin 교체 7개와 DLL·폰트·고지 추가 3개로 총 10개의 대상과 델타가 있었다. 새 파일은 빈 bytes를 source로 사용한다.

배포할 때 ZIP 하나로 묶을 수 있다. 내부 델타 파일이 여러 개라는 사실은 사용자가 각각 실행해야 한다는 의미가 아니다. 단일 EXE에 내장하려면 payload 읽기 계층을 바꾸면 되지만 해시와 복원 단위는 유지하는 편이 이해하기 쉽다.

```python
import sys
sys.path.insert(0, 'repack')
from msdelta import create, invoke
source = b'old synthetic data'
target = b'new synthetic data'
delta = create(source, target)  # 내부에서 apply 후 target과 비교
assert invoke(source, delta, False) == target
```

## 중단 복구와 원본 보존

엔진은 source·payload·target SHA-256을 확인하고 모든 결과를 먼저 stage한 후 교체한다. `.nega0-korean`에 원본 해시 기준 백업, 상태·작업 기록을 보관한다. 중단 후 복원할 수 있도록 상태를 flush한다. 개별 파일 교체를 사용하므로 전체 폴더가 하나의 원자적 트랜잭션이라고 설명하지 않는다.

상대 경로 탈출, 중복 대상, 재분석 지점, 관리 폴더와의 충돌을 거부한다. 복원에서는 추가한 파일을 제거하고 대상 원본을 되돌린다. 세이브/설정은 패치 manifest의 대상에 포함하지 않는다. 게시 전에는 합성 또는 작업용 사본으로 적용→복원과 중단 복구를 확인한다. 코드가 있다고 모든 환경에서 이미 검증됐다고 쓰지 않는다.

## 선택적인 설치 자산 경로 처리

원래 소스에는 완전 설치의 파일 이름·크기 119개를 확인해 로컬 Voice 경로를 우선 사용하는 옵션이 남아 있다. 불완전 설치는 원래 디스크 검색으로 돌아간다. 공개 EXE CLI의 `local_execution`은 기본 false다. `local_assets.h`는 **기존 번역본 크기 목록**이므로 새로 생성한 번역 아카이브 크기와 자동으로 일치하지 않는다. 이 옵션을 재사용하려면 새 결과를 기준으로 목록·검증을 갱신해야 한다. 이 기술 키트는 디스크 이미지나 게임 데이터를 배포하지 않는다.
