# AgentSUMO 설치 가이드

## 필수 요구사항

- Python 3.12
- SUMO (Simulation of Urban MObility)
- Claude API 키

---

## 1. SUMO 설치

### macOS
```bash
brew install sumo
```
또는 [Eclipse SUMO 공식 사이트](https://sumo.dlr.de/docs/Downloads.php)에서 다운로드

### Windows
[Eclipse SUMO 공식 사이트](https://sumo.dlr.de/docs/Downloads.php)에서 설치 파일 다운로드

### Linux (Ubuntu/Debian)
```bash
sudo add-apt-repository ppa:sumo/stable
sudo apt-get update
sudo apt-get install sumo sumo-tools sumo-doc
```

---

## 2. Python 환경 설정

### uv 설치
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 가상환경 생성 및 의존성 설치
```bash
cd AgentSUMO

# 가상환경 생성 (Python 3.12)
uv venv --python 3.12

# 가상환경 활성화
# macOS/Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# 의존성 설치
uv pip install -e .
```

---

## 3. 설정 파일 생성

프로젝트 루트(`AgentSUMO/`)에 다음 파일들을 생성하세요:

### claude_api.txt (필수)
```
sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```
[Anthropic Console](https://console.anthropic.com/)에서 API 키 발급

### sumo_home.txt (필수)
SUMO 설치 경로 입력:

**macOS (Homebrew):**
```
/opt/homebrew/share/sumo
```

**macOS (Eclipse SUMO):**
```
/Library/Frameworks/EclipseSUMO.framework/Versions/1.24.0/EclipseSUMO
```

**Windows:**
```
C:\Program Files (x86)\Eclipse\Sumo
```

**Linux:**
```
/usr/share/sumo
```

### mapbox_token.txt (선택)
```
pk.eyJ1Ijoixxxxxxxxxxxxxxxxxx
```
[Mapbox](https://www.mapbox.com/)에서 토큰 발급 (없어도 기본 토큰으로 작동)

---

## 4. 실행

### 웹 인터페이스
```bash
python web.py
```
브라우저에서 http://localhost:8000 접속

### CLI 모드
```bash
python chat.py
```

### Output 정리
```bash
python clean.py
```

---

## 문제 해결

### SUMO 경로 오류
`sumo_home.txt`의 경로 확인. 해당 경로에 `bin/sumo` (또는 `bin/sumo.exe`)가 있어야 함.

### API 키 오류
`claude_api.txt` 파일이 프로젝트 루트에 있고, 키가 올바른지 확인.

### 의존성 오류
```bash
uv pip install -e . --upgrade
```
