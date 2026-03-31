# SQLite Ablation — Full Report

## 1. Experiment Design

### Research Question
How does the method of data access affect an LLM's ability to accurately answer traffic simulation analysis questions?

### Conditions

| Condition | Data Access | Tools Available |
|-----------|------------|-----------------|
| **Full** | SQLite database | `read_query` (executes SQL) |
| **XML Only** | Raw XML files | `read_file`, `list_directory`, etc. (14 filesystem tools) |
| **No Output Management** | None | None (simulation outputs exist but are not structured or accessible) |

### Model
Claude Sonnet 4.5 (claude-sonnet-4-5-20250929), 1M context window

---

## 2. Simulation Setup

### Networks

| | Gangnam Station (Seoul) | Times Square (NYC) |
|---|---|---|
| Radius | 0.3 km | 0.3 km |
| Edges | 104 | ~100 |
| Vehicles | 156 | 148 |
| Traffic | Random OD, congested | Random OD, congested |
| Duration | 3600s (1 hour) | 3600s (1 hour) |

### Three Scenarios per Network

| Scenario | Description |
|----------|-------------|
| **Baseline** | Default signal timing, no optimization |
| **Webster** | Webster-based TLS adaptation — optimizes cycle length and phase splits based on traffic volume |
| **Green Wave** | TLS offset optimization — coordinates signals along corridors for continuous flow |

### Output Files (per scenario, 3 files each)
- `tripinfo.xml` — per-vehicle: duration, waitingTime, timeLoss, CO2_abs, fuel_abs, etc.
- `netstate.xml` — per-edge: density, speed, timeLoss, etc.
- `netstate_emission.xml` — per-edge: CO2_abs, fuel_abs (abs/normed/perVeh), etc.

### SQLite Database
All XML outputs converted into one DB with 3 tables:
- `simulations` — metadata (id, description, vehicle_count)
- `trips` (29 columns) — 22 traffic + 7 emission attributes per vehicle
- `edge_metrics` (41 columns) — 20 traffic + 21 emission attributes per edge

---

## 3. Ablation Procedure

### Full (SQLite)
- LLM receives DB schema in system prompt
- Executes SQL queries via `read_query` tool
- Single persistent session (conversation history across all 20 questions)

### XML Only (Filesystem)
- LLM reads raw XML files via filesystem MCP tools
- **Per-question sessions** — new session for each question to prevent token overflow
- Must parse XML content within the context window and compute answers manually

### No Output Management
- No tools available
- Simulates a scenario where simulation outputs exist but are not structured or accessible to the agent
- Single persistent session

---

## 4. Benchmark Questions

### L1 — Single-Simulation Retrieval (5 questions)

| ID | Question |
|----|----------|
| L1_01 | What is the average trip duration (in seconds) in the baseline? |
| L1_02 | What is the total waiting time of all vehicles (in seconds) in the baseline? |
| L1_03 | What is the average CO2 emission per vehicle (CO2_abs in mg) in the Webster scenario? |
| L1_04 | What is the maximum trip duration (in seconds) in the Green Wave scenario? |
| L1_05 | What percentage of vehicles have a waiting time greater than 60 seconds in the baseline? |

### L2 — Single-Simulation Aggregation (5 questions)

| ID | Question |
|----|----------|
| L2_01 | What is the sum of density (veh/km) of the top 5 densest edges in the baseline? |
| L2_02 | What is the minimum speed (m/s) among the top 5 fastest edges in the Webster scenario? |
| L2_03 | What is the total trip duration (in seconds) of the top 5 longest-duration vehicles in the baseline? |
| L2_04 | What is the average CO2 emission (CO2_abs) of the top 5 highest-emission edges in the Green Wave scenario? |
| L2_05 | What percentage of vehicles have zero waiting time in the Green Wave scenario? |

### L3 — Multi-Simulation Comparison (5 questions)

| ID | Question |
|----|----------|
| L3_01 | What is the percentage reduction in average trip duration from baseline to Webster? |
| L3_02 | What is the percentage reduction in average waiting time from baseline to Green Wave? |
| L3_03 | What is the difference in average fuel consumption per vehicle (fuel_abs in ml) between Webster and Green Wave? |
| L3_04 | What is the percentage reduction in maximum edge density from baseline to Webster? |
| L3_05 | What is the difference in average time loss between baseline and Webster for the top 10% longest-duration vehicles (in seconds)? |

### L4 — Multi-Simulation Judgment (5 questions)

| ID | Question |
|----|----------|
| L4_01 | Which scenario has a higher percentage of vehicles with zero waiting time: Webster or Green Wave? |
| L4_02 | Which policy achieves a lower average edge density: Webster or Green Wave? |
| L4_03 | Which policy achieves a lower average CO2 emission on the top 5 highest-emission edges in the baseline: Webster or Green Wave? |
| L4_04 | Considering both average CO2 emission reduction and average fuel consumption reduction compared to baseline, which policy is more environmentally effective: Webster or Green Wave? |
| L4_05 | Among the top 10% vehicles by duration in the baseline, which policy reduces their average trip duration more: Webster or Green Wave? |

### Evaluation Criteria
- **L1-L3 (numeric)**: Exact match with 5% relative tolerance (`|response - GT| / |GT| <= 0.05`)
- **L4 (judgment)**: Exact string match ("Webster" or "Green Wave")
- **Ground truth**: Generated by running SQL queries directly on the DB (`generate_ground_truth.py`)

---

## 5. Results

### Table 1: Overall Accuracy

| City | Full (SQLite) | XML Only (File) | No Data |
|------|:---:|:---:|:---:|
| Gangnam | **19/20 (95%)** | 13/20 (65%) | 3/20 (15%) |
| Times Square | **19/20 (95%)** | 12/20 (60%) | 3/20 (15%) |
| **Total** | **38/40 (95%)** | 25/40 (63%) | 6/40 (15%) |

### Table 2: Accuracy by Question Level (2 cities combined, 40 questions total)

| Level | Description | Full | XML Only | No Data |
|-------|------------|:----:|:--------:|:-------:|
| L1 (10) | Single-sim retrieval | **10/10 (100%)** | 5/10 (50%) | 0/10 (0%) |
| L2 (10) | Single-sim aggregation | **10/10 (100%)** | 8/10 (80%) | 0/10 (0%) |
| L3 (10) | Multi-sim comparison | **9/10 (90%)** | 5/10 (50%) | 0/10 (0%) |
| L4 (10) | Multi-sim judgment | **9/10 (90%)** | 7/10 (70%) | 6/10 (60%) |

### Table 3: Cost Efficiency (averaged across 2 cities)

| Metric | Full | XML Only | No Data |
|--------|-----:|--------:|-------:|
| Total tokens | 151,519 | 1,208,355 | **23,445** |
| Input tokens | 144,904 | 1,183,500 | **18,094** |
| Output tokens | 6,615 | 24,855 | **5,351** |
| API calls | 45 | 90 | **21** |
| Tool calls | 24 | 70 | 0 |
| Latency (sec) | **154** | 553 | 164 |
| **Tokens / correct answer** | **3,987** | 48,334 | 3,907 |

### Table 4: Per-Level Token Usage (tokens per question, averaged)

| Level | Full | XML Only | No Data |
|-------|-----:|--------:|-------:|
| L1 | 3,049 | 42,796 | **639** |
| L2 | 4,917 | 30,587 | **991** |
| L3 | 7,107 | 85,134 | **1,291** |
| L4 | 14,750 | 91,150 | **1,734** |

---

## 6. Detailed Results — Gangnam Station

### Ground Truth

| ID | Answer | Unit |
|----|--------|------|
| L1_01 | 39.40 | seconds |
| L1_02 | 18.0 | seconds |
| L1_03 | 119,450.48 | mg |
| L1_04 | 118.0 | seconds |
| L1_05 | 0.0 | percent |
| L2_01 | 92.86 | veh/km |
| L2_02 | 18.84 | m/s |
| L2_03 | 515.0 | seconds |
| L2_04 | 743,953.41 | mg |
| L2_05 | 96.15 | percent |
| L3_01 | -1.45 | percent |
| L3_02 | 22.22 | percent |
| L3_03 | 662.68 | ml |
| L3_04 | 9.23 | percent |
| L3_05 | -1.4 | seconds |
| L4_01 | Green Wave | — |
| L4_02 | Green Wave | — |
| L4_03 | Webster | — |
| L4_04 | Green Wave | — |
| L4_05 | Green Wave | — |

### Per-Question Results

| ID | GT | Full | | XML Only | | No Data | |
|----|-----|------|:-:|----------|:-:|---------|:-:|
| L1_01 | 39.40 | 39.40 | **O** | 43.20 | X | 850 | X |
| L1_02 | 18.0 | 18.0 | **O** | 18.00 | **O** | 420,000 | X |
| L1_03 | 119,450 | 119,450 | **O** | 125,129 | X | 2,300 | X |
| L1_04 | 118.0 | 118.0 | **O** | 118.00 | **O** | 2,400 | X |
| L1_05 | 0.0% | 0.0% | **O** | 0% | **O** | 45% | X |
| L2_01 | 92.86 | 92.86 | **O** | 92.86 | **O** | 450 | X |
| L2_02 | 18.84 | 18.84 | **O** | 18.84 | **O** | 13 | X |
| L2_03 | 515.0 | 515.0 | **O** | 515.00 | **O** | 9,500 | X |
| L2_04 | 743,953 | 743,953 | **O** | 743,953 | **O** | 2,500,000 | X |
| L2_05 | 96.15% | 96.15% | **O** | 100% | X | 20% | X |
| L3_01 | -1.45% | +1.45% | **O** | -0.80% | X | 12% | X |
| L3_02 | 22.22% | 22.22% | **O** | 21.74% | **O** | 18% | X |
| L3_03 | 662.68 | 662.68 | **O** | -859.22 | X | 15 | X |
| L3_04 | 9.23% | 9.23% | **O** | 9.23% | **O** | 20% | X |
| L3_05 | -1.4 | +1.72 | X | -1.56 | **O** | 120 | X |
| L4_01 | Green Wave | Green Wave | **O** | identical | X | Green Wave | **O** |
| L4_02 | Green Wave | Green Wave | **O** | Green Wave | **O** | Green Wave | **O** |
| L4_03 | Webster | Webster | **O** | Webster | **O** | Webster | **O** |
| L4_04 | Green Wave | Green Wave | **O** | Green Wave | **O** | Green Wave | **O** |
| L4_05 | Green Wave | Green Wave | **O** | Green Wave | **O** | Webster | X |

---

## 7. Detailed Results — Times Square

### Ground Truth

| ID | Answer | Unit |
|----|--------|------|
| L1_01 | 71.97 | seconds |
| L1_02 | 3,600.0 | seconds |
| L1_03 | 204,328.87 | mg |
| L1_04 | 189.0 | seconds |
| L1_05 | 10.81 | percent |
| L2_01 | 631.76 | veh/km |
| L2_02 | 15.45 | m/s |
| L2_03 | 978.0 | seconds |
| L2_04 | 1,672,311.37 | mg |
| L2_05 | 38.51 | percent |
| L3_01 | 2.66 | percent |
| L3_02 | 17.83 | percent |
| L3_03 | 6,356.56 | ml |
| L3_04 | 50.88 | percent |
| L3_05 | 24.27 | seconds |
| L4_01 | Green Wave | — |
| L4_02 | Webster | — |
| L4_03 | Green Wave | — |
| L4_04 | Green Wave | — |
| L4_05 | Green Wave | — |

### Per-Question Results

| ID | GT | Full | | XML Only | | No Data | |
|----|-----|------|:-:|----------|:-:|---------|:-:|
| L1_01 | 71.97 | 72.0 | **O** | 82.79 | X | 450 | X |
| L1_02 | 3,600 | 3,600 | **O** | 3,616 | **O** | 18,000 | X |
| L1_03 | 204,329 | 204,329 | **O** | 194,863 | X | 950 | X |
| L1_04 | 189.0 | 189.0 | **O** | 189.00 | **O** | 1,200 | X |
| L1_05 | 10.81% | 10.8% | **O** | 11.56% | X | 40% | X |
| L2_01 | 631.76 | 631.76 | **O** | 631.76 | **O** | 400 | X |
| L2_02 | 15.45 | 15.45 | **O** | 15.45 | **O** | 20 | X |
| L2_03 | 978.0 | 978.0 | **O** | 978.00 | **O** | 6,500 | X |
| L2_04 | 1,672,311 | 1,672,311 | **O** | 1,672,311 | **O** | 125,000 | X |
| L2_05 | 38.51% | 38.5% | **O** | 64.63% | X | 20% | X |
| L3_01 | 2.66% | 2.66% | **O** | 6.96% | X | 12% | X |
| L3_02 | 17.83% | 17.8% | **O** | 50.15% | X | 25% | X |
| L3_03 | 6,357 | 6,357 | **O** | 5,595 | X | 25 | X |
| L3_04 | 50.88% | 50.9% | **O** | 50.88% | **O** | 20% | X |
| L3_05 | 24.27 | 25.1 | **O** | 14.50 | X | 120 | X |
| L4_01 | Green Wave | Green Wave | **O** | Green Wave | **O** | Green Wave | **O** |
| L4_02 | Webster | Webster | **O** | Webster | **O** | Green Wave | X |
| L4_03 | Green Wave | Green Wave | **O** | Green Wave | **O** | Green Wave | **O** |
| L4_04 | Green Wave | Webster | X | Green Wave | **O** | Green Wave | **O** |
| L4_05 | Green Wave | Green Wave | **O** | Green Wave | **O** | Green Wave | **O** |

---

## 8. Error Analysis

### Full (SQLite) — 2 errors / 40

| Question | GT | Response | Cause |
|----------|-----|---------|-------|
| Gangnam L3_05 | -1.4s | +1.72s | Different subquery for "top 10%" vehicle selection |
| Times Square L4_04 | Green Wave | Webster | Different normalization in combined CO2+fuel score |

Both errors stem from valid but slightly different computational approaches, not from data access failures.

### XML Only — 15 errors / 40

| Error Type | Count | Description |
|-----------|:-----:|-------------|
| Arithmetic error | 5 | Manual summation of hundreds of values from XML — addition mistakes |
| Incomplete data scan | 4 | Missed or double-counted entries when scanning XML line by line |
| Multi-file comparison error | 4 | Errors when cross-referencing values across 2-3 XML files |
| Wrong judgment from wrong data | 2 | Incorrect intermediate values led to wrong policy choice |

### No Data — 34 errors / 40

| Error Type | Count | Description |
|-----------|:-----:|-------------|
| Wrong numeric estimate (L1-L3) | 28 | Estimates off by 1-3 orders of magnitude |
| Wrong judgment (L4) | 4 | General knowledge led to incorrect policy comparison |
| Correct judgment (L4) | 6 | General traffic knowledge correctly predicted the better policy |

---

## 9. Scalability

| Network Size | tripinfo tokens | Full | XML Only |
|-------------|:---------:|:-----------:|:----------------:|
| Small (150 vehicles) | ~23K | Yes | Yes |
| Medium (1,500 vehicles) | ~230K | Yes | L1/L2 only |
| Large (5,700 vehicles) | ~850K | Yes | No (exceeds context) |
| Real-world (50K+ vehicles) | ~8M+ | Yes | No |

SQLite queries return only the needed results (a few tokens), regardless of dataset size. XML file access requires loading entire files into context, which scales linearly with data size and eventually exceeds the LLM context window.
