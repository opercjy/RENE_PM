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
                self.radon_status_update.emit("Sending setup commands...")
                
                if self.config.get("reset_on_start", False):
                    init_cmd = self.config.get("init_command", "")
                    if init_cmd:
                        logging.info(f"Sending Radon Init Command: {init_cmd}")
                        self.ser.write(f"{init_cmd}\r\n".encode())
                        time.sleep(2)
                
                unit_cmd = self.config.get("unit_command", "")
                if unit_cmd:
                    logging.info(f"Sending Radon Unit Command: {unit_cmd}")
                    self.ser.write(f"{unit_cmd}\r\n".encode())
                    time.sleep(1)
            
            self.is_stabilizing = True
            self.countdown_seconds = self.config.get('stabilization_s', 600)
            status_msg = f"Stabilizing ({self.countdown_seconds}s left)..."
            self.radon_status_update.emit(status_msg)
            self.countdown_timer.start(1000)
            
        except serial.SerialException as e:
            self.error_occurred.emit(f"Radon Error: {e}")
            self.radon_status_update.emit("Connection Error")

    def _update_countdown(self):
        if self.countdown_seconds > 0:
            self.countdown_seconds -= 1
            if self.is_stabilizing:
                status_msg = f"Stabilizing ({self.countdown_seconds}s left)..."
            else:
                status_msg = f"Measured. Next in {self.countdown_seconds}s..."
            self.radon_status_update.emit(status_msg)
        
        if self.countdown_seconds <= 0:
            if self.is_stabilizing:
                self.is_stabilizing = False
                self.measure()
            else:
                self.measure()

    def measure(self):
        if not (self.ser and self.ser.is_open): return
        
        self.radon_status_update.emit("Measuring...")
        
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
                self.radon_status_update.emit(f"Measured. Next in {self.countdown_seconds}s...")
            else:
                logging.warning(f"Radon device returned no data or invalid data: '{res}'")
                self.radon_status_update.emit(f"Read failed. Retrying...")
                self.countdown_seconds = self.interval
        except Exception as e:
            logging.error(f"Radon parsing/comm error: {e}")
            self.radon_status_update.emit(f"Error. Retrying...")
            self.countdown_seconds = self.interval

    def _enqueue_db_data(self, ts, mu, sigma):
        dt_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
        self.data_queue.put({'type': 'RADON', 'data': (dt_str, round(mu, 2), round(sigma, 2))})

    @pyqtSlot()
    def stop_worker(self):
        self.countdown_timer.stop()
        if self.ser:
            self.ser.close()