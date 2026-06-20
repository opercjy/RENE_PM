# workers/arduino_worker.py (전체 덮어쓰기)

import time
import numpy as np
import logging
import serial
import glob
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

class ArduinoWorker(QObject):
    avg_data_ready = pyqtSignal(float, dict)
    raw_data_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, config, data_queue):
        super().__init__()
        self.config = config
        self.data_queue = data_queue
        self.ser = None
        self.db_cols = [f'analog_{i}' for i in range(1, 6)] + ['digital_status', 'message']
        self.interval = float(config.get('interval_s', 2.0))
        self._is_running = False
        self.samples = {key: [] for key in self.config.get('data_mapping', {}).keys()}
        self.tick_counter = 0

    def _auto_hunt_arduino(self):
        ports_to_try = [self.config.get('port', '/dev/ttyACM0')]
        ports_to_try += sorted(glob.glob('/dev/ttyACM*')) + sorted(glob.glob('/dev/ttyUSB*'))
        ports_to_try = list(dict.fromkeys(ports_to_try))
        
        for p in ports_to_try:
            try:
                s = serial.Serial(port=p, baudrate=self.config.get('baudrate', 9600), timeout=1.5)
                for _ in range(3):
                    line = s.readline().decode('utf-8', 'ignore').strip()
                    if "temp0:" in line and "dist:" in line:
                        logging.info(f"✅ Arduino auto-detected and connected on port: {p}")
                        return s
                s.close()
            except Exception:
                pass
        return None

    @pyqtSlot()
    def run(self):
        self._is_running = True
        logging.info("Arduino worker background loop started. Hunting for device...")
        try:
            while self._is_running:
                ts = time.time()
                try:
                    if self.ser is None:
                        self.ser = self._auto_hunt_arduino()
                        if self.ser is None:
                            raise ConnectionError("Arduino port not found.")
                        
                    line = self.ser.readline().decode('utf-8', 'ignore').strip()
                    if line:
                        data = {}
                        for pair in line.split(','):
                            if ':' in pair:
                                key, val_str = pair.split(':', 1)
                                key = key.strip()
                                val_str = val_str.strip()
                                if key in self.samples:
                                    data[key] = None if val_str.upper() == 'NONE' else float(val_str)
                        if data:
                            self.raw_data_ready.emit({'arduino': data})
                            self._process_and_enqueue(ts, data)
                except Exception as e:
                    if not self._is_running: break
                    if self.tick_counter % 5 == 0:
                        logging.warning(f"Arduino communication error: {e}")
                    if self.ser:
                        try: self.ser.close()
                        except: pass
                        self.ser = None

                elapsed = time.time() - ts
                time.sleep(max(0, self.interval - elapsed))
        finally:
            if self.ser:
                try: self.ser.close()
                except: pass

    def _process_and_enqueue(self, ts, raw_data):
        for key, val in raw_data.items():
            if val is not None and key in self.samples:
                self.samples[key].append(val)
        
        self.tick_counter += 1
        if self.tick_counter >= int(60 / self.interval):
            avg_data_for_gui = {}
            for key, val_list in self.samples.items():
                if val_list: avg_data_for_gui[key] = float(np.mean(val_list))
            if avg_data_for_gui:
                self.avg_data_ready.emit(time.time(), avg_data_for_gui)
                self._enqueue_db_data(ts, avg_data_for_gui)
            self.samples = {key: [] for key in self.samples.keys()}
            self.tick_counter = 0

    def _enqueue_db_data(self, ts, data):
        dt = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
        mapping = self.config.get('data_mapping', {})
        db_data = {col: None for col in self.db_cols}
        for key, val in data.items():
            if key in mapping and val is not None:
                db_data[mapping[key]] = round(val, 2)
        
        db_tuple = (dt, db_data.get('analog_1'), db_data.get('analog_2'), db_data.get('analog_3'), 
                    db_data.get('analog_4'), db_data.get('analog_5'), 
                    db_data.get('digital_status'), db_data.get('message'))
        self.data_queue.put({'type': 'ARDUINO', 'data': db_tuple})

    @pyqtSlot()
    def stop(self):
        self._is_running = False