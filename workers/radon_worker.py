# workers/radon_worker.py (전체 덮어쓰기)

import time
import logging
import serial
import re
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
            # [핵심 1] 10분간 쌓인 시리얼 라인 노이즈 버퍼 완벽 비우기
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            
            self.ser.write(b'VALUE?\r\n')
            self.ser.flush()
            
            # [핵심 2] 에코나 빈 줄 무시를 위한 5회 연속 판독 루프
            valid_found = False
            for _ in range(5):
                res = self.ser.readline().decode('ascii', 'ignore').strip()
                if not res: continue
                
                if "VALUE" in res.upper():
                    ts = time.time()
                    
                    # [핵심 3] 정규표현식(Regex)을 이용한 강건한 데이터 파싱
                    mu_match = re.search(r'VALUE\s*[:=]?\s*([0-9.]+)', res, re.IGNORECASE)
                    sigma_match = re.search(r'SIGMA\s*[:=]?\s*([0-9.]+)', res, re.IGNORECASE)
                    
                    mu = float(mu_match.group(1)) if mu_match else 0.0
                    sigma = float(sigma_match.group(1)) if sigma_match else 0.0
                    
                    self.data_ready.emit(ts, mu, sigma) 
                    self._enqueue_db_data(ts, mu, sigma)
                    valid_found = True
                    break
            
            if not valid_found:
                # 마지막까지 값을 찾지 못했을 때만 에러 출력
                logging.warning(f"Radon returned invalid data: '{res}'")
                
        except Exception as e:
            logging.error(f"Radon parsing/comm error: {e}")

    def _enqueue_db_data(self, ts, mu, sigma):
        dt_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
        self.data_queue.put({'type': 'RADON', 'data': (dt_str, round(mu, 2), round(sigma, 2))})

    @pyqtSlot()
    def stop(self):
        self._is_running = False
