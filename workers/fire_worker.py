import time
import logging
import struct
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer

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
        # 설정이 없으면 기본 1초 간격
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
            logging.info(f"FireWorker (FS24X Plus) started on {self.config['port']}")
        except Exception as e:
            self.error_occurred.emit(f"Fire Detector Error: {e}")

    def _read_float32(self, address, slave_id):
        """Modbus 레지스터 2개를 읽어 Float32로 변환 (Big Endian)"""
        # 주소 보정: 40001 기반 주소를 0-based 주소로 변환
        relative_addr = address - 40001
        
        # 2개의 레지스터(4바이트) 읽기
        rr = self.client.read_holding_registers(address=relative_addr, count=2, slave=slave_id)
        
        if rr.isError():
            raise ModbusException(f"Read Error at {address}")
            
        # 2개의 16비트 정수를 Big Endian Float로 변환
        raw_bytes = struct.pack('>HH', rr.registers[0], rr.registers[1])
        return struct.unpack('>f', raw_bytes)[0]

    def measure(self):
        if not self._is_running: return
        try:
            ts = time.time()
            slave_id = self.config.get('slave_id', 1)
            regs = self.config.get('registers', {
                "alarm_level": 40003, 
                "fault_code": 40005, 
                "monitor_state": 40007
            })
            
            # 1. Read Alarm Level (Float32) at 40003
            alarm_val = self._read_float32(regs['alarm_level'], slave_id)
            
            # 2. Read Fault Code (Uint16) at 40005
            fault_addr_rel = regs['fault_code'] - 40001
            rr_fault = self.client.read_holding_registers(address=fault_addr_rel, count=1, slave=slave_id)
            
            if not rr_fault.isError():
                fault_code = rr_fault.registers[0]
            else:
                fault_code = 0
            
            # Status Logic
            # Alarm Level: 0.0=Normal, 1.0=Alarm1, 2.0=Alarm2
            is_fire = (alarm_val >= 1.0)
            is_fault = (fault_code > 0)
            
            status_str = "NORMAL"
            if is_fire: 
                status_str = "FIRE ALARM"
            elif is_fault: 
                status_str = f"FAULT ({fault_code})"

            # GUI 전송 데이터 구성
            data = {
                'fire_detector': {
                    'status_code': int(alarm_val),
                    'is_fire': is_fire,
                    'is_fault': is_fault,
                    'msg': status_str
                }
            }
            
            self.data_ready.emit(data)
            self._enqueue_db_data(ts, int(alarm_val), is_fire, is_fault)

        except Exception as e:
            self.error_occurred.emit(f"Fire Detector Comm Error: {e}")

    def _enqueue_db_data(self, ts, code, fire, fault):
        dt_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
        # DB Worker가 처리할 수 있는 튜플 형태로 큐에 삽입
        self.data_queue.put({'type': 'FIRE', 'data': (dt_str, code, fire, fault)})

    @pyqtSlot()
    def stop_worker(self):
        self._is_running = False
        self.timer.stop()
        if self.client: 
            self.client.close()