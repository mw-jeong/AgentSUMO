# NetTrafficQA

LLM의 교통 네트워크 그래프 추론 능력을 평가하는 벤치마크 프레임워크.
SUMO 네트워크에서 최단 경로 거리(hop 수)를 질문하고, 다양한 네트워크 표현 방식(baseline)에 따른 LLM 정확도를 비교한다.

## 구조

```
NetTrafficQA_/
├── scripts/
│   ├── utils.py                  # 공통 유틸 (API 클라이언트, 네트워크 로딩)
│   └── methods/
│       ├── raw.py                # Baseline 1: Raw XML 전체를 컨텍스트로 제공
│       ├── adj.py                # Baseline 2: 인접 리스트(텍스트)를 제공
│       └── codegen.py            # Baseline 3: XML 경로 + run_python 도구 제공 
├── QAdataset/
│   ├── feature_retrieval         # questions/ 에 {network}_{type}.csv 파일들
│   ├── pathfinding               # questions/ 에 {network}_{type}.csv 파일들
│   └── network_comprehension     # questions/ 에 {network}_{type}.csv 파일들
├── run_experiment.py             # 실험 실행 (LLM 응답 수집)
├── evaluate.py                   # 정답 파싱 및 정확도 평가
└── generate_qa.py                # QA 데이터셋 생성 스크립트
```

## Baselines

| Baseline | 입력 | 설명 |
|----------|------|------|
| **raw** | SUMO `.net.xml` 전문 | LLM이 XML을 직접 읽고 추론 |
| **adj** | 엣지 인접 리스트 (텍스트) | 전처리된 그래프 구조를 텍스트로 제공 |
| **codegen** | XML 파일 경로 + `run_python` 도구 | LLM이 Python 코드를 생성·실행하여 답을 계산 |

## 데이터 (QAdataset)

데이터셋은 세 가지 카테고리로 구성되며, 각 카테고리 내 `questions/` 폴더에 네트워크별 개별 CSV 파일로 저장된다.

- **feature_retrieval**: 엣지/노드 속성 (junction id, coordinates, lanes, types 등)
- **pathfinding**: 경로 추론 (next/prev edges, shortest path edges/sequence, distance by length)
- **network_comprehension**: 네트워크 전체 특성 (lane changes, highways, source/sink, O-D pairs)

## 실행 방법

### 1. QA 데이터셋 생성

실험에 필요한 질문을 새로 생성하거나 질문 수를 조정할 수 있다.

```bash
# 전체 네트워크/카테고리에 대해 질문 생성 (기본 10개씩)
python generate_qa.py --n 10

# 특정 카테고리만 20개씩 생성
python generate_qa.py --category feature_retrieval --n 20
```

### 2. 응답 수집

```bash
# 특정 task 및 baseline으로 실행 (전체 네트워크)
python run_experiment.py --task QAdataset/feature_retrieval --baseline adj

# 특정 네트워크만 실행
python run_experiment.py --task QAdataset/feature_retrieval --baseline adj --network grid_11x11
```

### 3. 평가

다양한 필터를 사용하여 특정 네트워크, 베이스라인, 또는 질문 유형에 대해 평가할 수 있다.

```bash
# 전체 결과 통합 평가 (QAdataset 하위 모든 결과 검색)
python evaluate.py --task QAdataset

# 특정 베이스라인 및 카테고리만 필터링하여 평가
python evaluate.py --task QAdataset --baseline adj --type pathfinding

# 필터링 및 그룹핑: [baseline | network | type | model] 순서로 요약 리포트 제공
python evaluate.py --task QAdataset --network grid_11x11

# 단일 파일 상세 평가
python evaluate.py --task QAdataset/feature_retrieval --input QAdataset/feature_retrieval/results/adj_responses_grid_11x11_from_junction_n10_claude.csv
```

## 평가 지표

- 거리 bin별(near/medium/far) 및 전체 정확도(exact match)를 출력
- codegen 응답은 JSON trace에서 마지막 assistant 텍스트를 파싱하여 최종 답을 추출
