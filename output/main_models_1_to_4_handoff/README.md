# RMS 싱글파트 모델 1~4: AI 인계 패키지

이 패키지는 `main` 브랜치의 커밋 `99e660fb8d262451cc361c72f68ff11c301d6021`을 기준으로 다음 네 모델을 수식화하고 비교하기 위한 독립 자료이다.

1. 논문/기준 MILP
2. 논문형 MILP + RMT 위치 적응(adaptive relocation)
3. 시간확장 network formulation
4. network + adaptive relocation

## 가장 먼저 읽을 순서

1. `00_EXECUTIVE_OVERVIEW.md`
2. `01_COMMON_NOTATION_AND_DATA.md`
3. `02_MODELS_1_TO_4.md`
4. `03_EQUIVALENCE_AND_COMPARISON.md`
5. `04_CODE_MAP_VALIDATION_WARNINGS.md`
6. `05_PAPER_CONTEXT_AND_RESEARCH_DECISIONS.md`
7. `AI_HANDOFF_PROMPT.md`

`main_source_snapshot.zip`에는 위 커밋에서 직접 추출한 관련 코드, 싱글파트 데이터와 기존 비교 결과가 들어 있다. 현재 체크아웃된 브랜치의 파일을 복사한 것이 아니므로 로컬 작업 내용과 섞이지 않는다.

## 핵심 결론

- Model 1과 Model 3은 물리적으로 같은 **고정 위치 문제**를 서로 다른 변수로 표현한다.
- Model 2와 Model 4는 물리적으로 같은 **이동 가능 문제**를 각각 implication MILP와 network flow로 표현하려는 모델이다.
- 정수 물리해로 사영하면, 동일한 가정 아래 `F1 = F3 ⊆ F2 = F4`가 목표 관계다.
- 따라서 network는 새 운영정책이 아니라 주로 **재수식화**이며, adaptive가 실제 의사결정 범위를 넓힌다.
- 다만 `main`의 Model 2 파일은 공유자원·모듈재고 등 추가 실험 제약까지 포함하고 기본 실행 경로에도 연결되어 있지 않다. 이 패키지는 그 파일에서 relocation 핵심만 분리해 Model 2를 정의한다.

## 범위와 한계

- 이 문서는 코드 해석과 후속 수식 정립을 돕는 연구용 명세이다.
- 논문 PDF 자체는 ZIP에 재배포하지 않았다.
- 코드의 material-flow 부분은 논문의 식을 문자 그대로 옮긴 것이 아니라, 공정경로의 arc별 수요를 정확히 맞추는 구현형 표현이다.
- Model 2와 Model 4의 완전한 동치성은 최종 수식에서 초기상태, 구매시점, 허용 전이, 위치 용량, 비용 정의를 동일하게 맞춘 뒤 검증해야 한다.
