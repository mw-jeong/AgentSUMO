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
├── shortest_path_distance/
│   ├── qa_pairs.csv              # 질문-정답 쌍 (30개)
│   ├── run_experiment.py         # 실험 실행 (LLM 응답 수집)
│   ├── evaluate.py               # 정답 파싱 및 정확도 평가
│   └── results/                  # 수집된 응답 CSV
```

## Baselines

| Baseline | 입력 | 설명 |
|----------|------|------|
| **raw** | SUMO `.net.xml` 전문 | LLM이 XML을 직접 읽고 추론 |
| **adj** | 엣지 인접 리스트 (텍스트) | 전처리된 그래프 구조를 텍스트로 제공 |
| **codegen** | XML 파일 경로 + `run_python` 도구 | LLM이 Python 코드를 생성·실행하여 답을 계산 |

## 데이터

`qa_pairs.csv`에 2개 네트워크(grid_11x11, random)에 대한 30개 최단 경로 질문이 포함되어 있다.
거리 난이도별로 3개 bin으로 분류:
- **near**: 1–5 hops
- **medium**: 7–12 hops
- **far**: 13–17 hops

## 실행 방법

### 1. 응답 수집

```bash
# 특정 baseline으로 실험 실행
python shortest_path_distance/run_experiment.py --baseline raw
python shortest_path_distance/run_experiment.py --baseline adj
python shortest_path_distance/run_experiment.py --baseline codegen

# 모델 지정 및 샘플 수 제한
python shortest_path_distance/run_experiment.py --baseline adj --model claude-sonnet-4-6 --n 5
```

### 2. 평가

```bash
# 전체 결과 비교 테이블 출력
python shortest_path_distance/evaluate.py

# 단일 파일 평가
python shortest_path_distance/evaluate.py --input results/adj_responses_claude-sonnet-4-6.csv
```

## 평가 지표

- 거리 bin별(near/medium/far) 및 전체 정확도(exact match)를 출력
- codegen 응답은 JSON trace에서 마지막 assistant 텍스트를 파싱하여 최종 답을 추출
