import time
import logging
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer

class FireWorker(QObject):
    data_ready = pyqtSignal(dict)
    status_update = pyqtSignal(str, bool) # status_msg, is_fire_alarm
    error_occurred = pyqtSignal(str)

    def __init__(self, config, data_queue):
        super().__init__()
        self.config = config
        self.data_queue = data_queue
        self.client = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.measure)
        self.interval = int(config.get('interval_s', 1.0) * 1000)
        self._is_running = False

    @pyqtSlot()
    def start_worker(self):
        try:
            self.client = ModbusSerialClient(
                port=self.config['port'], 
                baudrate=self.config.get('baudrate', 19200), 
                parity='N', stopbits=1, bytesize=8, timeout=1
            )
            if not self.client.connect():
                raise ConnectionError(f"Failed to connect to {self.config['port']}")
            
            self._is_running = True
            self.timer.start(self.interval)
            logging.info(f"FireWorker (FS24X) started on {self.config['port']}")
        except Exception as e:
            self.error_occurred.emit(f"Fire Detector Error: {e}")

    def measure(self):
        if not self._is_running: return
        try:
            ts = time.time()
            slave_id = self.config.get('slave_id', 1)
            # FS24X 레지스터: 매뉴얼 Appendix 6 참조 (보통 40001 근처)
            # 설정 파일에서 지정한 status_register (기본 40001) 읽기
            reg_addr = self.config.get('status_register', 40001) - 40001
            
            # Holding Register 읽기
            rr = self.client.read_holding_registers(address=reg_addr, count=1, slave=slave_id)
            
            if rr.isError():
                raise ModbusException(f"Modbus Error: {rr}")

            status_val = rr.registers[0]
            
            # 비트 마스킹 (FS24X 일반적인 비트맵, 실제 매뉴얼 확인 필요)
            # 예: Bit 0=Fault, Bit 1=Warning, Bit 2=Alarm
            is_fault = bool(status_val & 0x0001)
            is_fire = bool(status_val & 0x0004) or bool(status_val & 0x0008) # 예시 비트

            status_str = "NORMAL"
            if is_fire: status_str = "FIRE ALARM"
            elif is_fault: status_str = "FAULT"

            data = {
                'fire_detector': {
                    'status_code': status_val,
                    'is_fire': is_fire,
                    'is_fault': is_fault,
                    'msg': status_str
                }
            }
            
            self.data_ready.emit(data)
            self.status_update.emit(status_str, is_fire)
            self._enqueue_db_data(ts, status_val, is_fire, is_fault)

        except Exception as e:
            self.error_occurred.emit(f"Fire Detector Comm Error: {e}")
            # 일시적 오류 시 재접속 시도 로직 등을 추가할 수 있음

    def _enqueue_db_data(self, ts, code, fire, fault):
        dt_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
        self.data_queue.put({'type': 'FIRE', 'data': (dt_str, code, fire, fault)})

    @pyqtSlot()
    def stop_worker(self):
        self._is_running = False
        self.timer.stop()
        if self.client: self.client.close()
