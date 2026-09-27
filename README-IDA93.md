# IDA 9.3 호환판

공식 Hex-Rays 소스를 바탕으로 만든 비공식 호환판입니다. 공식 지원 버전은 아닙니다.
IDA 실행 파일이나 보고되는 버전은 변경하지 않습니다. 실제 커널 버전은 `9.3`입니다.

## 설치

Git, uv, Python 3.11 이상과 idalib을 사용할 수 있는 IDA 9.3 설치가 필요합니다.
검증 환경은 Windows / IDA Professional 9.3 / Python 3.12입니다.
IDA 실행 파일과 라이선스는 이 저장소에 포함하지 않습니다.

```powershell
git clone --branch compatibility/ida-9.3 https://github.com/dhsgud/ida-mcp-93.git
git clone --branch compatibility/ida-9.3 https://github.com/dhsgud/ida-nexus-93.git
cd ida-mcp-93
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe ..\ida-nexus-93 .
```

**두 로컬 패키지를 함께 설치해야 합니다.** PyPI의 `ida-nexus`나 원본 HCLI
자동 설치 명령을 사용하면 9.4 이상을 요구하는 원본으로 바뀔 수 있습니다.

Codex의 `%USERPROFILE%/.codex/config.toml`에서 다음 예시의 경로를 실제 절대 경로로
바꿔 등록하세요. 기존 `mcp_servers.ida`가 있으면 중복 추가하지 말고 수정하세요.

```toml
[mcp_servers.ida]
command = 'C:\path\to\ida-mcp-93\.venv\Scripts\ida-mcp.exe'
args = ["stdio", "--agent=codex"]
startup_timeout_sec = 120

[mcp_servers.ida.env]
PYTHONUTF8 = "1"
IDADIR = 'C:\Program Files\IDA Professional 9.3'
```

Codex를 재시작하면 적용됩니다. 바이너리 경로를 전달하면 headless worker가
열리므로 IDA GUI를 먼저 열 필요가 없습니다.

## 소스와 검증 환경

- MCP: `../ida-mcp-93`, upstream `d9e415dc88654cbb392802e5c55b3236c090155d`
- Nexus: `../ida-nexus-93`, upstream `c470ed0a2c1671ce8ee5217d0131f4bcd79d58df`
- 두 저장소의 호환 브랜치: `compatibility/ida-9.3`
- Python 3.12, IDA Professional 9.3
- 실행 환경: `ida-mcp-93/.venv`
- 패키지: ida-mcp 20260924.0.3, ida-nexus 0.13.0, ida-domain 0.5.1, idapro 0.0.10
- 일반 패키지 설치를 사용합니다. 소스를 수정하면 재설치해야 합니다.

## 실패 원인과 수정

호출 흐름은 다음과 같습니다.

```text
Codex → MCP(stdio) → DatabaseManager → Nexus HTTP 서버
                                     → IDA 메인 스레드 → IDAPython/디컴파일러
```

원본 Nexus는 `IDA >= 9.4`를 검사하고, headless worker에서
`ida_kernwin.serve()`로 메인 스레드의 요청 큐를 처리합니다.
9.3에는 `serve()`와 `stop_serving()`이 없어 버전 문자열만 위장해도 실패합니다.

수정 사항:

1. `_compat93.py`: Python 표준 라이브러리 `Queue`와 `Future`로 Nexus의 동기 작업을
   IDA 메인 스레드에 전달합니다. 종료 시 대기 중인 요청도 오류로 깨웁니다.
2. `_runtime.py`: 9.3 headless에서는 위 디스패처를 사용합니다. 9.3 미만은 거부하고,
   디스패처 없이 9.3 headless를 시작하는 것도 거부합니다.
3. `cli/worker.py`: 네이티브 serve API가 없을 때 호환 루프를 선택합니다.
   9.4 이상에서 해당 API가 있으면 원래 경로를 유지합니다.
4. 9.3에서는 백그라운드 스레드의 `clr_cancelled()` 호출도 교착되므로,
   취소 플래그 정리는 이미 메인 스레드에서 실행되는 작업 내부에서 처리합니다.
5. GUI 버전 검사와 두 플러그인 매니페스트의 최소 버전을 9.3으로 조정했습니다.
   GUI 자체 이벤트 루프를 사용하는 경로는 유지했습니다.
6. 기존 테스트 하나의 POSIX 경로 가정을 Windows에서도 성립하도록 수정했습니다.

## 검증 결과

- Nexus 일반 테스트: **314 passed, 1 skipped**. 별도 IDA 실기 테스트 18개는 이 명령에서 제외.
- MCP 도구·CLI·메타데이터 테스트: **44 passed**.
- IDA 9.3 실기 테스트: **6 passed**. 복수 클라이언트, 저장 유지, 지연 분석,
  DB 이벤트, Python 타임아웃·취소, 사용자 코드 실패 후 복구를 확인했습니다.
- stdio MCP 통합 테스트: 초기화 → 바이너리 열기 → 분석 → 디컴파일 → 함수명 변경
  → 저장 → 닫기 → 재열기 후 변경 유지 → 마지막 worker 종료까지 통과.
- ELF 샘플: 함수 28개, 첫 함수 의사코드 224자. 작업이 메인 스레드에서 실행됨을 확인.
- Windows `whoami.exe` 복사본: 함수 242개, 분석·저장·종료 통과.
- 변경한 Python 파일의 Ruff 검사와 Git diff 공백 검사 통과.

재현 가능한 MCP 통합 검사:

```powershell
# 이 저장소 폴더에서 실행
.\.venv\Scripts\python.exe .\smoke_test_93.py
```

이 검사는 임시 디렉터리에 샘플을 복사하며, 로그와 DB 경로를 출력합니다.
기존 사용자 DB에는 쓰지 않습니다.

## 제한

- Python 루프의 타임아웃·취소는 검증했습니다. 오래 걸리는 네이티브 호출은
  Python으로 제어가 돌아와야 취소 예외가 적용됩니다. 9.4의 네이티브 취소 동작을
  완전히 재현하지 않습니다.
- 임의의 사용자 스크립트가 별도 스레드에서 직접 `ida_kernwin.execute_sync()`를
  호출하는 경우까지 호환시키지 않습니다. 이 어댑터는 Nexus 내부 작업 전달용입니다.
- 실제 IDA GUI 연동과 실제 9.4 설치 환경은 검증하지 않았습니다.
  현재 설치한 구성은 headless MCP이며 GUI 플러그인은 설치하지 않았습니다.
- 9.4에서 새로 추가된 분석 API가 전부 9.3에 생기는 것은 아닙니다.

## 수정 후 재설치

두 저장소를 현재처럼 같은 부모 폴더에 두고, 이 저장소 폴더에서 실행합니다.
이미 설치한 환경을 업데이트할 때는 다음 명령만 실행하면 됩니다.

```powershell
uv pip install --python .venv\Scripts\python.exe --reinstall --no-deps ..\ida-nexus-93 .
```

Python 3.12의 Windows 로캘 문제 때문에 한글 경로에서 editable(`-e`) 설치는
사용하지 않았습니다. 일반 설치는 이 문제를 피합니다.

## Codex 설정 복구

변경 전에 자신의 `config.toml`을 백업하세요. 복구할 때는 다른 변경을 보존하도록
백업의 `[mcp_servers.ida]` 및 관련 환경변수 블록만 복원하고 Codex를 재시작하세요.
원본 공식 MCP로 돌아갈 경우 IDA 9.4 이상이 필요합니다.
