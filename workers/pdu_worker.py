# workers/pdu_worker.py

import time
import logging
from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException, ConnectionException

# Modbus TCP Slave ID
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
        self.is_connected = None

    def get_client(self):
        """요구사항 1 준수: Modbus 클라이언트 객체를 매번 생성하여 반환"""
        return ModbusTcpClient(self.ip, port=self.port, timeout=self.timeout)

    @pyqtSlot()
    def start_worker(self):
        """스레드 시작 시 호출됨"""
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
        """워커 종료 처리"""
        if self.is_running:
            self.is_running = False
            if hasattr(self, 'timer'):
                self.timer.stop()
            self.sig_log_message.emit("INFO", "PDU Worker stopping.")
            # 종료 시 연결 상태를 False로 설정
            self.set_connection_status(False, force_log=False) 
        self.finished.emit() # 스레드 종료를 위한 시그널 발생

    def set_connection_status(self, status, force_log=True):
        # 상태가 변경되었을 때만 시그널 발생
        if self.is_connected != status:
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

        try:
            with self.get_client() as client:
                if not client.connect():
                    self.sig_log_message.emit("WARNING", "Failed to connect to PDU for polling.")
                    self.set_connection_status(False)
                    return

                self.set_connection_status(True)

                # --- 데이터 읽기 ---
                
                # 1. Global Data (Freq:0, Volt:1)
                rr_gv = client.read_input_registers(address=0, count=2, slave=MODBUS_SLAVE_ID)
                # 2. Total Power (Addr 200)
                rr_gp = client.read_input_registers(address=200, count=1, slave=MODBUS_SLAVE_ID)
                
                if rr_gv and not rr_gv.isError() and rr_gp and not rr_gp.isError():
                    data_gui['global']['freq'] = rr_gv.registers[0] / 100.0
                    data_gui['global']['volt'] = rr_gv.registers[1] / 10.0
                    data_gui['global']['power'] = rr_gp.registers[0]
                
                # 3. Port Data Values (전류, 전력, 에너지는 일괄 읽기 유지)
                # Current (mA) (InputReg 101~108)
                rr_curr = client.read_input_registers(address=101, count=8, slave=MODBUS_SLAVE_ID)
                # Power (W) (InputReg 201~208)
                rr_watts = client.read_input_registers(address=201, count=8, slave=MODBUS_SLAVE_ID)
                # Energy (Wh) (InputReg 301~308)
                rr_energy = client.read_input_registers(address=301, count=8, slave=MODBUS_SLAVE_ID)

                if (not rr_curr or rr_curr.isError() or not rr_watts or rr_watts.isError()):
                    self.sig_log_message.emit("ERROR", "Failed to read PDU Port Measurement data.")
                    return

                # --- 데이터 파싱 (상태값 개별 읽기 적용) ---
                for i in range(8):
                    port_num = i + 1
                    
                    # [핵심 수정] 상태값 개별 읽기 (Address: 101, 102... 순차 접근)
                    # 비트 밀림 방지 및 4kf/8kf 모델 호환성 확보
                    try:
                        # Coil 주소는 100 + 포트번호 (101, 102...)
                        rr_state_single = client.read_coils(address=100 + port_num, count=1, slave=MODBUS_SLAVE_ID)
                        if rr_state_single and not rr_state_single.isError():
                            state_bool = rr_state_single.bits[0]
                        else:
                            # 읽기 실패 시 전력값이 있으면 ON으로 간주 (안전장치)
                            state_bool = (rr_watts.registers[i] > 0)
                    except Exception:
                        state_bool = False

                    current_ma = rr_curr.registers[i]
                    power_w = rr_watts.registers[i]
                    
                    # Energy 데이터 처리
                    if rr_energy and not rr_energy.isError() and len(rr_energy.registers) > i:
                         energy_wh = rr_energy.registers[i]
                    else:
                         energy_wh = 0.0

                    # GUI용 데이터 저장
                    data_gui['outputs'][port_num] = {
                        'state_bool': state_bool,
                        'power': power_w,
                        'current': current_ma,
                        'energy': energy_wh
                    }
                    
                    # DB용 데이터 저장
                    db_payloads.append((timestamp_db, port_num, state_bool, float(power_w), current_ma, float(energy_wh)))
                
                # 데이터 처리 완료 후 시그널 발생
                self.sig_status_updated.emit(data_gui)
                # DB 큐로 데이터 전송
                if db_payloads:
                    self.sig_queue_data.emit({'type': 'PDU', 'data': db_payloads})

        except ConnectionException as e:
             self.logger.error(f"PDU Connection Error during polling: {e}")
             self.sig_log_message.emit("CRITICAL", f"Connection Error: {e}")
             self.set_connection_status(False)
        except ModbusException as e:
            self.logger.error(f"Modbus Exception during PDU polling: {e}")
            self.sig_log_message.emit("CRITICAL", f"Modbus Exception: {e}")
            self.set_connection_status(False)
        except Exception as e:
             self.logger.error(f"Unexpected Exception during PDU polling: {e}", exc_info=True)
             self.sig_log_message.emit("CRITICAL", f"Polling Error: {e}")
             self.set_connection_status(False)

    @pyqtSlot(int, bool)
    def control_single_port(self, port_num, state):
        """[슬롯] 개별 포트 제어 요청을 처리합니다."""
        if not (1 <= port_num <= 8): return

        address = 100 + port_num
        action_str = "ON" if state else "OFF"
        self.sig_log_message.emit("INFO", f"Attempting to turn Port {port_num} {action_str}...")

        try:
            with self.get_client() as client:
                if not client.connect():
                    self.sig_log_message.emit("ERROR", f"Failed to connect for control (Port {port_num}).")
                    return
                
                result = client.write_coil(address=address, value=state, slave=MODBUS_SLAVE_ID)
                if result and not result.isError():
                    self.sig_log_message.emit("SUCCESS", f"[OK] Port {port_num} successfully turned {action_str}.")
                    # 제어 후 상태 즉시 갱신 요청 (0.5초 후)
                    QTimer.singleShot(500, self.poll_data)
                else:
                    self.sig_log_message.emit("ERROR", f"[ERR] Failed to control Port {port_num}. Modbus Error: {result}")

        except ConnectionException as e:
             self.logger.error(f"PDU Connection Error during single port control: {e}")
             self.sig_log_message.emit("CRITICAL", f"Connection Error during control: {e}")
        except Exception as e:
            self.logger.error(f"Exception during PDU single port control: {e}", exc_info=True)
            self.sig_log_message.emit("CRITICAL", f"Exception during control: {e}")

    @pyqtSlot(bool)
    def control_all_ports(self, state):
        """[슬롯] 일괄 포트 제어 요청을 처리합니다."""
        action_str = "ON" if state else "OFF"
        self.sig_log_message.emit("INFO", f"[INFO] Starting sequence to turn ALL ports {action_str}...")

        try:
            with self.get_client() as client:
                if not client.connect():
                    self.sig_log_message.emit("ERROR", "Failed to connect for ALL control.")
                    return

                for i in range(8):
                    port_num = i + 1
                    address = 100 + port_num
                    
                    result = client.write_coil(address=address, value=state, slave=MODBUS_SLAVE_ID)
                    
                    if result and result.isError():
                         self.sig_log_message.emit("WARNING", f"Failed setting Port {port_num} during ALL control.")
                    
                    # 딜레이 유지
                    time.sleep(0.15)
                
                self.sig_log_message.emit("SUCCESS", f"[DONE] ALL ports {action_str} sequence complete.")
                QTimer.singleShot(500, self.poll_data)

        except ConnectionException as e:
             self.logger.error(f"PDU Connection Error during all port control: {e}")
             self.sig_log_message.emit("CRITICAL", f"Connection Error during ALL control: {e}")
        except Exception as e:
            self.logger.error(f"Exception during PDU all port control: {e}", exc_info=True)
            self.sig_log_message.emit("CRITICAL", f"Exception during all port control: {e}")
