# IPP Ablation — Full Report

## 1. Experiment Design

### Research Question

Interactive Planning Protocol (IPP) — 시스템 프롬프트에 내장된 구조화된 추론 프로토콜 — 이 LLM 기반 교통 시뮬레이션 시나리오 설계 및 실행 품질을 향상시키는가?

### IPP 구성 요소

IPP는 AgentSUMO의 시스템 프롬프트에 통합된 세 가지 구성 요소로 이루어진다:

1. **Task Complexity Assessment**: 에이전트가 사용자 요청을 세 가지로 분류:
   - *Simple*: 단일 tool call로 답할 수 있는 직접적 질의
   - *Complex*: 정책 비교나 파라미터 탐색이 필요한 다단계 작업
   - *Agentic*: 중간 평가가 포함된 다단계 추론이 필요한 개방형 작업

   에이전트는 분류에 따라 추론 깊이를 조절 — Complex에는 `<thinking>`, Agentic에는 `<extended_thinking>` 사용.

2. **Parameter Sufficiency Validation**: 실행 전에 필요한 파라미터가 모두 지정되었는지 확인. 빠지거나 모호한 것(예: 네트워크 반경, 교통 조건, 정책 세부사항)이 있으면 기본값을 가정하지 않고 사용자에게 확인.

3. **Clarify-before-Execute**: 실행 계획(수행할 단계와 호출할 tool 목록)을 제시하고, 사용자 확인을 받은 후 tool 실행 시작.

### Conditions

| Condition | System Prompt | IPP Sections | 에이전트 행동 |
|-----------|--------------|:---:|----------------|
| **Full (IPP)** | `unified_system.md` | 포함 | complexity 평가, 빠진 파라미터 확인, 계획 제시, 사용자 확인 대기 |
| **No IPP** | `unified_system_no_ipp.md` | 제거 | 요청 수신 → 즉시 파라미터 자체 선택 → 실행 |

No IPP 프롬프트는 Full 프롬프트의 정확한 복사본에서 IPP 관련 섹션만 제거한 것. 나머지 모든 내용(tool 설명, 응답 형식, 도메인 지식)은 동일.

### Model

Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)

---

## 2. Scenario Design

### Scenarios

| ID | Prompt | Complexity | 확인이 필요한 주요 파라미터 |
|----|--------|:---:|--------------------------|
| **s1** | "How congested is the traffic around Gangnam Station?" | Simple | radius, traffic condition, duration |
| **s2** | "What would be the impact of lane closure on Teheran-ro near Gangnam Station?" | Complex | radius, traffic condition, 감소 차선 수, 대상 구간 |
| **s3** | "How would increasing the EV ratio affect air quality near Gangnam Station?" | Complex | radius, traffic condition, baseline vs policy EV 비율 |
| **s4** | "After an event at Gangnam Station, traffic spreads in all directions. Find where congestion builds and how to clear it faster." | Agentic | radius, traffic condition, 혼잡 식별 전략, 정책 선택 |

### 시나리오 선정 기준

- **s1**: Simple — 기본적인 빠진 파라미터에 대해서도 IPP가 물어보는지 테스트
- **s2**: Complex, 부분 명시 — "Teheran-ro"는 명시되었지만 차선 수, 교통량, 반경은 미지정
- **s3**: Complex, 모호한 파라미터 — "increasing the EV ratio"이지만 몇 %로인지 미지정
- **s4**: Agentic — 다단계 분석(시뮬 → 혼잡 식별 → 정책 제안 → 평가) 필요, 전략 선택에서 사용자 협력 테스트

### 반복

각 시나리오 × condition을 **5회 반복**하여 일관성 측정:
- 4 시나리오 × 2 conditions × 5 iterations = **총 40 sessions**
- 모든 세션은 `chat_ablation.py`를 통한 수동 대화

---

## 3. Ablation Procedure

### Full (IPP)

1. 에이전트가 사용자 프롬프트 수신
2. Task complexity 평가
3. 빠진 파라미터 식별 후 사용자에게 확인
4. 사용자가 사전 정의된 값으로 응답 (iteration 간 일관)
5. 실행 계획 제시
6. 사용자 확인
7. Tool 실행 및 결과 제시

### No IPP

1. 에이전트가 사용자 프롬프트 수신
2. 즉시 파라미터 선택 후 tool 실행
3. 결과 제시
4. (확인 없음, 계획 제시 없음, 사용자 확인 없음)

### 사용자 행동

Full (IPP) 세션에서 에이전트가 확인 질문을 하면, 사용자는 사전 정의된 값으로 일관되게 답변. 사용자가 먼저 파라미터를 제시하지 않음 — 에이전트가 물어볼 때만 답변.

No IPP 세션에서는 사용자가 첫 프롬프트만 제공하고 개입하지 않음.

---

## 4. Evaluation Methodology

### Conversational G-Eval

**DeepEval** 프레임워크의 **Conversational G-Eval** 사용 — 개별 응답이 아닌 전체 multi-turn 대화를 평가하도록 설계된 G-Eval 변형. "NLG Evaluation using GPT-4 with Better Human Alignment" (Liu et al.) 기반으로, chain-of-thought 프롬프팅으로 evaluation steps를 생성한 후 LLM 토큰 확률 정규화로 0-1 점수 산출.

**Judge model**: GPT-4o

**입력**: 전체 대화 이력(모든 user/assistant 턴, tool call 및 결과 포함)을 `ConversationalTestCase`의 `Turn` 객체로 전달. Judge가 전체 상호작용을 한번에 평가.

### 세 가지 커스텀 메트릭

**SimulationQuality** — 최종 시뮬레이션이 사용자 의도를 반영하는가?
```
evaluation_steps:
1. Check if the final simulation scenario accurately reflects the user's original intent
2. Check if the agent completed the task efficiently without redundant or unnecessary steps
3. Check if the agent chose appropriate simulation parameters (radius, traffic condition, duration) for the given scenario
```

**PlanningQuality** — 에이전트가 실행 전에 계획했는가?
```
evaluation_steps:
1. Check if the agent assessed the complexity of the task and adapted its reasoning depth accordingly
2. Check if the agent asked the user about missing or ambiguous parameters
3. Check if the agent waited for user confirmation before proceeding with execution
```

**InteractiveEngagement** — 에이전트가 사용자와 협력했는가?
```
evaluation_steps:
1. Check if the agent presented an execution plan before calling any tools
2. Check if the agent collaborated with the user to build the simulation scenario together
3. Check if the agent incorporated user feedback into its execution
4. Check if the agent engaged interactively with the user rather than making unilateral decisions
```

---

## 5. Results

### Table 1: Conversational G-Eval Aggregate (condition당 20 sessions)

| Metric | Full (IPP) | No IPP | Delta |
|--------|:---:|:---:|:---:|
| **SimulationQuality** | **1.00** | 0.96 | +0.04 |
| **PlanningQuality** | **0.98** | 0.45 | **+0.53** |
| **InteractiveEngagement** | **0.98** | 0.50 | **+0.48** |

### Table 2: Conversational G-Eval Per-Scenario Breakdown

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

---

## 6. Detailed Results by Scenario

### s1 — "How congested is the traffic around Gangnam Station?"

| Iteration | Full SQ | Full PQ | Full IE | No IPP SQ | No IPP PQ | No IPP IE |
|:---------:|:-------:|:-------:|:-------:|:---------:|:---------:|:---------:|
| 1 | 1.00 | 1.00 | 0.99 | 0.99 | 0.34 | 0.40 |
| 2 | 1.00 | 1.00 | 0.93 | 0.90 | 0.37 | 0.33 |
| 3 | 1.00 | 1.00 | 1.00 | 0.96 | 0.37 | 0.53 |
| 4 | 1.00 | 1.00 | 1.00 | 0.91 | 0.44 | 0.40 |
| 5 | 1.00 | 1.00 | 0.91 | 0.96 | 0.48 | 0.39 |
| **avg** | **1.00** | **1.00** | **0.96** | **0.94** | **0.40** | **0.41** |

### s2 — "What would be the impact of lane closure on Teheran-ro near Gangnam Station?"

| Iteration | Full SQ | Full PQ | Full IE | No IPP SQ | No IPP PQ | No IPP IE |
|:---------:|:-------:|:-------:|:-------:|:---------:|:---------:|:---------:|
| 1 | 1.00 | 1.00 | 1.00 | 0.90 | 0.38 | 0.44 |
| 2 | 1.00 | 1.00 | 0.97 | 1.00 | 0.52 | 0.50 |
| 3 | 1.00 | 1.00 | 1.00 | 0.90 | 0.43 | 0.51 |
| 4 | 1.00 | 1.00 | 1.00 | 0.91 | 0.45 | 0.58 |
| 5 | 1.00 | 1.00 | 0.99 | 1.00 | 0.33 | 0.59 |
| **avg** | **1.00** | **1.00** | **0.99** | **0.94** | **0.42** | **0.52** |

### s3 — "How would increasing the EV ratio affect air quality near Gangnam Station?"

| Iteration | Full SQ | Full PQ | Full IE | No IPP SQ | No IPP PQ | No IPP IE |
|:---------:|:-------:|:-------:|:-------:|:---------:|:---------:|:---------:|
| 1 | 1.00 | 1.00 | 1.00 | 0.90 | 0.32 | 0.47 |
| 2 | 1.00 | 0.98 | 1.00 | 1.00 | 0.42 | 0.49 |
| 3 | 0.99 | 0.90 | 1.00 | 0.92 | 0.39 | 0.53 |
| 4 | 1.00 | 1.00 | 1.00 | 0.97 | 0.40 | 0.44 |
| 5 | 1.00 | 0.90 | 1.00 | 0.99 | 0.44 | 0.42 |
| **avg** | **1.00** | **0.95** | **1.00** | **0.96** | **0.39** | **0.47** |

### s4 — "After an event at Gangnam Station, traffic spreads in all directions..."

| Iteration | Full SQ | Full PQ | Full IE | No IPP SQ | No IPP PQ | No IPP IE |
|:---------:|:-------:|:-------:|:-------:|:---------:|:---------:|:---------:|
| 1 | 1.00 | 1.00 | 1.00 | 1.00 | 0.50 | 0.44 |
| 2 | 1.00 | 1.00 | 1.00 | 1.00 | 0.57 | 0.61 |
| 3 | 0.98 | 1.00 | 1.00 | 1.00 | 0.56 | 0.54 |
| 4 | 1.00 | 0.91 | 0.91 | 1.00 | 0.65 | 0.58 |
| 5 | 1.00 | 1.00 | 1.00 | 0.98 | 0.70 | 0.87 |
| **avg** | **1.00** | **0.98** | **0.98** | **1.00** | **0.59** | **0.61** |

---

## 7. Analysis

### IPP의 핵심 효과: Output Quality가 아닌 Process Quality

가장 주목할 발견은 SimulationQuality (작은 delta: +0.04)와 PlanningQuality/InteractiveEngagement (큰 delta: +0.53, +0.48)의 대비이다:

- **IPP 유무와 관계없이, 에이전트는 합리적인 시뮬레이션을 실행한다.** 적절한 tool을 선택하고, 올바른 순서로 실행하며, 해석 가능한 결과를 생성한다.
- **차이는 시뮬레이션을 어떻게(HOW) 설계하느냐에 있다.** IPP가 있으면 에이전트는 파라미터에 대해 사용자와 상의하고, 계획을 제시하고, 확인을 기다린다. IPP 없이는 모든 결정을 독단적으로 내린다.

### SimulationQuality 차이가 작은 이유

LLM은 본질적으로 합리적인 파라미터를 선택할 수 있다. "How congested is the traffic around Gangnam Station?"이라는 질문에 `radius=1.0km, traffic=medium, duration=3600s`를 선택하는 것은 합리적인 기본값이며 — GPT-4o judge도 높게 평가한다. 문제는 사용자가 이러한 선택에 대해 발언권이 없었다는 것이다.

### s4에서 Delta가 가장 작은 이유

s4 (Agentic)에서 No IPP의 PlanningQuality가 0.59 (s1-s3의 0.39-0.42 대비 높음). 복잡한 다단계 특성이 에이전트로 하여금 자연스럽게 더 신중하게 계획하도록 만든다 — 혼잡 지점 식별, 정책 선택, 비교 시뮬레이션 실행. 그러나 s4에서도 에이전트는 여전히 사용자에게 어떤 정책을 시도할지 물어보지 않는다 (InteractiveEngagement: 0.61 vs 0.98).

### IPP 없이 파라미터가 사용자 의도와 달라지는 사례

모든 시나리오에서 No IPP 에이전트는 일관적으로 `traffic_condition=medium`을 선택했다 (19/20 sessions). 사용자의 의도한 시나리오는 `heavy` 교통이었다. medium은 합리적인 기본값이지만, 사용자가 원한 것과 일치하지 않는다. IPP는 명시적으로 확인함으로써 이를 방지한다.

s3 (EV ratio)에서 No IPP 에이전트는 iteration마다 다른 EV 비율을 선택했다: 0.5, 0.7, 0.5, 0.8, 0.5. Full 세션에서 사용자가 지정한 값은 0.2였다. IPP 없이는 사용자가 이 핵심 파라미터를 지정할 기회가 없었다.

### s2에서 반대 결론이 도출된 사례

가장 주목할 사례: Full(heavy 교통)에서는 테헤란로 차선 감소가 **부정적 영향** (이동 시간 +1.3%, 대기 시간 +1.5%), No IPP(medium 교통)에서는 오히려 **긍정적 영향** (이동 시간 -1.5%, 대기 시간 -2.1%). 동일한 정책이 교통량 설정에 따라 반대 결론을 도출 — IPP의 파라미터 확인이 분석 결과의 방향 자체를 바꿀 수 있음을 보여준다.

### Clarification Rate

- **Full (IPP)**: 20/20 sessions (100%)에서 최소 1회 확인 교환 발생
- **No IPP**: 1/20 sessions (5%) — s4/iteration5에서만 2번째 턴 발생, 그마저도 확인이 아닌 후속 질문

---

## 8. Supplementary: Direct Metrics

| Metric | Full (IPP) | No IPP | Delta |
|--------|:---:|:---:|:---:|
| Conversation turns | 3 ± 1 | 1 ± 0 | +2 |
| Total tokens | 74,900 ± 50,750 | 55,899 ± 41,846 | +19,001 |
| Tool calls | 11 ± 4 | 11 ± 3 | 0 |
| Clarification rate | 100% | 5% | +95% |

IPP는 세션당 약 1-2회의 확인 턴과 ~19K 토큰을 추가한다. Tool call 수는 동일 — IPP는 사용된 tool의 수가 아니라, 무엇을 실행할지 결정하는 프로세스만 변화시킨다.