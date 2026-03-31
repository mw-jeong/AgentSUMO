# SQLite Ablation — Summary

## Background

AgentSUMO는 SUMO 시뮬레이션 출력(XML)을 SQLite DB로 변환하여 LLM이 SQL 쿼리로 분석할 수 있게 한다. 기존 논문(TRC 제출본)은 프레임워크의 정성적 쇼케이스만 포함하여, 정량적 평가를 하고자 한다.

이 실험은 **SQLite DB 기반 데이터 관리가 LLM의 시뮬레이션 결과 분석 정확도에 얼마나 기여하는지**를 정량적으로 입증하기 위한 ablation study이다.

## Question

SUMO 시뮬레이션 실행 후, 출력 데이터의 관리 방식이 LLM의 결과 분석 정확도에 어떤 영향을 미치는가?

- **No Data**: 시뮬레이션은 돌렸지만 출력 데이터에 대한 관리/접근 체계가 없는 상태
- **XML Only**: 출력 XML 파일은 있지만 raw 상태로 방치 — LLM이 파일을 직접 읽고 파싱해야 함
- **Full (SQLite)**: 출력을 structured DB로 변환 — LLM이 SQL 쿼리로 정확하게 분석

## Setup

- **Model**: Claude Sonnet 4.5 (1M context)
- **Networks**: Gangnam Station (Seoul), Times Square (NYC) — 0.3 km radius, random congested traffic, 1 hour
- **Scenarios**: Baseline, Webster TLS adaptation, Green Wave TLS offset (각 네트워크당 3개 시뮬레이션)
- **20 benchmark questions** across 4 difficulty levels (L1-L4)
- **Evaluation**: exact match with 5% relative tolerance (numeric), exact string match (judgment)

### Question Levels
- **L1 (5)**: Single-simulation retrieval — 단일 시뮬레이션에서 값 하나 조회
- **L2 (5)**: Single-simulation aggregation — 단일 시뮬레이션에서 집계, 비율 계산
- **L3 (5)**: Multi-simulation comparison — 시나리오 간 수치 비교
- **L4 (5)**: Multi-simulation judgment — 시나리오 간 binary 판단 (e.g., webster or greenwave)

### Conditions Detail
| Condition | Data Access | Tools |
|-----------|------------|-------|
| **Full** | SQLite DB | `read_query` (SQLite MCP) |
| **XML Only** | Raw XML files | `read_file`, `list_directory` 등 (Filesystem MCP) |
| **No Data** | 없음 | 없음 |

## Results

### Accuracy

| | Full (SQLite) | XML Only | No Data |
|---|:---:|:---:|:---:|
| Gangnam | **19/20 (95%)** | 13/20 (65%) | 3/20 (15%) |
| Times Square | **19/20 (95%)** | 12/20 (60%) | 3/20 (15%) |
| **Total** | **38/40 (95%)** | 25/40 (63%) | 6/40 (15%) |

### Accuracy by Level

| Level | Full | XML Only | No Data |
|-------|:----:|:--------:|:-------:|
| L1 — Retrieval (10) | **100%** | 50% | 0% |
| L2 — Aggregation (10) | **100%** | 80% | 0% |
| L3 — Comparison (10) | **90%** | 50% | 0% |
| L4 — Judgment (10) | **90%** | 70% | 60% |

### Cost

| | Full | XML Only | No Data |
|---|---:|---:|---:|
| Tokens / session | 151K | 1,208K (**8x**) | 23K |
| Latency | **154s** | 553s (3.6x) | 164s |
| Tokens / correct answer | **3,987** | 48,334 | 3,907 |

## Key Findings

1. **Structured DB가 필수**: Full (SQLite)은 95% 정확도. DB 없이는 시뮬레이션을 돌려도 정확한 분석 불가능 (No Data 15%, XML Only 63%)

2. **Raw XML은 비용 대비 비효율**: XML Only는 8배 토큰을 쓰면서 63%에 그침. LLM이 XML을 컨텍스트에 넣고 수동으로 파싱/계산하면서 산술 오류 발생

3. **데이터 없이는 판단만 가능**: No Data는 L1-L3 (수치 질문) 0%, L4 (판단 질문) 60%. 일반 도메인 지식으로 "Webster vs Green Wave" 방향은 맞추지만 구체적 수치는 불가능

4. **확장성**: 실제 규모 네트워크(5K+ 차량)에서는 XML 파일이 LLM 컨텍스트 윈도우를 초과하여 XML Only 자체가 불가능. SQLite는 쿼리 결과만 반환하므로 데이터 규모에 무관

## Implications for Paper

- AgentSUMO의 XML→SQLite 파이프라인이 단순한 편의 기능이 아니라, LLM 기반 시뮬레이션 분석의 정확도를 결정하는 핵심 설계임을 정량적으로 입증
- "시뮬레이션 실행 후 출력 데이터의 체계적 관리 없이는 LLM이 정확한 분석을 수행할 수 없다"는 메시지