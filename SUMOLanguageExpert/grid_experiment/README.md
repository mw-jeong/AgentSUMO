# Grid Text-to-SQL 실험

11x11 그리드 네트워크에서 엣지 제거 시나리오를 예측.
여러 검색 전략에 따라 선택되는 시나리오의 근거와 결과가 어떻게 달라지는지 관찰.

## 데이터

11x11 그리드 네트워크의 220개 엣지에 대해 하나씩 제거하여 시뮬레이션을 돌린 결과가 `experiment_setup/results/`에 준비되어 있음:

- `simulations.db`: Train DB (176개 시나리오)
- `test_44.json`: Test 시나리오 (44개, DB에 없음)
- `ground_truth_test_44.csv`: Test 시나리오의 정답

## 폴더 구조

```
grid_experiment/
├── experiment_setup/             # 시뮬레이션 데이터 생성
│   ├── 01_setup/                 # 네트워크, 트립 생성
│   ├── 02_simulation/            # 시뮬레이션 실행
│   ├── 03_ground_truth/          # 정답 생성
│   ├── data/                     # 생성된 데이터
│   └── results/                  # DB, Ground Truth
├── results/                      # 실험 결과
│   ├── 01_autonomous_conversations/  # 대화 기록
│   ├── 02_neighbor_conversations/
│   ├── 03_cross_conversations/
│   ├── 04_exhaustive_conversations/
│   ├── 01_autonomous_answers.csv     # 각 전략 결과
│   ├── 02_neighbor_answers.csv
│   ├── 03_cross_answers.csv
│   └── 04_exhaustive_answers.csv
├── run_experiment.py             # 전략별 실험 실행
├── print_accuracy.py             # 정확도 출력
└── README.md
```

## 실행 방법

```bash
# 1. run_experiment.py 열어서 SELECTED 리스트 수정
#    원하는 전략만 주석 해제
SELECTED = [
    #"01_autonomous",
    #"02_neighbor",
    #"03_cross",
    "04_exhaustive",  # 실행할 전략
]

# 2. 실험 실행
uv run python SUMOLanguageExpert/grid_experiment/run_experiment.py

# 3. 정확도 출력
uv run python SUMOLanguageExpert/grid_experiment/print_accuracy.py
```

## 전략 종류

| 전략 | 설명 |
|------|------|
| autonomous | LLM이 자율적으로 쿼리 결정 |
| neighbor | 인접 엣지 시나리오 우선 검색 |
| cross | 교차 엣지 시나리오 우선 검색 |
| exhaustive | 전체 시나리오 검색 |

## CSV 형식

`results/{strategy}_answers.csv` 컬럼:

| 컬럼 | 설명 |
|------|------|
| edge_id | 테스트 엣지 ID |
| prompt | LLM에 전달한 전체 프롬프트 |
| response | LLM 최종 응답 |
| ref_count | 응답에서 참고한 시나리오 수 |
| ref_simulations | 참고한 엣지 리스트 (세미콜론 구분) |
| answer | 파싱된 답변 |
| gt_answer | Ground Truth 정답 |
| conversation_file | conversation_history 파일명 |
