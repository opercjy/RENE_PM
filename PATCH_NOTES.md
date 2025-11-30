# RENE-PM Patch Notes (Changelog)

## [v2.1.9] - 2025-11-30 (Latest)
### UI/UX 개선 및 최적화
* **하단 대시보드 레이아웃 재구성:**
    * 센서 그룹을 10개로 세분화 (Flame, VOC 독립 분리).
    * `UPS`와 `HV System` 그룹 분리. `HV Power` 상태는 UPS 그룹으로 이동하고, HV 그룹은 보드 온도(`Board Temps`)만 표시하도록 변경.
* **상태 표시 시인성 강화:**
    * HV 보드 온도에 색상 로직 적용 (🟢정상 < 50°C, 🟠주의 < 65°C, 🔴위험).
    * 자기장(Magnetometer) 성분별(Bx, By, Bz, |B|) 텍스트 색상을 그래프 선 색상과 일치시킴.
* **SOP 가이드 초기화:** 프로그램 시작 시 'Initializing...' 대신 기본 **[NORMAL]** 단계 가이드를 즉시 표시.

## [v2.1.5 ~ v2.1.8] - UI 스타일링 및 안전성 강화
* **가독성 향상:** 애플리케이션 전체 기본 폰트 크기를 **12pt**로 상향 조정.
* **탭 바 최적화 (Compact Tabs):** 탭 너비와 여백을 줄여 스크롤 없이 모든 탭이 한 화면에 들어오도록 개선.
* **설정 유연화:** VOC 감지기의 경고/위험 임계값(`thresholds`)을 `config_v2.json`에서 설정할 수 있도록 변경.
* **SOP HTML 강화:** 안전 탭의 SOP 가이드에 **비상 연락망(Contact Info)** 섹션을 추가하고, 상황별(Normal/Warning/Emergency) 스타일을 동적으로 적용.

## [v2.1.0 ~ v2.1.4] - 하드웨어 통합 및 기능 확장
### 신규 기능 (New Features)
* **고급 안전 탭 (Advanced Safety Tab):**
    * 화재(FS24X Plus) 및 유해가스(RAEGuard2 PID) 감지기 통합 모니터링.
    * 실시간 위험도에 따른 **신호등(Traffic Light) UI** 및 동적 SOP 가이드 제공.
    * VOC 농도 및 화재 센서 아날로그 레벨에 대한 실시간 트렌드 그래프 추가.
* **NETIO PowerPDU 8KF 통합:**
    * Modbus TCP를 이용한 PDU 원격 제어(개별/일괄 ON/OFF) 탭 신설.
    * 포트별 전력(W), 전류(mA), 에너지(Wh) 실시간 모니터링 및 DB 로깅.

### 버그 수정 (Bug Fixes)
* **종료 안정성 확보:** 애플리케이션 종료 시 `sip.isdeleted()` 체크를 통해 스레드 충돌(`RuntimeError`) 방지.
* **Modbus 호환성:** `pymodbus` v3.x 호환성을 위해 파라미터 명칭 수정 (`unit` -> `slave`).
* **설정 파일 오류 해결:** JSON 표준을 준수하기 위해 주석(`#`) 제거 및 `comments` 필드로 대체.
* **초기화 순서 수정:** GUI 로딩 후 워커가 시작되도록 `delayed_init` 도입하여 초기 로그 누락 방지.

---

## [v2.0.0] - Initial Release
* 초기 PyQt5 아키텍처 및 기본 환경 센서(cDAQ, Arduino 등) 모니터링 구축.
