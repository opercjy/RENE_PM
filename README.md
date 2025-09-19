# RENE_PM

-----

# RENE-PM v2.0: 통합 환경 및 고전압(HV) 실시간 모니터링 시스템

## 개요

RENE-PM(Project Integrated Monitoring System) v2.0은 다양한 물리 센서(온도, 거리, 라돈, 자기장 등)와 CAEN 고전압(HV) 시스템의 데이터를 단일 대시보드에서 실시간으로 수집, 처리, 시각화 및 저장하는 고성능 통합 모니터링 솔루션입니다.

v2.0은 대규모 아키텍처 최적화를 통해 시스템의 안정성과 성능을 극대화했습니다. 모든 하드웨어 제어와 데이터베이스 작업은 GUI와 완전히 독립된 백그라운드 스레드에서 비동기적으로 처리되어, 장기간 운영 시에도 최고의 응답성과 안정성을 보장합니다.

## 주요 특징 및 개선 사항

  - **완벽한 통합 모니터링 (Fully Integrated)**

      - 하나의 애플리케이션에서 **환경 센서**와 **CAEN HV 시스템** 상태를 동시에 모니터링합니다.
      - 32인치 QHD 해상도에 최적화된 대시보드는 모든 정보를 한눈에 파악할 수 있도록 설계되었습니다.

  - **고성능 비동기 아키텍처 (High-Performance Asynchronous Architecture)**

      - **생산자-소비자 패턴**: 모든 센서 워커(생산자)와 데이터베이스 워커(소비자)를 중앙 큐(`Queue`)로 연결하여, 데이터 수집과 DB 저장 부하를 완벽하게 분산시켰습니다.
      - **GUI 응답성 보장**: 모든 I/O 작업(하드웨어 통신, DB)이 백그라운드 스레드에서 처리되어 GUI 멈춤 현상(Freezing)이 원천적으로 발생하지 않습니다.

  - **최적화된 하드웨어 통신 (Optimized Hardware Communication)**

      - **HV 벌크 리드 (Bulk Read)**: `caenhvwrapper`의 일괄 읽기 기능을 사용하여 CAEN HV 시스템과의 네트워크 통신량을 **97% 이상 감소**시켰습니다.
      - **DAQ 오버샘플링 & 평균화**: NI-DAQ의 고속 샘플링(1000Hz)과 평균화 기법을 통해 노이즈가 많은 아날로그 신호(예: 초음파 센서)로부터 안정적이고 정밀한 값을 추출합니다.

  - **효율적인 실시간 시각화 (Efficient Real-time Visualization)**

      - **고속 그래프 렌더링**: `pyqtgraph`와 \*\*Numpy 순환 버퍼(Circular Buffer)\*\*를 사용하여 수십만 개의 데이터 포인트도 메모리 복사 없이 효율적으로 시각화합니다.
      - **동적 상태 표시**: HV 채널의 상태(전압/전류 차이, Power Off)를 색상으로 구분하여 직관적인 상태 파악이 가능합니다.

  - **안정적인 데이터베이스 로깅 (Robust Database Logging)**

      - **배치 처리 (Batch Processing)**: 전용 `DatabaseWorker` 스레드가 여러 데이터를 모아 단 한 번의 트랜잭션으로 DB에 일괄 삽입하여 쓰기 부하를 최소화합니다.
      - **통합 스키마**: 환경 데이터와 HV 데이터를 동일한 데이터베이스 내의 개별 테이블에 안정적으로 저장합니다.

  - **모듈식 설계 및 확장성 (Modular & Extensible Design)**

      - **워커(Worker) 패턴**: 각 하드웨어(DAQ, Radon, HV 등) 제어 로직을 `workers` 디렉토리 내의 독립적인 파일로 분리하여 유지보수성과 확장성을 극대화했습니다.
      - **외부 설정 관리**: 모든 환경 설정(하드웨어 정보, DB 접속 정보, 담당자 이름 등)을 `config_v2.json` 파일로 외부화하여 코드 수정 없이 환경 변경이 가능합니다.

-----

## 시스템 아키텍처

시스템은 메인 GUI 스레드, 다수의 센서 워커 스레드(생산자), 단일 데이터베이스 워커 스레드(소비자)로 구성됩니다. 데이터는 \*\*시그널(Signal)\*\*과 \*\*큐(Queue)\*\*를 통해 스레드 간에 안전하게 전달됩니다.

  - **메인 스레드**: UI 렌더링 및 사용자 이벤트 처리를 전담합니다.
  - **워커 스레드**: 각 하드웨어(NI-DAQ, Radon, Magnetometer, **CAEN HV** 등)와의 통신 및 데이터 수집을 담당합니다. 수집된 데이터는 UI 표시를 위해 메인 스레드로 **시그널**을 보내고, 영구 저장을 위해 DB **큐**에 데이터를 넣습니다.
  - **DB 스레드**: DB 큐를 감시하다가 데이터가 쌓이면 일괄 처리(Batch)하여 데이터베이스에 저장합니다.

-----

## 요구사항

### 하드웨어

  - **데이터 수집 장비 (DAQ)**: National Instruments cDAQ 섀시 및 모듈
  - **초음파 거리 센서**: SICK UM30 계열 또는 0-10V 아날로그 출력 센서
  - **라돈 검출기**: Ftlab(라돈아이) 또는 호환 시리얼 통신 모델
  - **자기장 센서**: TFM1186 또는 NI-VISA 호환 SCPI 지원 모델
  - **고전압 시스템**: CAEN SY4527 또는 호환 모델

### 소프트웨어 및 라이브러리

  - Python 3.8+
  - 필수 드라이버: NI-DAQmx, NI-VISA, CAEN HV C/C++ Wrapper
  - Python 라이브러리:
      - `PyQt5`
      - `pyqtgraph`
      - `numpy`
      - `nidaqmx`
      - `pyUSB`
      - `pyserial`
      - `pyvisa`
      - `mariadb`
      - `py-caen-libs` (CAEN HV Wrapper Python 바인딩)

-----

## 설치 및 실행

1.  **드라이버 설치**: NI와 CAEN에서 제공하는 모든 필수 하드웨어 드라이버를 먼저 설치합니다.

2.  **Python 가상환경 설정 및 라이브러리 설치**:

    ```bash
    # 프로젝트 디렉토리에서 가상환경 생성 및 활성화
    python -m venv venv
    source venv/bin/activate  # Linux/macOS

    # 필요 라이브러리 일괄 설치
    pip install numpy pyqt5 pyqtgraph nidaqmx pyserial pyvisa mariadb

    # py-caen-libs는 CAEN 제공 절차에 따라 별도 설치
    ```

3.  **환경 설정 (`config_v2.json`)**:
    프로젝트에 포함된 `config_v2.json` 파일을 열어, 사용자의 실제 DB 접속 정보, 시리얼 포트, DAQ 장치 이름, CAEN HV IP 주소 등을 정확하게 수정합니다.

4.  **실행**:

    ```bash
    python rene_pm_main.py
    ```

    프로그램은 시작 시 자동으로 모든 하드웨어 연결을 시도하며, 로그는 콘솔과 `rene_pm.log` 파일에 동시에 기록됩니다.

-----

## 데이터베이스 추출 예시

MariaDB에 저장된 HV 데이터를 CSV 파일로 추출하는 예시입니다.

```mysql
SELECT datetime, slot, channel, vmon, imon
FROM RENE_PM.HV_DATA
WHERE datetime >= '2025-09-14 00:00:00'
INTO OUTFILE '/tmp/hv_data_export.csv'
FIELDS TERMINATED BY ',' ENCLOSED BY '"';
```
