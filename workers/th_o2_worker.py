import time
import numpy as np
import logging
from pymodbus.client import ModbusSerialClient
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer

class ThO2Worker(QObject):
    avg_data_ready = pyqtSignal(float, float, float, float)
    raw_data_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, config, data_queue):
        super().__init__()
        self.config = config
        self.data_queue = data_queue
        self.client = None
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.measure)
        
        # 통신 주기 2초 (안전하게)
        self.interval = 2000 
        self._is_running = False
        
        self.samples = {'temp': [], 'humi': [], 'o2': []}
        self.error_count = 0

    @pyqtSlot()
    def start_worker(self):
        try:
            # [핵심 수정] 타임아웃 0.5초, 재시도 0회 (응답 없으면 즉시 포기)
            self.client = ModbusSerialClient(
                port=self.config['port'], 
                baudrate=self.config.get('baudrate', 4800), 
                parity='N', stopbits=1, bytesize=8, 
                timeout=0.5,  # 0.5초만 기다림
                retries=0     # 재시도 안 함
            )
            
            # 초기 연결 시도 (실패해도 시작함)
            if not self.client.connect():
                logging.warning(f"TH/O2: Init connection failed. Will retry in loop.")
            
            self._is_running = True
            self.timer.start(self.interval)
            
        except Exception as e:
            self.error_occurred.emit(f"TH/O2 Start Fail: {e}")

    def measure(self):
        if not self._is_running: return

        # [Cool-down] 연속 에러 시 10초간 통신 중단
        if self.error_count > 10:
            if self.error_count == 11:
                logging.warning("TH/O2: Too many errors. Cooling down for 10s.")
            self.error_count += 1
            if self.error_count > 15: # 10초 후 리셋 (interval 2s * 5회)
                self.error_count = 0
            return

        try:
            if not self.client.connected:
                if not self.client.connect():
                    self.error_count += 1
                    return

            # [중요] Input Registers 읽기
            slave_id = self.config.get('modbus_id', 1)
            rr = self.client.read_input_registers(address=0, count=3, slave=slave_id)
            
            if rr.isError():
                self.error_count += 1
                # 에러 발생 시 연결을 끊어서 다음 번에 깨끗하게 재연결 시도
                self.client.close() 
                return

            # 성공!
            self.error_count = 0
            
            t = rr.registers[0] / 10.0
            h = rr.registers[1] / 10.0
            o = rr.registers[2] / 10.0 if len(rr.registers) > 2 else 0.0
            
            # 즉시 전송 (대시보드용)
            self.avg_data_ready.emit(time.time(), t, h, o)
            
            # DB용 샘플링
            self.samples['temp'].append(t)
            self.samples['humi'].append(h)
            self.samples['o2'].append(o)

            if len(self.samples['temp']) >= 30: # 1분 데이터
                self._process_avg()

        except Exception as e:
            self.error_count += 1
            # logging.error(f"TH/O2 Exception: {e}")

    def _process_avg(self):
        ts = time.time()
        if not self.samples['temp']: return
        
        at = np.mean(self.samples['temp'])
        ah = np.mean(self.samples['humi'])
        ao = np.mean(self.samples['o2'])
        
        dt = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
        self.data_queue.put({'type': 'TH_O2', 'data': (dt, at, ah, ao)})
        self.samples = {'temp': [], 'humi': [], 'o2': []}

    @pyqtSlot()
    def stop_worker(self):
        self._is_running = False
        self.timer.stop()
        if self.client: self.client.close()