# Multi-Part Paper Warm Start

메인논문 Example 2, Figure 4(a-d)를 기준으로 만든 Gurobi warm start CSV입니다.

현재 MILP에는 period 2 신규 구매 변수가 없으므로, 논문에서 period 2에 구매되는 location 3과 17은 period 1에 flow 0인 idle 장비로 표현했습니다. 구매비는 동일하게 계산됩니다.

포함 파일:

- `purchased_machines.csv`: 전체 계획기간에 구매되는 장비 x[p,j,l]
- `machine_states.csv`: period별 장비 상태 s[p,j,l,t]와 처리량 v[p,l,t]
- `reconfigurations.csv`: configuration 변경 y[p,j_prev,j_next,l,t]
- `material_flows.csv`: 상태/처리량을 만족하는 feasible material flow f[p,l,q,l',t]
- `cost_breakdown.csv`: 논문 보고 비용 요약

논문 Example 2 보고 비용:

```text
purchase_cost = 19270
reconfiguration_cost = 1900
material_handling_cost = 14836
total_objective = 36006
```

주의: `material_flows.csv`는 Figure 4의 장비 상태와 period별 demand를 만족하도록 생성한 feasible flow입니다. 그림의 모든 작은 화살표를 수동 전사한 값이 아니라, warm start를 수용시키기 위한 flow입니다.
