# workers/radon_worker.py

import time
import logging
import serial
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer

class RadonWorker(QObject):
    data_ready = pyqtSignal(float, float, float)
    # --- 수정: 시그널이 문자열과 정수, 두 개의 인자를 보내도록 변경 ---
    radon_status_update = pyqtSignal(str, int)
    error_occurred = pyqtSignal(str)

    def __init__(self, config, data_queue):
        super().__init__()
        self.config = config
        self.data_queue = data_queue
        self.ser = None
        
        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self._update_countdown)

        self.interval = int(config.get('interval_s', 600))
        self.countdown_seconds = 0
        self.is_stabilizing = True

    @pyqtSlot()
    def start_worker(self):
        logging.debug("[RadonWorker] start_worker() called.")
        try:
            self.ser = serial.Serial(self.config['port'], 19200, timeout=10)
            
            if self.config.get("unit_change_on_start", False):
                self.radon_status_update.emit("Sending setup...", -1)
                # ... (init/unit command 로직은 그대로)
            
            self.is_stabilizing = True
            self.countdown_seconds = self.config.get('stabilization_s', 600)
            self.radon_status_update.emit("Stabilizing", self.countdown_seconds)
            self.countdown_timer.start(1000)
            
        except serial.SerialException as e:
            self.error_occurred.emit(f"Radon Error: {e}")
            self.radon_status_update.emit("Connection Error", -1)

    def _update_countdown(self):
        if self.countdown_seconds > 0:
            self.countdown_seconds -= 1
            state_str = "Stabilizing" if self.is_stabilizing else "Measured. Next in"
            self.radon_status_update.emit(state_str, self.countdown_seconds)
        
        if self.countdown_seconds <= 0:
            self.is_stabilizing = False # 안정화가 끝나면 측정 상태로 전환
            self.measure()

    def measure(self):
        if not (self.ser and self.ser.is_open): return
        
        self.radon_status_update.emit("Measuring...", -1)
        
        try:
            self.ser.write(b'VALUE?\r\n')
            time.sleep(0.5)
            res = self.ser.readline().decode('ascii', 'ignore').strip()
            
            if res and "VALUE" in res:
                ts = time.time()
                mu = float(res.split(':')[1].split(' ')[1])
                sigma = float(res.split(':')[2].split(' ')[1])
                
                self.data_ready.emit(ts, mu, sigma) 
                self._enqueue_db_data(ts, mu, sigma)
                
                self.countdown_seconds = self.interval
                self.radon_status_update.emit("Measured. Next in", self.countdown_seconds)
            else:
                logging.warning(f"Radon device returned no data or invalid data: '{res}'")
                self.countdown_seconds = self.interval
                self.radon_status_update.emit("Read failed. Retrying", self.countdown_seconds)
        except Exception as e:
            logging.error(f"Radon parsing/comm error: {e}")
            self.countdown_seconds = self.interval
            self.radon_status_update.emit("Error. Retrying", self.countdown_seconds)

    def _enqueue_db_data(self, ts, mu, sigma):
        dt_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
        self.data_queue.put({'type': 'RADON', 'data': (dt_str, round(mu, 2), round(sigma, 2))})

    @pyqtSlot()
    def stop_worker(self):
        self.countdown_timer.stop()
        if self.ser:
            self.ser.close()