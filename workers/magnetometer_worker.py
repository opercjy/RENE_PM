# workers/magnetometer_worker.py 파일을 아래 최종 버전으로 교체하세요.

import time
import math
import numpy as np
import logging
import pyvisa
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

class MagnetometerWorker(QObject):
    avg_data_ready = pyqtSignal(float, list)
    raw_data_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, config, data_queue):
        super().__init__()
        self.config = config
        self.data_queue = data_queue
        self.interval = config.get('interval_s', 1.0)
        self.samples = [[] for _ in range(4)]
        self._is_running = True
        self.inst = None

    def _parse_and_convert_tesla_to_mg(self, response_str: str) -> float:
        try:
            numeric_part = response_str.strip().split(' ')[0]
            value_in_tesla = float(numeric_part)
            return value_in_tesla * 10_000_000
        except (ValueError, IndexError) as e:
            logging.error(f"[Magnetometer] Failed to parse or convert response '{response_str}': {e}")
            return 0.0

    @pyqtSlot()
    def run(self):
        while self._is_running:
            try:
                logging.info("[Magnetometer] Attempting to connect...")
                rm = pyvisa.ResourceManager(self.config.get('library_path', ''))
                self.inst = rm.open_resource(self.config['resource_name'], timeout=5000)
                self.inst.read_termination = '\n'
                self.inst.write_termination = '\n'
                self.inst.write('*RST'); time.sleep(2.0)
                idn = self.inst.query('*IDN?').strip()
                logging.info(f"[Magnetometer] Successfully connected to device. ID: {idn}")

                while self._is_running:
                    ts = time.time()
                    response_x = self.inst.query(':MEASure:SCALar:FLUX:X?')
                    response_y = self.inst.query(':MEASure:SCALar:FLUX:Y?')
                    response_z = self.inst.query(':MEASure:SCALar:FLUX:Z?')
                    bx = self._parse_and_convert_tesla_to_mg(response_x)
                    by = self._parse_and_convert_tesla_to_mg(response_y)
                    bz = self._parse_and_convert_tesla_to_mg(response_z)
                    b_mag = math.sqrt(bx**2 + by**2 + bz**2)
                    raw = {'mag': [bx, by, bz, b_mag]}
                    self.raw_data_ready.emit(raw)
                    self._process_and_enqueue(ts, raw['mag'])
                    time.sleep(self.interval)

            except pyvisa.errors.VisaIOError as e:
                if not self._is_running: break
                self.error_occurred.emit(f"Magnetometer I/O Error: {e}. Reconnecting in 15s...")
                if self.inst: self.inst.close()
                time.sleep(15)
            
            except Exception as e:
                if not self._is_running: break
                self.error_occurred.emit(f"Magnetometer Error: {e}. Retrying in 15s...")
                if self.inst: self.inst.close()
                time.sleep(15)

    def _process_and_enqueue(self, ts, raw_data):
        for i in range(4):
            self.samples[i].append(raw_data[i])
        
        if len(self.samples[0]) >= int(60 / self.interval):
            avg_for_gui = [np.mean(ch) for ch in self.samples]
            self.avg_data_ready.emit(time.time(), avg_for_gui)
            self._enqueue_db_data(ts, raw_data)
            self.samples = [[] for _ in range(4)]

    def _enqueue_db_data(self, ts, data):
        dt_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
        self.data_queue.put({'type': 'MAG', 'data': (dt_str, round(data[0],2), round(data[1],2), round(data[2],2), round(data[3],2))})

    @pyqtSlot()
    def stop(self):
        logging.info("MagnetometerWorker stop method called.")
        self._is_running = False
        if self.inst:
            try:
                logging.info("Explicitly closing PyVISA instrument...")
                self.inst.close()
                logging.info("PyVISA instrument closed.")
            except Exception as e:
                logging.error(f"Error closing PyVISA instrument: {e}")