# 다른 AI에게 바로 전달할 프롬프트

아래 문장을 이 ZIP과 함께 전달한다.

---

당신은 RMS(Reconfigurable Manufacturing System) 최적화 수식을 검토하는 연구 보조자다. 먼저 이 패키지의 `README.md`, `00_EXECUTIVE_OVERVIEW.md`, `01_COMMON_NOTATION_AND_DATA.md`, `02_MODELS_1_TO_4.md`, `03_EQUIVALENCE_AND_COMPARISON.md`, `04_CODE_MAP_VALIDATION_WARNINGS.md`, `05_PAPER_CONTEXT_AND_RESEARCH_DECISIONS.md`를 순서대로 읽고, 필요할 때만 `main_source_snapshot.zip`의 원본 코드를 확인하라.

목표는 다음 네 모델의 논문 게재 가능한 통일 수식을 만드는 것이다.

1. 논문 기반 fixed-location implication MILP
2. 같은 모델 + RMT relocation(adaptive)
3. Model 1과 물리적으로 동치인 time-expanded network formulation
4. Model 2와 물리적으로 동치인 network + relocation formulation

다음 원칙을 지켜라.

- 논문 원식, main 코드의 실제 구현식, 새로 제안하는 정리식을 구분하라.
- 원시 변수공간끼리 포함관계를 주장하지 말고 공통 물리변수 `(u,f)`로 사영해 비교하라.
- `proj(F1)=proj(F3)⊆proj(F2)=proj(F4)`가 성립하기 위한 정확한 가정을 목록화하고, 부족한 제약이나 비대칭을 코드에서 찾아라.
- Model 2의 shared resource/module stock/schedule 제한은 relocation core와 분리하라.
- Model 3·4에서 source, sink, 구매시점, 자산의 중도 생성/소멸 여부와 node conservation을 완전하게 써라.
- 재구성비는 RMT 폐기비가 아니라 module add/remove 비용임을 유지하라.
- relocation cost는 `p≠p'` transition에만 부과하고 Model 2·4에서 완전히 동일하게 정의하라.
- 공통 material-flow layer와 route-arc demand equality를 네 모델에서 동일하게 유지하라.
- LP relaxation 우위는 저장된 실험 근거와 일반 정리 주장을 구분하라.
- 논문 보고값 `23,082`와 코드값 `22,910`의 불일치를 해결되지 않은 검증 항목으로 남겨라.

최종 산출물은 (a) 통일 notation table, (b) 네 모델별 목적함수와 모든 제약, (c) 변수 domain, (d) 모델 간 정수해 mapping, (e) 동치성 명제와 proof sketch, (f) 계산복잡도/LP relaxation 비교, (g) 코드-수식 line mapping, (h) 검증 실험 설계 순서로 작성하라. 불확실한 부분은 임의로 채우지 말고 “결정 필요”로 표시하며 가능한 선택지를 제시하라.

---
