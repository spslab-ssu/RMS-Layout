# Architecture

```text
CLI/config or app.py
   |
   v
Src/data.py ------------> RMSInstance
   |                           |
   |                           v
   |                  Src/strengthening.py
   |                  counting / theta / MIR
   |                           |
   |                  Src/relocation.py
   |             move arcs / physical policy
   |                           |
   +---------------------------+
                               v
                         Src/milp.py
                    lifecycle + material flow
                               |
                               v
                         RMSSolution
                         /          \
                        v            v
              Src/output.py   Src/visualize.py
```

## 책임 분리

- `config.py`: 실험 기본값과 독립 configuration 생성
- `main.py`: CLI 인자 처리와 전체 파이프라인 조립
- `app.py`: 격자·수요·제약 편집과 Stage 1/2 비교를 제공하는 Streamlit UI
- `Src/scenario.py`: 임의 `m × n` 좌표 생성, 편집 테이블 검증, 원본과 분리된 시나리오 입력 생성
- `Src/sensitivity.py`: 이동비용·configuration 변경비용·격자 후보 생성, 반복 풀이, 안정 구간 추천
- `Src/data.py`: CSV schema 검증과 model parameter 전처리
- `Src/milp.py`: network/flow 변수, 제약, 목적함수, 해 추출
- `Src/milp.py`의 solve hierarchy: 시스템 비용 최적화 후 같은 비용에서 relocation 최소화
- `Src/base_milp.py`: 기존 논문의 `x-s-y` formulation 비교 기준선
- `Src/strengthening.py`: valid inequality 생성과 dominance pruning
- `Src/relocation.py`: relocation arc, 다운타임, 크루, 맞교환, 체증비용을 담당하는 coupling 계층
- `Src/output.py`: 안정된 CSV/JSON 결과 schema와 Stage 1 후보/Stage 2 분리 저장
- `Src/visualize.py`: period별 layout, relocation 화살표, 단계별 양쪽 비교 그림
- `experiments/`: 논문표와 후속 실험 재현
- `experiments/compare_formulations.py`: base/network/network_mir 동일조건 비교
- `tests/`: 수치 회귀검사

## 정리한 레거시

- 이전 `Data/`, `Src/`, 실행 스크립트와 결과 폴더는 `archive/legacy_root/`로 이동
- Python cache와 중첩 프로젝트 폴더는 삭제
- 현재 루트에는 network+MIR/relocation 기준 구현만 유지

입력 데이터와 PDF reference는 재현성을 위해 유지합니다.

과거 `adaptive_milp.py`, `network_adaptive.py`는 `archive/legacy_root/Src/`에
보존했다. 새 relocation 연구의 기준 구현은 `Src/milp.py` +
`Src/relocation.py`이며, baseline은 `ENABLE_RELOCATION=False`로 보존한다.
