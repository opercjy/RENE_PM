# RENE-PM Patch Notes (Changelog)

## [v2.1.0] - 2025-11-27

### 개요
v2.1은 NETIO PowerPDU 8KF 통합을 통한 원격 전원 제어 기능 추가와 시스템 안정성 향상에 중점을 두었습니다.

### 신규 기능 (Added)

*   **NETIO PowerPDU 8KF 통합:**
    *   Modbus TCP 프로토콜을 사용하여 PDU와의 통신을 구현했습니다 (`workers/pdu_worker.py`).
    *   PDU 상태(전압, 주파수, 총 전력) 및 8개 포트의 개별 상태(ON/OFF, 전력, 전류, 에너지)를 모니터링합니다.
*   **PDU 제어 UI:**
    *   GUI에 "⚡ Power Control (PDU)" 탭을 신설했습니다.
    *   원격 제어(개별/일괄 ON/OFF) 기능을 제공합니다. 일괄 제어 시 안전 확인 대화상자가 표시됩니다.
*   **데이터베이스 확장:**
    *   PDU 데이터를 기록하기 위한 `PDU_DATA` 테이블 스키마를 추가했습니다 (`workers/database_worker.py`).
*   **PDU 데이터 분석 기능:**
    *   Analysis 탭에 PDU 데이터(Power, Current, Energy) 시계열 조회 기능을 추가했습니다 (`rene_pm_main.py`).
    *   조회할 포트를 선택할 수 있는 UI를 구현하고, 결과 시각화 및 CSV 내보내기를 지원합니다.

### 개선 사항 (Changed)

*   **DatabaseWorker 로직 개선:**
    *   `process_batch` 함수가 단일 레코드(Tuple) 뿐만 아니라 배치 레코드(List[Tuple], 예: PDU 데이터)도 효율적으로 처리할 수 있도록 로직을 일반화했습니다.
*   **PDU 일괄 제어 딜레이 조정:**
    *   일괄 제어 시 장비 부하를 줄이기 위해 포트 간 딜레이를 0.15초로 조정했습니다.

### 버그 수정 (Fixed)

*   **애플리케이션 종료 안정성 확보:**
    *   애플리케이션 종료 시 스레드 정리 과정에서 발생하던 충돌 문제(`RuntimeError: wrapped C/C++ object... has been deleted`)를 해결했습니다 (`rene_pm_main.py`). `sip.isdeleted()`를 사용하여 QObject 생명주기를 안전하게 확인합니다.
*   **PDU 통신 호환성 문제 해결:**
    *   `pymodbus` 라이브러리 3.0 이상 버전과의 호환성을 위해 Modbus 통신 파라미터를 `unit`에서 `slave`로 변경했습니다 (`TypeError: unexpected keyword argument 'unit'` 오류 해결).
*   **PDU 통신 안정성 개선:**
    *   `ConnectionException`([Errno 104])에 대한 예외 처리를 강화하고 Modbus Slave ID를 명시적으로 사용하여 통신 안정성을 높였습니다.

## [v2.0.0] - (이전 릴리즈 날짜)

### 개요
RENE-PM 초기 배포 버전. PyQt5 기반의 통합 모니터링 시스템 아키텍처 구축.

### 주요 기능
*   환경 센서 모니터링 (NI-cDAQ, Radon, Magnetometer, TH/O2, Arduino).
*   CAEN HV 시스템 제어 및 모니터링.
*   UPS 상태 감시 및 비상 시 HV 자동 셧다운 기능.
*   실시간 데이터 시각화 및 MariaDB 로깅.
*   과거 데이터 분석 및 상관관계 분석 기능.
