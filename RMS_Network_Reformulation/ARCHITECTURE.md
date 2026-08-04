# Architecture

```text
CLI/config
   |
   v
Src/data.py ------------> RMSInstance
   |                           |
   |                           v
   |                  Src/strengthening.py
   |                  counting / theta / MIR
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
- `Src/data.py`: CSV schema 검증과 model parameter 전처리
- `Src/milp.py`: network/flow 변수, 제약, 목적함수, 해 추출
- `Src/base_milp.py`: 기존 논문의 `x-s-y` formulation 비교 기준선
- `Src/strengthening.py`: valid inequality 생성과 dominance pruning
- `Src/output.py`: 안정된 CSV/JSON 결과 schema
- `Src/visualize.py`: period별 layout 그림
- `experiments/`: 논문표와 후속 실험 재현
- `experiments/compare_formulations.py`: base/network/network_mir 동일조건 비교
- `tests/`: 수치 회귀검사

## 의도적으로 제거한 것

- 존재하지 않는 legacy 경로에서 CSV를 복사하던 `Data/generate_data.py`
- base `x/s/y` 설명이 남아 있던 `SEQUENCE.md`
- 동일 실행을 중복하던 root-level 실험 스크립트
- 저장된 결과물을 소스처럼 포함하던 기존 `Result_network_single/`

입력 데이터와 PDF reference는 재현성을 위해 유지합니다.
