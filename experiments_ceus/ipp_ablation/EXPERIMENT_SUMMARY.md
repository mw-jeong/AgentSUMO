# IPP Ablation — Summary

## Background

AgentSUMO는 시스템 프롬프트에 Interactive Planning Protocol (IPP)을 내장하여, LLM 에이전트가 시뮬레이션 실행 전에 구조화된 추론을 거치도록 한다. IPP는 세 가지 구성 요소로 이루어져 있다:

1. **Task Complexity Assessment** — 사용자 요청을 Simple/Complex/Agentic으로 분류하고 추론 깊이를 조절
2. **Parameter Sufficiency Validation** — 빠지거나 모호한 파라미터를 식별하고, 가정하지 않고 사용자에게 확인
3. **Clarify-before-Execute** — 실행 계획을 먼저 제시하고 사용자 확인을 받은 후 tool 호출

이 실험은 논문 재투고(TRC)를 위한 정량적 평가로, IPP가 시스템 프롬프트에 있는 것과 없는 것이 LLM의 시뮬레이션 시나리오 설계 품질에 어떤 차이를 만드는지를 검증한다.

구체적으로:
- **IPP 있을 때**: 사용자에게 빠진 파라미터를 물어보고, 계획을 세우고, 확인받은 뒤 실행
- **IPP 없을 때**: 사용자 요청을 받으면 바로 실행 (파라미터 임의 추정, 계획 없이)

## Question

측정할 수 있는 것:
- 사용자에게 확인 질문을 했는가
- 파라미터를 임의로 가정했는가
- 실행 계획을 먼저 제시했는가
- 최종 시뮬레이션이 사용자 의도에 맞았는가

## Setup

- **Model**: Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)
- **Location**: Gangnam Station, Seoul
- **4 scenarios** (난이도별):
  - s1 (Simple): "How congested is the traffic around Gangnam Station?"
  - s2 (Complex): "What would be the impact of lane closure on Teheran-ro near Gangnam Station?"
  - s3 (Complex): "How would increasing the EV ratio affect air quality near Gangnam Station?"
  - s4 (Agentic): "After an event at Gangnam Station, traffic spreads in all directions. Find where congestion builds and how to clear it faster."
- **2 conditions**:
  - **Full (IPP)**: 시스템 프롬프트에 IPP 포함 (`unified_system.md`)
  - **No IPP**: IPP 섹션만 제거, 나머지 동일 (`unified_system_no_ipp.md`)
- **5 iterations** per scenario per condition (총 40 sessions)
- **수동 대화**: 사용자가 첫 프롬프트 제공, Full condition에서는 에이전트의 확인 질문에 사전 정의된 의도대로 답변

### Evaluation

IPP ablation은 GT(정답)가 존재하지 않는 행동 품질 평가이므로, 두 가지 접근을 병행한다:

- **정량적 평가**: Conversational G-Eval (LLM-as-judge)로 전체 대화를 커스텀 criteria에 따라 채점
- **정성적 평가**: Full vs No IPP 대표 대화 로그를 나란히 비교하여, IPP가 에이전트 행동에 미치는 구체적 차이를 보여줌

**Conversational G-Eval** (DeepEval 프레임워크, GPT-4o as judge):
- 전체 multi-turn 대화를 한번에 평가하는 LLM-as-judge 메트릭
- "NLG Evaluation using GPT-4 with Better Human Alignment" (Liu et al.) 기반

세 가지 커스텀 메트릭:

| Metric | 평가 기준 |
|--------|---------|
| **SimulationQuality** | 시뮬레이션이 사용자 의도를 반영하는가? 효율적으로 완수했는가? 적절한 파라미터를 선택했는가? |
| **PlanningQuality** | task complexity를 평가했는가? 빠진 파라미터를 물어봤는가? 확인을 기다렸는가? |
| **InteractiveEngagement** | 실행 전 계획을 제시했는가? 사용자와 협력했는가? 피드백을 반영했는가? interactive하게 진행했는가? |

## Results

### Conversational G-Eval (Aggregate)

| Metric | Full (IPP) | No IPP | Delta |
|--------|:---:|:---:|:---:|
| **SimulationQuality** | **1.00** | 0.96 | +0.04 |
| **PlanningQuality** | **0.98** | 0.45 | **+0.53** |
| **InteractiveEngagement** | **0.98** | 0.50 | **+0.48** |

### Conversational G-Eval (Per-Scenario)

| Scenario | Metric | Full | No IPP | Delta |
|----------|--------|:---:|:---:|:---:|
| **s1** (Simple) | SimulationQuality | 1.00 | 0.94 | +0.06 |
| | PlanningQuality | 1.00 | 0.40 | **+0.60** |
| | InteractiveEngagement | 0.96 | 0.41 | **+0.55** |
| **s2** (Complex) | SimulationQuality | 1.00 | 0.94 | +0.06 |
| | PlanningQuality | 1.00 | 0.42 | **+0.58** |
| | InteractiveEngagement | 0.99 | 0.52 | **+0.47** |
| **s3** (Complex) | SimulationQuality | 1.00 | 0.96 | +0.04 |
| | PlanningQuality | 0.95 | 0.39 | **+0.56** |
| | InteractiveEngagement | 1.00 | 0.47 | **+0.53** |
| **s4** (Agentic) | SimulationQuality | 1.00 | 1.00 | +0.00 |
| | PlanningQuality | 0.98 | 0.59 | **+0.39** |
| | InteractiveEngagement | 0.98 | 0.61 | **+0.37** |

## Key Findings

1. **IPP는 Planning과 Interaction 품질을 극적으로 향상시킨다**: PlanningQuality (+0.53)와 InteractiveEngagement (+0.48)에서 가장 큰 차이. IPP의 핵심 가치는 최종 결과가 아니라 추론 프로세스에 있다.

2. **SimulationQuality는 IPP 유무에 거의 차이 없다** (+0.04): 에이전트는 어느 조건에서든 합리적인 시뮬레이션을 실행한다 — 하지만 IPP 없이는 사용자에게 확인 없이 파라미터를 임의로 결정한다.

3. **IPP 없이는 에이전트가 거의 물어보지 않는다**: No IPP 20회 중 19회에서 단일 턴으로 전체 시뮬레이션을 실행. IPP가 있으면 100% clarification 발생.

4. **파라미터 가정이 사용자 의도와 다르다**: No IPP에서 에이전트는 19/20회에서 `traffic_condition=medium`을 선택했지만 사용자 의도는 `heavy`. s3에서 EV ratio가 iteration마다 0.5, 0.7, 0.8으로 변동 — 사용자가 지정하지 않은 값.

5. **s2에서 반대 결론이 도출됨**: Full(heavy 교통)에서는 차선 감소가 부정적 영향, No IPP(medium 교통)에서는 오히려 긍정적 영향. 동일한 정책이 교통량 설정에 따라 반대 결론 — IPP의 파라미터 확인이 결과의 방향 자체를 바꿀 수 있음.

## Implications for Paper

- IPP는 단순한 프롬프트 엔지니어링이 아니라, 에이전트가 사용자와 상호작용하는 방식을 구조적으로 변화시키는 추론 프로토콜
- IPP의 핵심 기여는 **output quality가 아니라 process quality**: 시뮬레이션은 어느 쪽이든 완수되지만, IPP가 있어야 사용자 의도를 반영한 시나리오가 설계됨
- IPP 없이는 에이전트의 파라미터 선택이 합리적이지만 임의적 — 사용자가 실행 전에 검증하거나 수정할 기회가 없음