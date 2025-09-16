# workers/magnetometer_worker.py

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
        try:
            rm = pyvisa.ResourceManager(self.config.get('library_path', ''))
            self.inst = rm.open_resource(self.config['resource_name'], timeout=5000)
            self.inst.read_termination = '\n'
            self.inst.write_termination = '\n'
            logging.info("[Magnetometer] Successfully connected to device.")
            self.inst.write('*RST'); time.sleep(1.5)
            while self._is_running:
                try:
                    ts = time.time() # === 변경점: 타임스탬프를 루프 시작 시 기록 ===
                    response_x = self.inst.query(':MEASure:SCALar:FLUX:X?')
                    response_y = self.inst.query(':MEASure:SCALar:FLUX:Y?')
                    response_z = self.inst.query(':MEASure:SCALar:FLUX:Z?')
                    bx = self._parse_and_convert_tesla_to_mg(response_x)
                    by = self._parse_and_convert_tesla_to_mg(response_y)
                    bz = self._parse_and_convert_tesla_to_mg(response_z)
                    b_mag = math.sqrt(bx**2 + by**2 + bz**2)
                    raw = {'mag': [bx, by, bz, b_mag]}
                    self.raw_data_ready.emit(raw)
                    # === 변경점: DB 저장 및 GUI 그래프 업데이트를 위해 ts와 raw값을 함께 전달 ===
                    self._process_and_enqueue(ts, raw['mag'])
                    time.sleep(self.interval)
                except pyvisa.errors.VisaIOError as e:
                    if not self._is_running: break
                    else: raise e
        except Exception as e:
            self.error_occurred.emit(f"Magnetometer Communication Error: {e}")
        finally:
            if self.inst:
                self.inst.close()

    def _process_and_enqueue(self, ts, raw_data):
        # 1. GUI 그래프용 데이터 샘플링 (기존 평균 로직 유지)
        for i in range(4):
            self.samples[i].append(raw_data[i])
        
        # 2. DB 저장 및 GUI 그래프 업데이트 주기 확인
        if len(self.samples[0]) >= int(60 / self.interval):
            # GUI 그래프용 평균값 계산 및 전송
            avg_for_gui = [np.mean(ch) for ch in self.samples]
            self.avg_data_ready.emit(time.time(), avg_for_gui)
            
            # === 핵심 변경점: DB에는 평균이 아닌, '방금 들어온 마지막 값(raw_data)'을 저장 ===
            self._enqueue_db_data(ts, raw_data)
            
            # 샘플 초기화
            self.samples = [[] for _ in range(4)]

    def _enqueue_db_data(self, ts, data):
        dt_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
        self.data_queue.put({'type': 'MAG', 'data': (dt_str, round(data[0],2), round(data[1],2), round(data[2],2), round(data[3],2))})

    @pyqtSlot()
    def stop(self):
        self._is_running = False