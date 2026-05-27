# AgentSUMO

[![Docs](https://readthedocs.org/projects/agentsumo/badge/?version=latest)](https://agentsumo.readthedocs.io/en/latest/?badge=latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)

AI-Powered SUMO Traffic Simulation Platform

Claude LLM과 Model Context Protocol(MCP)을 결합한 대화형 교통 시뮬레이션 자동화 플랫폼

**[Documentation](https://agentsumo.readthedocs.io)** ·
[Installation](https://agentsumo.readthedocs.io/en/latest/installation.html) ·
[Tools](https://agentsumo.readthedocs.io/en/latest/mcp_servers/agentsumo/index.html) ·
[Schema](https://agentsumo.readthedocs.io/en/latest/database/index.html) ·
[Tutorials](https://agentsumo.readthedocs.io/en/latest/tutorials/index.html)

## 개요

AgentSUMO는 자연어로 교통 시뮬레이션을 제어할 수 있는 AI 에이전트입니다.

- 대화형 인터페이스로 시뮬레이션 설정 및 실행
- 도로 차단, 신호 최적화 등 정책 실험
- 시뮬레이션 결과 분석 및 비교

## 아키텍처

```
User (자연어 입력)
    |
    v
AgentSUMO (Claude LLM)
    |
    +---> SUMO MCP Client ---> SUMO MCP Server ---> SUMO Tools
    |
    +---> SQLite MCP Client ---> SQLite MCP Server ---> DB
```

## 프로젝트 구조

```
AgentSUMO/
├── agentsumo/
│   ├── agent/           # AI Agent (Claude orchestrator)
│   ├── client/          # MCP Client (SUMO, SQLite)
│   ├── server/          # SUMO MCP Server
│   │   ├── baseline/    # 네트워크/트립 생성, 시뮬레이션 실행
│   │   ├── customization/  # 도로 편집, 신호 제어
│   │   ├── analysis/    # 결과 분석, 리포트 생성
│   │   └── visualization/  # 시각화
│   └── core/            # 설정
├── web/                 # 웹 인터페이스
├── sqlite-mcp-server/   # SQLite MCP Server
├── chat.py              # CLI 실행
├── web.py               # 웹 서버 실행
└── clean.py             # Output 정리
```

## 주요 기능

### 시뮬레이션 기본
- 네트워크 생성 (OpenStreetMap 기반)
- 트립 생성 (RandomOD / RealOD)
- 시뮬레이션 실행

### 정책 실험
- 도로 차단
- 차선 축소
- 신호 오프셋 최적화
- 신호 주기 적응

### 결과 분석
- SQL 쿼리 기반 상세 분석
- 시나리오 비교
- HTML 리포트 생성

## Documentation

전체 문서는 **[agentsumo.readthedocs.io](https://agentsumo.readthedocs.io)** 에서 확인하실 수 있습니다.

- [Installation](https://agentsumo.readthedocs.io/en/latest/installation.html) — SUMO, Python 3.12, 환경 설정
- [Tools](https://agentsumo.readthedocs.io/en/latest/mcp_servers/agentsumo/index.html) — 24개 도구 상세 reference
- [Schema](https://agentsumo.readthedocs.io/en/latest/database/index.html) — `simulations.db` ER 다이어그램과 컬럼 표
- [Tutorials](https://agentsumo.readthedocs.io/en/latest/tutorials/index.html) — 페이퍼 케이스 스터디 walkthrough

## 빠른 시작

```bash
# 1. 의존성 설치
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .

# 2. 설정 파일 생성
echo "your-api-key" > claude_api.txt
echo "/path/to/sumo" > sumo_home.txt

# 3. 실행
# 웹
python web.py
uv run web.py
# cli
python chat.py
uv run chat.py
```

자세한 설치 방법은 [INSTALL.md](INSTALL.md) 참조

## 요구사항

- Python 3.12
- SUMO 1.24+
- Claude API 키

## 라이선스

MIT License
