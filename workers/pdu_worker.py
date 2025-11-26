# workers/pdu_worker.py

import time
import logging
from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer
from pymodbus.client import ModbusTcpClient
# [v2.1 수정] ConnectionException 명시적 임포트
from pymodbus.exceptions import ModbusException, ConnectionException

# Modbus TCP Slave ID. NETIO 장비는 일반적으로 1을 사용합니다.
# [v2.1 수정] pymodbus 3.0+ 호환성을 위해 변수명 변경 및 'slave' 파라미터 사용
MODBUS_SLAVE_ID = 1 

class PDUWorker(QObject):
    # 시그널 정의
    sig_status_updated = pyqtSignal(dict)       # GUI 업데이트용 전체 상태 데이터
    sig_log_message = pyqtSignal(str, str)      # (level, message) GUI 로그창 표시용
    sig_connection_changed = pyqtSignal(bool)   # 연결 상태 변경 시그널
    sig_queue_data = pyqtSignal(dict)           # DB 저장용 데이터 패킷
    finished = pyqtSignal()                     # 워커 종료 시그널

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.ip = self.config.get('ip_address')
        self.port = self.config.get('port', 502)
        self.timeout = self.config.get('timeout_sec', 3)
        self.polling_interval_ms = self.config.get('polling_interval_sec', 5) * 1000
        self.logger = logging.getLogger(__name__)

        self.is_running = False
        self.is_connected = None # None (초기상태), True, False

    def get_client(self):
        """요구사항 1 준수: Modbus 클라이언트 객체를 매번 생성하여 반환"""
        return ModbusTcpClient(self.ip, port=self.port, timeout=self.timeout)

    @pyqtSlot()
    def start_worker(self):
        """스레드 시작 시 호출됨 (QThread.started 시그널에 연결)"""
        if not self.is_running:
            self.is_running = True
            # QTimer를 사용하여 워커 스레드의 이벤트 루프에서 주기적 작업 수행
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.poll_data)
            self.timer.start(self.polling_interval_ms)
            self.sig_log_message.emit("INFO", f"PDU Worker started. Polling {self.ip}...")
            self.poll_data() # 시작 시 즉시 폴링 수행

    @pyqtSlot()
    def stop_worker(self):
        """워커 종료 처리 (애플리케이션 종료 시 QMetaObject.invokeMethod로 호출됨)"""
        if self.is_running:
            self.is_running = False
            if hasattr(self, 'timer'):
                self.timer.stop()
            self.sig_log_message.emit("INFO", "PDU Worker stopping.")
            # 종료 시 연결 상태를 False로 설정 (force_log=False로 설정하여 불필요한 로그 억제)
            self.set_connection_status(False, force_log=False) 
        self.finished.emit() # 스레드 종료를 위한 시그널 발생

    def set_connection_status(self, status, force_log=True):
        # 상태가 변경되었을 때만 시그널 발생
        if self.is_connected != status:
            # 이전 상태 저장
            previous_status = self.is_connected
            self.is_connected = status
            self.sig_connection_changed.emit(status)
            
            # 연결 상태 변경 시 로그 출력 (초기 상태(None)가 아닐 때만)
            if force_log and previous_status is not None:
                if status:
                    self.sig_log_message.emit("INFO", "PDU Reconnected.")
                else:
                    self.sig_log_message.emit("ERROR", "PDU Connection Lost.")

    @pyqtSlot()
    def poll_data(self):
        """주기적으로 PDU 상태를 읽어옵니다. (Modbus 통신)"""
        if not self.is_running: return

        data_gui = {'global': {}, 'outputs': {}}
        db_payloads = []
        timestamp = datetime.now()
        # MariaDB DATETIME(3) 형식
        timestamp_db = timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        # 요구사항 1 준수: with 구문 사용
        try:
            with self.get_client() as client:
                if not client.connect():
                    # 연결 실패 시 로그 출력 및 상태 변경
                    self.sig_log_message.emit("WARNING", "Failed to connect to PDU for polling.")
                    self.set_connection_status(False)
                    return

                self.set_connection_status(True)

                # --- 데이터 읽기 (요구사항 2: 주소 매핑 준수) ---
                # [v2.1 수정] pymodbus 3.0+ 호환성을 위해 unit -> slave로 변경
                
                # 1. Global Data (Freq:0, Volt:1)
                rr_gv = client.read_input_registers(address=0, count=2, slave=MODBUS_SLAVE_ID)
                # 2. Total Power (Addr 200)
                rr_gp = client.read_input_registers(address=200, count=1, slave=MODBUS_SLAVE_ID)
                
                if rr_gv and not rr_gv.isError() and rr_gp and not rr_gp.isError():
                    data_gui['global']['freq'] = rr_gv.registers[0] / 100.0
                    data_gui['global']['volt'] = rr_gv.registers[1] / 10.0
                    data_gui['global']['power'] = rr_gp.registers[0]
                else:
                    self.sig_log_message.emit("ERROR", f"Failed to read PDU Global data. GV:{rr_gv}, GP:{rr_gp}")
                    return

                # 3. Port Data 읽기
                # Status (Coils 101~108)
                rr_states = client.read_coils(address=101, count=8, slave=MODBUS_SLAVE_ID)
                # Current (mA) (InputReg 101~108)
                rr_curr = client.read_input_registers(address=101, count=8, slave=MODBUS_SLAVE_ID)
                # Power (W) (InputReg 201~208)
                rr_watts = client.read_input_registers(address=201, count=8, slave=MODBUS_SLAVE_ID)
                # Energy (Wh) (InputReg 301~308, NETIO 표준 주소 가정)
                rr_energy = client.read_input_registers(address=301, count=8, slave=MODBUS_SLAVE_ID)

                if (not rr_states or rr_states.isError() or 
                    not rr_curr or rr_curr.isError() or 
                    not rr_watts or rr_watts.isError()):
                    self.sig_log_message.emit("ERROR", "Failed to read PDU Port data (Status, Current, or Power).")
                    return

                # --- 데이터 파싱 ---
                for i in range(8):
                    port_num = i + 1
                    # Coils는 bits 리스트의 앞부분만 사용
                    if len(rr_states.bits) > i:
                        state_bool = rr_states.bits[i]
                    else:
                        state_bool = False # 응답 길이 오류 시 기본값

                    current_ma = rr_curr.registers[i]
                    power_w = rr_watts.registers[i]
                    
                    # Energy 데이터 처리 (펌웨어 버전에 따라 지원 안될 수 있으므로 선택적 처리)
                    if rr_energy and not rr_energy.isError() and len(rr_energy.registers) > i:
                         energy_wh = rr_energy.registers[i]
                    else:
                         energy_wh = 0.0 # 실패 시 0으로 처리


                    # GUI용 데이터 저장
                    data_gui['outputs'][port_num] = {
                        'state_bool': state_bool,
                        'power': power_w,
                        'current': current_ma,
                        'energy': energy_wh
                    }
                    
                    # DB용 데이터 저장 (DatabaseWorker의 처리 방식에 맞춘 튜플 형식)
                    # DB 스키마에 맞춰 power_w와 energy_wh는 float으로 전달
                    db_payloads.append((timestamp_db, port_num, state_bool, float(power_w), current_ma, float(energy_wh)))
                
                # 데이터 처리 완료 후 시그널 발생
                self.sig_status_updated.emit(data_gui)
                # DB 큐로 데이터 전송
                if db_payloads:
                    self.sig_queue_data.emit({'type': 'PDU', 'data': db_payloads})

        # [v2.1 수정] 에러 로깅 강화
        except ConnectionException as e:
             # Errno 104 (Connection reset by peer) 등 네트워크 오류 처리
             self.logger.error(f"PDU Connection Error during polling: {e}")
             self.sig_log_message.emit("CRITICAL", f"Connection Error during polling: {e}")
             self.set_connection_status(False)
        except ModbusException as e:
            self.logger.error(f"Modbus Exception during PDU polling: {e}")
            self.sig_log_message.emit("CRITICAL", f"Modbus Exception during polling: {e}")
            self.set_connection_status(False)
        except Exception as e:
             self.logger.error(f"Unexpected Exception during PDU polling: {e}", exc_info=True)
             self.sig_log_message.emit("CRITICAL", f"Unexpected Exception during polling: {e}")
             self.set_connection_status(False)


    @pyqtSlot(int, bool)
    def control_single_port(self, port_num, state):
        """[슬롯] 개별 포트 제어 요청을 처리합니다."""
        if not (1 <= port_num <= 8): return

        address = 100 + port_num
        action_str = "ON" if state else "OFF"
        self.sig_log_message.emit("INFO", f"Attempting to turn Port {port_num} {action_str}...")

        try:
            # 요구사항 1 준수: with 구문 사용
            with self.get_client() as client:
                if not client.connect():
                    self.sig_log_message.emit("ERROR", f"Failed to connect for control (Port {port_num}).")
                    return
                
                # 코일 쓰기 (write_coil)
                # [v2.1 수정] pymodbus 3.0+ 호환성을 위해 unit -> slave로 변경
                result = client.write_coil(address=address, value=state, slave=MODBUS_SLAVE_ID)
                if result and not result.isError():
                    self.sig_log_message.emit("SUCCESS", f"✅ Port {port_num} successfully turned {action_str}.")
                    # 제어 후 상태 즉시 갱신 요청 (0.5초 후)
                    QTimer.singleShot(500, self.poll_data)
                else:
                    self.sig_log_message.emit("ERROR", f"❌ Failed to control Port {port_num}. Modbus Error: {result}")

        # [v2.1 수정] 에러 로깅 강화
        except ConnectionException as e:
             self.logger.error(f"PDU Connection Error during single port control: {e}")
             self.sig_log_message.emit("CRITICAL", f"Connection Error during control: {e}")
        except Exception as e:
            self.logger.error(f"Exception during PDU single port control: {e}", exc_info=True)
            self.sig_log_message.emit("CRITICAL", f"Exception during single port control: {e}")

    @pyqtSlot(bool)
    def control_all_ports(self, state):
        """[슬롯] 일괄 포트 제어 요청을 처리합니다. (딜레이 포함)"""
        action_str = "ON" if state else "OFF"
        self.sig_log_message.emit("INFO", f"🚀 Starting sequence to turn ALL ports {action_str}...")

        try:
            with self.get_client() as client:
                if not client.connect():
                    self.sig_log_message.emit("ERROR", "Failed to connect for ALL control.")
                    return

                for i in range(8):
                    port_num = i + 1
                    address = 100 + port_num
                    
                    # [v2.1 수정] pymodbus 3.0+ 호환성을 위해 unit -> slave로 변경
                    result = client.write_coil(address=address, value=state, slave=MODBUS_SLAVE_ID)
                    
                    if result and result.isError():
                         self.sig_log_message.emit("WARNING", f"Failed setting Port {port_num} during ALL control. Error: {result}")
                    
                    # 요구사항 3 준수 및 [v2.1 수정] 딜레이 소폭 증가 (0.1초 -> 0.15초)
                    time.sleep(0.15)
                
                self.sig_log_message.emit("SUCCESS", f"✨ ALL ports {action_str} sequence complete.")
                QTimer.singleShot(500, self.poll_data)

        # [v2.1 수정] 에러 로깅 강화
        except ConnectionException as e:
             # Errno 104 발생 가능성 높음
             self.logger.error(f"PDU Connection Error during all port control: {e}")
             self.sig_log_message.emit("CRITICAL", f"Connection Error during ALL control (Device might be busy): {e}")
        except Exception as e:
            self.logger.error(f"Exception during PDU all port control: {e}", exc_info=True)
            self.sig_log_message.emit("CRITICAL", f"Exception during all port control: {e}")