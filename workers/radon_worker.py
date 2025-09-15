# workers/radon_worker.py

import time
import logging
import serial
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer

class RadonWorker(QObject):
    data_ready = pyqtSignal(float, float, float)
    radon_status_update = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, config, data_queue):
        super().__init__()
        self.config = config
        self.data_queue = data_queue
        self.ser = None
        
        # === 변경점 1: 상태 업데이트를 위한 타이머들 분리 및 명확화 ===
        self.stabilization_timer = QTimer(self)
        self.stabilization_timer.timeout.connect(self._update_stabilization_countdown)
        
        self.measurement_timer = QTimer(self)
        self.measurement_timer.timeout.connect(self.measure)
        
        self.status_countdown_timer = QTimer(self) # 다음 측정까지 남은 시간을 보여주기 위한 1초짜리 타이머
        self.status_countdown_timer.timeout.connect(self._update_measurement_countdown)

        self.interval = int(config.get('interval_s', 600))
        self.countdown_seconds = 0

    @pyqtSlot()
    def start_worker(self):
        try:
            self.ser = serial.Serial(self.config['port'], 19200, timeout=10)
            self.countdown_seconds = self.config.get('stabilization_s', 600)
            status_msg = f"Stabilizing ({self.countdown_seconds}s left)..."
            self.radon_status_update.emit(status_msg)
            self.stabilization_timer.start(1000)
        except serial.SerialException as e:
            self.error_occurred.emit(f"Radon Error: {e}")
            self.radon_status_update.emit("Connection Error")

    def _update_stabilization_countdown(self):
        self.countdown_seconds -= 1
        status_msg = f"Stabilizing ({self.countdown_seconds}s left)..."
        self.radon_status_update.emit(status_msg)
        
        if self.countdown_seconds <= 0:
            self.stabilization_timer.stop()
            self.radon_status_update.emit("Measuring...")
            self.measurement_timer.start(self.interval * 1000)
            self.measure() # 안정화 후 첫 측정 즉시 실행

    # === 변경점 2: 다음 측정까지 남은 시간을 주기적으로 업데이트하는 슬롯 추가 ===
    def _update_measurement_countdown(self):
        self.countdown_seconds -= 1
        status_msg = f"Measured. Next in {self.countdown_seconds}s..."
        self.radon_status_update.emit(status_msg)
        if self.countdown_seconds <= 0:
            self.status_countdown_timer.stop()

    def measure(self):
        if not (self.ser and self.ser.is_open): return
        try:
            self.radon_status_update.emit("Measuring...")
            self.ser.write(b'VALUE?\r\n')
            res = self.ser.readline().decode('ascii', 'ignore').strip()
            
            if res and "VALUE" in res:
                ts = time.time()
                mu = float(res.split(':')[1].split(' ')[1])
                sigma = float(res.split(':')[2].split(' ')[1])
                
                self.data_ready.emit(ts, mu, sigma) 
                self._enqueue_db_data(ts, mu, sigma)
                
                # === 변경점 3: 측정 성공 후, 카운트다운 시작 및 상태 업데이트 ===
                self.countdown_seconds = self.interval
                status_msg = f"Measured. Next in {self.countdown_seconds}s..."
                self.radon_status_update.emit(status_msg)
                
                if not self.status_countdown_timer.isActive():
                    self.status_countdown_timer.start(1000)

            else:
                logging.warning(f"Radon device returned no data or invalid data: '{res}'")
                self.radon_status_update.emit("Device not responding")

        except Exception as e:
            logging.error(f"Radon parsing error: {e}")
            self.radon_status_update.emit("Parsing Error")

    def _enqueue_db_data(self, ts, mu, sigma):
        dt_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
        self.data_queue.put({'type': 'RADON', 'data': (dt_str, round(mu, 2), round(sigma, 2))})

    @pyqtSlot()
    def stop_worker(self):
        self.stabilization_timer.stop()
        self.measurement_timer.stop()
        self.status_countdown_timer.stop()
        if self.ser:
            self.ser.close()