
---

# 📖 RENE-PM Integrated Monitoring System v3.0 공식 매뉴얼

**RENE-PM v3.0**은 정밀 중성미자 탐색 실험(RENE)의 안전과 안정적인 운영을 위해 개발된 **고성능, 분산형 통합 모니터링 및 제어 시스템**입니다.
본 시스템은 실험실 내 다종의 환경 센서, 고전압(HV) 공급 장치, 전원 분배 장치(PDU), 그리고 인명 안전과 직결된 화재 및 가스 감지 시스템을 단일 인터페이스로 통합하여 실시간으로 감시 및 제어합니다.

기존 V2.1.9의 모놀리식(Monolithic) 구조에서 이따금 발생하던 하드웨어 I/O 병목 현상, UI 멈춤(Freezing), 그리고 종료 시 발생하던 코어 덤프(Core Dump) 문제를 근본적으로 해결하기 위해, V3.0은 완전한 이벤트 기반 분산형 아키텍처(Event-Driven Decentralized Architecture)로 전면 재설계되었습니다.

---

## 1. 프로젝트 개요 (System Overview)

본 시스템은 실험실 내 물리적으로 분리된 다양한 하드웨어를 소프트웨어적으로 통합합니다. 메인 스레드의 간섭 없이 백그라운드 스레드들이 각 장비와 독립적으로 통신하며, 수집된 모든 데이터는 MariaDB에 안전하게 영속화(Persistence)됩니다. 또한 설정 파일을 통한 하드웨어의 런타임 핫스왑(Hot-Swap)을 지원하여 무중단 운영을 지향합니다.

## 2. 아키텍처 설계 제1원리 (Architecture & First Principles)

RENE-PM v3.0은 '제어의 역전(Inversion of Control)'과 '데이터와 로직의 철저한 격리'를 제1원칙으로 작동합니다.

* **거대 지식망 (EventBus):** 시스템 내 어떠한 UI 객체나 하드웨어 워커도 타 객체를 직접 참조(Import)하거나 메서드를 호출하지 않습니다. 모든 모듈은 오직 중앙의 `global_bus`를 통해 `pyqtSignal` 형태로 데이터를 직렬화하여 비동기 브로드캐스트합니다. 특정 장비의 통신 지연이나 오류가 메인 GUI 렌더링에 영향을 미치는 단일 장애점(SPOF)을 완벽히 차단했습니다.
* **상태 저장소 (StateStore) & 링 버퍼:** 초당 수십 건씩 유입되는 센서 데이터를 파이썬의 동적 리스트(`append`)로 처리하면 메모리 재할당과 가비지 컬렉션(GC) 렉이 발생합니다. V3.0은 `np.full(np.nan)`을 통해 최대 한 달 치 데이터를 담을 수 있는 거대한 2D NumPy 배열을 사전 할당하고, 포인터만 순환시키는 **O(1) 복잡도의 링 버퍼(Ring Buffer)** 메커니즘을 적용하여 극한의 메모리 안정성을 확보했습니다.
* **하드웨어 워커 관리자 (WorkerManager):** 스레드의 생성과 소멸을 전담합니다. 장비를 물리적으로 교체하거나 설정을 변경할 때, 시스템 재시작 없이 UI 탭 조작만으로 해당 워커 스레드를 동적으로 회수하고 재배치(Hot-Swap)할 수 있습니다.
* **독립된 안전 룰 엔진 (SafetyExpert):** UI와 완전히 분리된 백그라운드 판단망입니다. 모든 센서 데이터를 감시하며, VOC 가스 농도 초과, 화재 감지, UPS 배터리 부족 시 즉각적으로 전체 HV 전원 차단 명령을 시스템에 하달하고 상황에 맞는 행동 지침을 UI로 발행합니다.

## 3. 주요 기능 및 패널 안내 (UI Features)

화면은 크게 좌측 탭(70%), 우측 HV 상태 그리드(30%), 하단 시스템 상태 대시보드(20%)의 직관적인 3분할 와이드 레이아웃으로 구성됩니다.

* **🛡️ Safety:** 화재/VOC 센서의 상세 수치를 보여주고, 비상 상황 단계(NORMAL, WARNING, EMERGENCY)에 따라 시각적 색상이 격상되며 외부 파일(`sop.json`)에 정의된 행동 지침을 실시간 렌더링합니다.
* **🎛️ HV Control & 📈 HV S1/S4/S8:** CAEN 고전압 보드의 채널별 설정(V0Set, I0Set)을 변경하고 전원을 제어합니다. 분리된 HV S# 탭을 통해 백그라운드에서 샘플링된 전압/전류 데이터를 PyqtGraph 시계열 트렌드로 렌더링합니다.
* **🌡️ Env Graphs:** DAQ 온도, 수위, 자기장, 라돈, 온습도 등 모든 환경 센서의 시계열 추세를 모니터링합니다. 단 1개의 데이터 점(Dot)도 놓치지 않고 렌더링되도록 시각화 로직이 최적화되었습니다.
* **🔍 Data History:** 백그라운드 전용 스레드(`AnalysisWorker`)를 통해 DB에 저장된 과거 데이터를 불러와 Time Series(시계열) 및 상관관계(Correlation) 플롯을 생성하며, 즉시 CSV 포맷으로 추출할 수 있습니다.
* **⚡ PDU Control:** 실험 장비 전원(PDU)의 개별/전체 ON/OFF 원격 제어 및 포트별 소비 전력을 모니터링합니다.
* **🗺️ Guide & 📝 Notes:** PMT 채널 배치도 검색 가이드와 Markdown 기반 실험실 작업 일지 뷰어를 제공합니다.
* **📜 Logs & ⚙️ Settings:** 터미널에 출력되는 로깅 내역을 실시간으로 가로채어 보여주며, 하드웨어 스레드를 시스템 재시작 없이 핫스왑 제어합니다.

## 4. 지원 하드웨어 규격 (Hardware Integration)

본 시스템은 상이한 통신 프로토콜을 가진 다종의 하드웨어를 독립된 데몬 스레드(Worker)를 통해 완벽하게 병렬 통합합니다.

* **고전압 제어 (CAEN HV SY4527):** TCP/IP (Socket) 통신. C/C++ 래퍼(`caen_HWWrapper`,`caen_libs`)를 통한 제어 및 보드 온도 폴링.
* **전원 분배 (NETIO PowerPDU 8KF):** Modbus TCP 통신 (`pymodbus`). 포트별 전력/전류 측정 및 릴레이 제어.
* **안전 감지 시스템 (Honeywell FS24X Plus / RAEGuard2 PID):** Modbus RTU (RS-485 to USB). 화재 알람 코드 및 VOC 실시간 감지.
* **데이터 수집 (NI cDAQ-9178):** NI-DAQmx 프로토콜. PT-3851 RTD 기반 정밀 온도 및 아날로그 초음파 수위 측정.
* **자기장 센서 (Metrolab TFM1186):** PyVISA (USBTMC) 기반 SCPI 통신.
* **라돈 감지기 (Radon7):** Serial ASCII 통신. 초기 구동 시 측정 안정화 카운트다운 로직 포함.
* **온습도/산소 (TH/O2) & Arduino:** Modbus RTU 및 일반 Serial 통신 기반 보조 환경 데이터 수집.
* **비상 전원 (APC UPS):** 리눅스 `apcupsd` 데몬(`apcaccess` 파싱) 서브프로세스 호출을 통한 전압/배터리 잔량 모니터링.

## 5. 시스템 요구사항 (System Requirements)

RENE-PM v3.0은 Python 3.9 이상 및 리눅스(Linux) 환경에 최적화되어 있습니다. 기존 PyQt5에서 최신 렌더링 엔진인 **PyQt6**로 프레임워크가 격상되었습니다.

---

## 6. 시스템 요구사항 및 하드웨어 의존성 설치 (Installation & Dependencies)

RENE-PM 시스템은 다종의 산업용 규격 장비와 통신하므로, 파이썬 패키지 설치 이전에 반드시 OS 수준의 데몬과 제조사 공식 드라이버가 선행 설치되어야 합니다. 본 가이드는 구버전(V2.1.9)과 신버전(V3.0)의 양립(Coexistence) 환경 구축을 기준으로 작성되었습니다.

### 6.1. 운영체제(OS) 코어 및 데몬 패키지 설치 (Linux)

GUI 렌더링, 데이터베이스 서버, 그리고 비상 전원(UPS) 감시를 위한 리눅스 시스템 패키지를 설치합니다.

**[RHEL / CentOS / Rocky Linux / AlmaLinux 계열]**

```bash
# 1. PyQt6 GUI 렌더링을 위한 X11 커서 플러그인 (V3.0 필수)
sudo dnf install xcb-util-cursor

# 2. MariaDB 데이터베이스 서버 및 C 커넥터 (Python mariadb 패키지 빌드 시 필수)
sudo dnf install mariadb-server mariadb-connector-c-devel gcc gcc-c++
sudo systemctl enable --now mariadb

# 3. APC UPS 통신 데몬 (UPS 상태 폴링용)
sudo dnf install apcupsd
sudo systemctl enable --now apcupsd

```

**[Ubuntu / Debian 계열]**

```bash
sudo apt-get update
sudo apt-get install libxcb-cursor0 mariadb-server libmariadb-dev gcc g++ apcupsd
sudo systemctl enable --now mariadb
sudo systemctl enable --now apcupsd

```

### 6.2. 하드웨어 벤더(Vendor) 드라이버 및 C/C++ 라이브러리

파이썬 패키지를 설치하기 전, 하드웨어 제조사가 제공하는 시스템 드라이버를 OS에 직접 설치해야 합니다.

* **CAEN HV 제어 라이브러리:**
1. CAEN 공식 웹사이트에서 `CAEN HV Wrapper Library (Linux)` 소스코드를 다운로드하여 설치 스크립트(`install.sh`)를 실행하거나 `make install`을 통해 시스템(`/usr/lib`)에 `.so` 동적 라이브러리를 적재합니다. (`sudo ldconfig` 수행 필수)
2. RENE 실험실 시스템에 맞게 C++ 라이브러리를 바인딩하여 자체 제작한 `caen_libs` 폴더로 이동하여 파이썬 래퍼를 수동 컴파일 및 설치합니다.


```bash
cd caen_libs/
python setup.py build
pip install -e .

```


* **NI-DAQmx (National Instruments):**
수위 및 온도 센서 제어를 위한 공식 리눅스 드라이버입니다.
1. NI 공식 홈페이지에서 제공하는 `NI Linux Device Drivers` (RPM/DEB)를 시스템에 등록합니다.
2. 리눅스 커널용 모듈을 설치합니다.


```bash
sudo dnf install ni-daqmx ni-linux-driver-dkms
sudo dkms autoinstall  # 설치 후 커널 인식 및 장치 마운트를 위해 재부팅 권장

```



### 6.3. 파이썬 통합 패키지 설치 (Python Dependencies)

V2.1.9(PyQt5)와 V3.0(PyQt6) 아키텍처가 가상환경(`venv`) 내에서 충돌 없이 동시에 실행될 수 있도록 두 가지 Qt 프레임워크를 모두 설치하며, 하드웨어 제어용 패키지를 일괄 설치합니다.

```bash
# 1. pip 패키지 매니저 최신화
python -m pip install --upgrade pip

# 2. UI 프레임워크 및 데이터 시각화/분석 코어 (V2 및 V3 동시 지원)
pip install PyQt5 PyQt5-sip PyQt6 PyQt6-sip pyqtgraph numpy pandas matplotlib

# 3. 하드웨어 통신 및 데이터베이스 영속성 모듈
# - mariadb: 고속 DB 일괄 저장 (※ 6.1의 C 개발 헤더가 설치되어 있어야 빌드 성공)
# - pymodbus: NETIO PDU 전원 제어, 화재(FS24X Plus) 및 VOC 센서 통신
# - pyserial: 라돈 및 아두이노 센서 통신
# - nidaqmx: NI cDAQ 제어
# - pyvisa, pyvisa-py: 자력계(Magnetometer) 등 SCPI 계측기 통신
pip install mariadb pymodbus pyserial nidaqmx pyvisa pyvisa-py

```

> **💡 Note:** PyVISA 연동을 사용하는 장비의 경우, 파이썬 순수 구현체인 `pyvisa-py` 백엔드가 설치되어 있으면 별도의 무거운 외부 라이브러리(NI-VISA 등) 없이도 리눅스 내장 `/dev/usbtmc*`를 통해 직접 제어가 가능합니다.

### 6.4. 통신 포트 장치 접근 권한 부여 (Permission Settings)

직렬 포트(RS-485 to USB 등)를 통해 라돈, 온습도, 화재 센서 등에 접근하려면, RENE-PM을 실행하는 리눅스 사용자 계정에 시리얼 통신 접근 권한이 있어야 합니다. (권한 부족 시 Permission Denied 에러 발생)

```bash
sudo usermod -aG dialout $USER
sudo usermod -aG lock $USER
# 권한 적용을 위해 시스템 로그아웃 후 재로그인 필요

```

---

## 7. 환경 설정 파일 구조 (Configuration Files)

시스템의 핵심 설정은 소스 코드 내부의 하드코딩을 철저히 배제하고 외부 JSON 파일을 통해 단일 진실 공급원(SSOT)으로 관리됩니다.

* **`config_v3.json` (메인 환경설정):** 데이터베이스 연결 정보, 하드웨어 IP/Port, 장비별 활성화 여부(`enabled`), 폴링 주기 등을 설정합니다. 프로그램 구동 시 이 파일이 없을 경우 하위 호환성을 위해 자동으로 `config_v2.json`을 폴백(Fallback)으로 로드합니다.
* **`sop.json` (표준 운영 절차 데이터):** 안전 패널(Safety Panel)에 표시되는 비상 상황 단계별 대응 절차와 비상 연락망(Emergency Contacts)을 정의합니다. 최초 실행 시 루트 폴더에 기본 템플릿이 자동 생성되며, 언제든 텍스트 에디터로 현장 규칙에 맞게 내용을 수정하여 UI에 동적으로 반영시킬 수 있습니다.

---


## 8. 디렉터리 구조 및 단일 책임 원칙 (Directory Structure & SRP)

RENE-PM v3.0은 객체 지향 프로그래밍의 핵심인 관심사의 분리(Separation of Concerns)와 단일 책임 원칙(Single Responsibility)에 따라 철저하게 역할이 분리된 디렉터리 구조를 갖습니다.

```text
RENE_PM_V3/
├── main.py                  # 엔트리 포인트 (의존성 주입, 타이머 귀속, 이벤트 루프 실행)
├── config_v3.json           # 시스템 통합 설정 파일 (단일 진실 공급원 - SSOT)
├── sop.json                 # 비상 대응 절차 및 연락망 동적 구성 파일
├── notes.md                 # Markdown 기반 실험실 작업 일지
│
├── core/                    # [데이터 및 통신망 계층]
│   ├── event_bus.py         # 모듈 간 결합도를 0으로 만드는 글로벌 Pub/Sub 라우터
│   └── state_store.py       # O(1) 복잡도를 보장하는 링 버퍼 기반 대용량 센서 상태 저장소
│
├── experts/                 # [상황 판단 및 스레드 관리 계층]
│   ├── safety_expert.py     # 센서 데이터를 평가하여 비상 상황(SOP)을 결정하는 자율 룰 엔진
│   └── worker_manager.py    # 스레드 생명주기 관리 및 런타임 핫스왑 동적 제어
│
├── workers/                 # [I/O 및 영속성 계층] (순수 백그라운드 구동)
│   ├── daq_worker.py, ...   # 하드웨어 통신 프로토콜을 전담하는 백그라운드 데몬 스레드들
│   └── database_worker.py   # 메인 렌더링 루프와 완전히 격리된 DB Batch Insert 전용 데몬
│
└── views/                   # [표현 계층 - 수동적 뷰 패턴]
    ├── main_window.py       # 전체 윈도우 레이아웃 및 탭 라우팅 조립
    ├── components/          # 대시보드(Dashboard) 및 HV 상태 그리드 등 재사용 UI 조각
    └── panels/              # EventBus 신호에만 반응하여 렌더링을 수행하는 수동적 뷰 패널들

```

## 9. 수동적 뷰 패턴 및 렌더링 최적화 (Passive View Pattern)

GUI 컴포넌트(`views/` 하위)는 자체적인 타이머를 난립시키거나, 하드웨어 데이터 가공, 연산 로직을 일절 갖지 않는 철저한 '수동적 뷰(Passive View)'로 설계되었습니다.

* **GUI 렌더링 틱(Tick) 동기화:** 수십 개의 시계열 그래프가 각자의 타이머로 화면을 갱신하면 Qt 렌더링 파이프라인에 엄청난 병목 현상이 발생합니다. V3.0에서는 메인 윈도우에 귀속된 단 하나의 글로벌 타이머가 500ms 주기로 `ui_update_requested` 시그널을 발행합니다. 모든 그래프 패널(`EnvPanel`, `HVGraphPanel`)은 일제히 이에 동기화되어 `StateStore` 내 변경 플래그(`plot_dirty_flags`)가 있는 데이터만 찾아 화면을 갱신합니다. 이를 통해 화면 끊김(Stuttering) 현상을 근절했습니다.
* **완벽한 UI 반응성 보장:** 사용자가 'PDU Control'이나 'HV Control' 탭에서 버튼을 누르면, UI는 즉시 자신의 버튼을 비활성화하고 `EventBus`로 명령 딕셔너리만 던진 후 렌더링을 계속합니다. 통신과 하드웨어 제어는 백그라운드 스레드가 알아서 수행하며, 그 결과가 돌아올 때 비로소 UI 라벨이 업데이트됩니다.

## 10. 고성능 데이터베이스 영속성 (High-Performance Data Persistence)

매초 생성되는 하드웨어 데이터를 디스크(DB)에 기록하는 과정은 UI 프레임 드랍(렉)의 가장 큰 원인입니다. 이를 원천 차단하기 위해 V3.0은 **완벽한 비동기 일괄(Batch) 처리 구조**를 도입했습니다.

1. **메모리 큐 버퍼링:** 하드웨어 워커들은 측정 즉시 DB 서버에 접근하지 않습니다. 데이터를 `(타입, 튜플)` 형태로 스레드-안전(Thread-Safe)한 객체인 `queue.Queue`에 가볍게 던져놓고 즉시 본연의 측정 루프로 돌아갑니다.
2. **60초 주기 일괄 삽입:** 독립된 데몬인 `DatabaseWorker` 스레드가 정확히 1분(60초)마다 깨어납니다. 큐에 쌓여 있는 데이터(HV 96채널 전체 + 각종 환경 센서 등 약 100여 건)를 단 한 번에 꺼내어 MariaDB의 `executemany` 명령으로 밀어 넣습니다. 단일 트랜잭션으로 디스크 I/O를 최소화합니다.
3. **장애 복구 (Fault Tolerance):** 데이터베이스 서버 순단(네트워크 단절 등)으로 인해 삽입 중 `mariadb.Error`가 발생하면, 즉시 작업을 중단하고 트랜잭션을 롤백(Rollback)합니다. 실패한 데이터는 큐에 안전하게 보존되므로, 다음 분(Minute)에 연결이 복구되면 이전 데이터까지 100% 누락 없이 밀어 넣습니다.

## 11. 트러블슈팅: 코어 덤프 방지 설계 (Thread Safety & Core Dump Prevention)

리눅스 및 PyQt 환경에서 메인 창을 닫을 때 프로그램이 비정상 종료되며 `QObject::killTimer: Timers cannot be stopped from another thread` 등의 예외(세그멘테이션 오류)를 뱉는 것은 고질적인 문제였습니다. V3.0은 스레드의 특성에 따라 종료 시퀀스를 이원화하여 이 교착상태를 완벽하게 해결했습니다.

* **무한 루프(While) 기반 워커 (`daq`, `magnetometer` 등):** 클래스 내부의 제어 플래그(`_is_running = False`)를 즉시 변경하여, 워커 스스로 루프를 탈출하고 하드웨어 자원을 반환하도록 부드럽게 유도합니다.
* **QTimer 기반 워커 (`caen_hv`, `database` 등):** 메인 스레드에서 타 스레드 내부에 있는 타이머 객체를 강제로 끄면 코어 덤프가 발생합니다. 대신 `QMetaObject.invokeMethod(..., Qt.ConnectionType.QueuedConnection)` 메서드를 활용하여, "네 타이머를 직접 끄렴" 이라는 메시지를 워커 스레드의 자체 이벤트 루프에 비동기적으로 우편 발송(Queued)합니다.
* **데드락 회피 (Hung Detection):** 하드웨어 타임아웃으로 인해 스레드가 반환되지 않을 수 있으므로, 메인 스레드는 `wait(3000)` 명령으로 최대 3초의 유예 기간을 주며, 응답이 없으면 시스템 보호를 위해 즉시 스레드 메모리를 강제 회수(`terminate`)하고 애플리케이션을 깔끔하게 종료합니다.

## 12. 제어 시그널 라우팅 명세 (Core Signal Routing)

시스템 내 결합도를 0으로 유지하는 `EventBus`의 핵심 시그널 규격은 다음과 같습니다. 기능 확장 시 반드시 아래의 룰을 지켜야 합니다.

* `sensor_data_updated(str sensor_type, dict payload)`: 워커 스레드가 데이터를 획득하면 송출합니다. `StateStore`가 이를 수신해 링 버퍼를 갱신하고, 대시보드 UI가 실시간 수치를 업데이트하며, `SafetyExpert`가 비상 상황을 감지합니다.
* `system_log_message(str level, str message)`: 시스템 전역의 상태나 오류를 발행합니다. `main.py`에 적용된 `LogToEventBusHandler`를 통해 터미널에 찍히는 모든 표준 출력 또한 이 시그널을 거쳐 GUI의 **📜 Logs** 패널에 동기화 표출됩니다.
* `cmd_hv_control(dict command)` / `cmd_toggle_worker(str worker_name, bool enable)`: UI 패널에서 하드웨어를 제어하거나 핫스왑을 요청할 때 발행합니다. 이 시그널들은 `WorkerManager`로 라우팅되어 백그라운드의 활성화된 워커 스레드로 비동기 전달됩니다.

## 13. 향후 모듈 확장 가이드 (Extensibility Guidelines)

새로운 종류의 측정 하드웨어를 시스템에 추가하는 절차는 기존 메인 코드를 단 한 줄도 수정하지 않는 철저한 '개방-폐쇄 원칙(OCP)'을 따릅니다.

1. `workers/` 디렉터리에 `QObject`를 상속받는 하드웨어 통신 전담 클래스를 작성합니다. (예: `new_sensor_worker.py`)
2. 수집된 데이터를 `global_bus.sensor_data_updated.emit()`을 통해 지식망으로 방송합니다.
3. `core/state_store.py`의 고정 2D NumPy 배열 선언부에 해당 센서가 기록될 공간을 할당합니다.
4. `workers/database_worker.py`의 `TABLE_SCHEMAS` 리스트에 새 테이블 생성 쿼리를 추가합니다.
5. `experts/worker_manager.py`의 `worker_map` 딕셔너리에 새 워커 클래스 이름을 등록하고, `config_v3.json`에 장비 연결 속성과 `"enabled": true` 속성을 추가하면 즉시 작동을 시작합니다.

---

## 14. 사사 및 감사의 글 (Acknowledgements) 🇰🇷

본 정밀 중성미자 탐색을 위한 고성능 통합 모니터링 시스템(RENE-PM v3.0) 아키텍처의 혁신적 재설계와 고도화 개발은 **한국연구재단(NRF)의 연구비 지원**을 바탕으로 수행되었습니다.

현대 고에너지 입자 물리학과 국가 기초 과학 인프라의 발전을 위해, 보이지 않는 곳에서도 소중한 국민의 혈세(세금)를 아낌없이 지원해 주시는 **대한민국 국민 여러분들께** 연구진을 대표하여 머리 숙여 깊은 감사의 말씀을 올립니다.

우주의 근원을 탐구하고 지식의 경계를 넓히는 기초 과학의 위대한 여정은 오직 국민적 공감대와 헌신적인 뒷받침 없이는 결코 이루어질 수 없습니다. 

*(This work was supported by the research grant from the Government of the Republic of Korea. We express our deepest gratitude to the citizens and the government for their invaluable support in advancing fundamental science and high-energy physics research.)*
