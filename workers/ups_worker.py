# workers/ups_worker.py (최종 수정본)

import time
import logging
import subprocess
import collections
from PyQt5.QtCore import QObject, pyqtSignal, QTimer, pyqtSlot

class UPSWorker(QObject):
    data_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, config, data_queue):
        super().__init__()
        self.config = config
        self.data_queue = data_queue
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.measure)
        self.interval_s = config.get('interval_s', 5)
        self.db_push_counter = 0
        self.db_push_threshold = int(60 / self.interval_s)

    @pyqtSlot()
    def start_worker(self):
        try:
            subprocess.run(['apcaccess'], capture_output=True, check=True)
            self.timer.start(self.interval_s * 1000)
            logging.info(f"UPS worker started with {self.interval_s}s interval.")
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            self.error_occurred.emit(f"Failed to run 'apcaccess'. Is apcupsd running? Error: {e}")

    def measure(self):
        try:
            output = subprocess.check_output(['apcaccess'], text=True)
            ups_info = collections.OrderedDict()
            for line in output.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    ups_info[key.strip()] = value.strip()
            
            # === 변경점: .split()[0]을 사용하여 단위(unit)를 제거하고 숫자만 추출 ===
            data = {
                'STATUS': ups_info.get('STATUS', 'N/A'),
                'LINEV': float(ups_info.get('LINEV', '0.0').split()[0]),
                'BCHARGE': float(ups_info.get('BCHARGE', '0.0').split()[0]),
                'TIMELEFT': float(ups_info.get('TIMELEFT', '0.0').split()[0]),
            }
            
            self.data_ready.emit(data)
            
            self.db_push_counter += 1
            if self.db_push_counter >= self.db_push_threshold:
                self._enqueue_db_data(time.time(), data)
                self.db_push_counter = 0
        except Exception as e:
            self.error_occurred.emit(f"UPS data fetch error: {e}")
            self.timer.stop()

    def _enqueue_db_data(self, ts, data):
        dt_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
        db_tuple = (dt_str, data['STATUS'], data['LINEV'], data['BCHARGE'], data['TIMELEFT'])
        self.data_queue.put({'type': 'UPS', 'data': db_tuple})

    @pyqtSlot()
    def stop_worker(self):
        self.timer.stop()
        logging.info("UPS worker stopped.")