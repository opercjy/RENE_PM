# RENE-PM (Project Integrated Monitoring System)

RENE-PM은 물리 실험 환경의 다양한 장비를 통합 모니터링하고 제어하기 위해 개발된 PyQt5 기반의 고성능 데스크톱 애플리케이션입니다. 환경 센서, 고전압(HV) 장비, 전력 분배 시스템(PDU), 그리고 안전 센서(Fire/Gas)를 실시간으로 통합 관리합니다.

## 1. 프로젝트 정보

* **현재 버전:** v2.1.9
* **개발 언어:** Python 3.8+
* **GUI 프레임워크:** PyQt5
* **데이터베이스:** MariaDB
* **주요 통신:** Modbus TCP/RTU, Serial, NI-DAQmx

## 2. 주요 기능 (Key Features)

### 2.1. 고급 안전 모니터링 (Advanced Safety) 🛡️
* **통합 안전 대시보드:** 화재 감지기(Honeywell FS24X Plus)와 VOC 감지기(RAEGuard 2 PID) 데이터를 실시간 분석.
* **동적 SOP 가이드:** 위험 수준(Normal / Warning / Emergency)에 따라 행동 요령(SOP)과 비상 연락망을 즉시 화면에 표시.
* **시각적 경보:** 위험 감지 시 화면 전체에 붉은색 경고 및 "EMERGENCY" 상태 점멸.

### 2.2. 전원 제어 및 관리 (Power Control) ⚡
* **NETIO PowerPDU 8KF 통합:** Modbus TCP를 통해 8개 포트의 개별 전원 ON/OFF 제어.
* **전력 모니터링:** 각 포트의 실시간 전력(W), 전류(mA), 누적 에너지(Wh) 측정 및 로깅.
* **UPS 연동:** 정전 시 배터리 잔량을 감시하여 HV 장비를 자동으로 안전하게 종료(Emergency Shutdown).

### 2.3. 고전압(HV) 시스템 제어 🎛️
* **CAEN HV 제어:** 슬롯/채널별 전압(VMon) 및 전류(IMon) 모니터링.
* **원격 설정:** V0Set, I0Set, Power On/Off 원격 제어 지원.
* **상태 시각화:** 보드 온도에 따른 색상 코딩(🟢정상, 🟠주의, 🔴위험) 제공.

### 2.4. 데이터 분석 및 로깅 🔍
* **실시간 그래프:** PyQtGraph 기반의 고속 시계열 데이터 플로팅.
* **Data History:** 과거 데이터 조회, 상관관계 분석(Correlation Analysis), CSV 내보내기.
* **데이터베이스:** 모든 센서 데이터는 타임스탬프와 함께 MariaDB에 영구 저장.

## 3. 하드웨어 구성 및 통신

| 장비명 | 통신 방식 | 프로토콜 | 역할 |
| :--- | :--- | :--- | :--- |
| **CAEN HV (SY4527)** | Ethernet | TCP/IP (Socket) | PMT 고전압 공급 및 제어 |
| **NETIO PowerPDU 8KF** | Ethernet | Modbus TCP | 실험 장비 전원 분배 및 제어 |
| **Honeywell FS24X+** | RS-485 | Modbus RTU | 불꽃(화재) 감지 |
| **RAEGuard 2 PID** | RS-485 | Modbus RTU | 휘발성 유기 화합물(VOC) 감지 |
| **NI cDAQ-9178** | USB | NI-DAQmx | 액체 레벨, 온도 센서(RTD) 수집 |
| **Arduino / Sensors** | USB(Serial) | Custom/ASCII | 온습도, 라돈, 자기장 등 보조 센서 |

## 4. 설치 및 실행

### 4.1. 필수 요구사항
* Python 3.8 이상
* MariaDB Server
* NI-DAQmx Driver (옵션)

### 4.2. 패키지 설치
```bash
pip install PyQt5 pyqtgraph numpy pandas matplotlib mariadb pymodbus nidaqmx pyvisa pyvisa-py
```
### 4.3. 설정 (Configuration)
config_v2.json 파일에서 DB 접속 정보와 장비별 포트/임계값을 설정합니다.

```JSON

"voc_detector": {
    "thresholds": { "warning_ppm": 50.0, "critical_ppm": 100.0 }
}
```
### 4.4. 실행
```Bash
python rene_pm_main.py
```
