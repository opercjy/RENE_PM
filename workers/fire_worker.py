# workers/fire_worker.py (전체 덮어쓰기)

import time
import logging
import struct
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer

logging.getLogger("pymodbus").setLevel(logging.CRITICAL)

class FireWorker(QObject):
    data_ready = pyqtSignal(dict)
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
        self.consecutive_errors = 0

    @pyqtSlot()
    def start_worker(self):
        try:
            self.client = ModbusSerialClient(
                port=self.config['port'], 
                baudrate=self.config.get('baudrate', 9600), 
                parity=self.config.get('parity', 'E'), 
                stopbits=1, bytesize=8, timeout=0.5
            )
            if not self.client.connect():
                raise ConnectionError(f"Failed to connect to {self.config['port']}")
            
            self._is_running = True
            self.timer.start(self.interval)
            logging.info(f"FireWorker (FS24X Plus) started on {self.config['port']}")
        except Exception as e:
            self.error_occurred.emit(f"Fire Detector Error: {e}")

    def measure(self):
        if not self._is_running: return
        try:
            ts = time.time()
            slave_id = self.config.get('slave_id', 45)
            
            # [최적화] Address 2부터 14까지 총 13개의 레지스터를 단 한 번의 통신으로 블록 읽기
            res = self.client.read_holding_registers(address=2, count=13, slave=slave_id)

            if res.isError() or len(res.registers) < 13:
                raise ModbusException("Modbus Response Error")

            if self.consecutive_errors >= 10:
                logging.info("Fire Detector (IR3 Flame) 통신이 복구되었습니다.")
            self.consecutive_errors = 0

            # 1. Alarm Level 파싱 (Float32: Offset 0, 1 -> Addr 2, 3)
            raw_bytes = struct.pack('>HH', res.registers[0], res.registers[1])
            alarm_level = struct.unpack('>f', raw_bytes)[0]
            
            # 2. Fault Code 파싱 (Uint16: Offset 2 -> Addr 4)
            fault_code = res.registers[2]
            
            # 3. Monitor State 파싱 (Uint8: Offset 4 -> Addr 6)
            state_val = res.registers[4]
            if state_val in [1, 6]: state_str = "NORMAL"
            elif state_val in [2, 3]: state_str = "INHIBITED"
            elif state_val in [5, 7]: state_str = "WARNING"
            elif state_val in [1, 4, 8]: state_str = "FAULT"
            elif state_val in [16, 17, 3] or alarm_level >= 1.0: state_str = "FIRE ALARM!"
            else: state_str = f"UNKNOWN ({state_val})"

            # 4. Temperature 파싱 (Int16: Offset 12 -> Addr 14)
            temp_raw = res.registers[12]
            if temp_raw > 32767: temp_raw -= 65536
            temperature = temp_raw / 10.0

            is_fire = ("ALARM" in state_str)
            is_fault = ("FAULT" in state_str or fault_code > 0)
            
            if is_fault and not is_fire:
                state_str = f"FAULT ({fault_code})"

            display_msg = f"{state_str} ({temperature:.1f}°C)"

            data = {
                'fire_detector': {
                    'status_code': int(alarm_level),
                    'is_fire': is_fire,
                    'is_fault': is_fault,
                    'msg': display_msg
                }
            }
            
            self.data_ready.emit(data)
            self._enqueue_db_data(ts, int(alarm_level), is_fire, is_fault, temperature)

        except Exception as e:
            self.consecutive_errors += 1
            if self.consecutive_errors == 10:
                self.error_occurred.emit(f"Fire Detector 통신 단절 (10회 연속 응답 없음).")
                self.data_ready.emit({
                    'fire_detector': {
                        'status_code': -1, 'is_fire': False, 'is_fault': True, 'msg': 'COMM FAULT'
                    }
                })

    def _enqueue_db_data(self, ts, code, fire, fault, temp):
        dt_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
        self.data_queue.put({'type': 'FIRE', 'data': (dt_str, code, fire, fault, round(temp, 1))})

    @pyqtSlot()
    def stop_worker(self):
        self._is_running = False
        self.timer.stop()
        if self.client: 
            self.client.close()