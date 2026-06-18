# core/event_bus.py

from PyQt6.QtCore import QObject, pyqtSignal

class EventBus(QObject):
    """
    [거대 지식망 (Knowledge Network)]
    시스템 전체의 통신을 담당하는 글로벌 Pub/Sub 라우터.
    어떤 모듈도 서로를 직접 참조하지 않고 오직 EventBus를 통해서만 소통합니다.
    """
    
    # ==========================================
    # 1. 센서 데이터 이벤트 (생산자 -> 지식망 -> 저장소/UI)
    # ==========================================
    # sensor_type: 'daq_avg', 'radon_raw', 'ups_status', 'hv_status' 등
    # data: 실제 센서값 딕셔너리
    sensor_data_updated = pyqtSignal(str, dict)
    
    # 장비 연결 상태 알림 (HardwareManager 또는 Worker -> UI)
    device_connection_changed = pyqtSignal(str, bool)

    # ==========================================
    # 2. 시스템 상태 및 로깅 (전문가/워커 -> 지식망 -> UI)
    # ==========================================
    # level: "INFO", "WARNING", "ERROR", "CRITICAL"
    system_log_message = pyqtSignal(str, str)
    
    # phase: "NORMAL", "WARNING", "EMERGENCY"
    # html_msg: SOP 가이드에 표시할 텍스트
    safety_status_changed = pyqtSignal(str, str)
    
    # 라돈 센서 특수 상태 (측정 대기시간 등)
    radon_status_updated = pyqtSignal(str, int)

    # ==========================================
    # 3. 제어 명령 이벤트 (UI/안전전문가 -> 지식망 -> 하드웨어 워커)
    # ==========================================
    # CAEN HV 제어 (type: set_power/set_params, slot, channels, value/params)
    cmd_hv_control = pyqtSignal(dict)
    request_hv_setpoints = pyqtSignal(int, int) # slot, channel
    hv_setpoints_ready = pyqtSignal(dict)       # 응답
    
    # PDU 제어
    cmd_pdu_control_single = pyqtSignal(int, bool) # port_num, state
    cmd_pdu_control_all = pyqtSignal(bool)         # state

    # ==========================================
    # 4. 시스템 제어 및 동기화 이벤트
    # ==========================================
    # 하드웨어 워커 핫스왑 명령 (worker_name, is_enabled)
    cmd_toggle_worker = pyqtSignal(str, bool)

    # GUI 동기화 틱 (Tick)
    ui_update_requested = pyqtSignal()

# 애플리케이션 전역에서 사용할 싱글톤 인스턴스
global_bus = EventBus()