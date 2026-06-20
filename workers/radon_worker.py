# workers/radon_worker.py (전체 덮어쓰기)

import time
import logging
import serial
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

class RadonWorker(QObject):
    data_ready = pyqtSignal(float, float, float)
    radon_status_update = pyqtSignal(str, int)
    error_occurred = pyqtSignal(str)

    def __init__(self, config, data_queue):
        super().__init__()
        self.config = config
        self.data_queue = data_queue
        self.ser = None
        self._is_running = False

    @pyqtSlot()
    def run(self):
        self._is_running = True
        logging.info(f"RadonWorker background loop started on {self.config['port']}")
        
        try:
            try:
                self.ser = serial.Serial(self.config['port'], 19200, timeout=2.0, write_timeout=2.0)
            except Exception as e:
                self.error_occurred.emit(f"Radon Connection Error: {e}")
                self.radon_status_update.emit("Connection Error", -1)
                return

            stab_s = self.config.get('stabilization_s', 600)
            start_t = time.time()
            
            while self._is_running and (time.time() - start_t) < stab_s:
                remain = int(stab_s - (time.time() - start_t))
                self.radon_status_update.emit("Stabilizing", remain)
                time.sleep(1.0)
                
            interval = self.config.get('interval_s', 600)
            last_measure = 0
            
            while self._is_running:
                now = time.time()
                if now - last_measure >= interval:
                    self.measure()
                    last_measure = time.time()
                else:
                    remain = int(interval - (now - last_measure))
                    self.radon_status_update.emit("Measured. Next in", remain)
                time.sleep(1.0)
        finally:
            if self.ser:
                try: self.ser.close()
                except: pass

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
            else:
                logging.warning(f"Radon returned invalid data: '{res}'")
        except Exception as e:
            logging.error(f"Radon parsing/comm error: {e}")

    def _enqueue_db_data(self, ts, mu, sigma):
        dt_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
        self.data_queue.put({'type': 'RADON', 'data': (dt_str, round(mu, 2), round(sigma, 2))})

    @pyqtSlot()
    def stop(self):
        self._is_running = False