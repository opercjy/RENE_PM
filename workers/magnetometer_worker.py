# workers/magnetometer_worker.py (전체 덮어쓰기)

import time
import math
import numpy as np
import logging
import pyvisa
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

class MagnetometerWorker(QObject):
    """
    [자기장 센서 통신 전담 워커]
    """
    avg_data_ready = pyqtSignal(float, list)
    raw_data_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, config, data_queue):
        super().__init__()
        self.config = config
        self.data_queue = data_queue
        self.interval = config.get('interval_s', 1.0)
        self.samples = [[] for _ in range(4)]
        self._is_running = False
        self.inst = None
        self.rm = None

    def _parse_and_convert_tesla_to_mg(self, response_str: str) -> float:
        try:
            numeric_part = response_str.strip().split(' ')[0]
            return float(numeric_part) * 10_000_000
        except (ValueError, IndexError):
            return float('nan')

    @pyqtSlot()
    def run(self):
        self._is_running = True
        
        while self._is_running:
            try:
                # [핵심] 연결 유실 시 ResourceManager 자체를 재생성하여 libusb 메모리 오염 세탁
                if self.rm is None:
                    self.rm = pyvisa.ResourceManager(self.config.get('library_path', '@py'))
                
                self.inst = self.rm.open_resource(self.config['resource_name'], timeout=3000)
                self.inst.read_termination = '\n'
                self.inst.write_termination = '\n'
                
                self.inst.write('*RST')
                time.sleep(1.5)
                
                idn = self.inst.query('*IDN?').strip()
                logging.info(f"[Magnetometer] Successfully connected. ID: {idn}")

                while self._is_running:
                    ts = time.time()
                    
                    response_x = self.inst.query(':MEASure:SCALar:FLUX:X?')
                    time.sleep(0.05)
                    response_y = self.inst.query(':MEASure:SCALar:FLUX:Y?')
                    time.sleep(0.05)
                    response_z = self.inst.query(':MEASure:SCALar:FLUX:Z?')
                    
                    bx = self._parse_and_convert_tesla_to_mg(response_x)
                    by = self._parse_and_convert_tesla_to_mg(response_y)
                    bz = self._parse_and_convert_tesla_to_mg(response_z)
                    b_mag = math.sqrt(bx**2 + by**2 + bz**2)
                    
                    raw = {'mag': [bx, by, bz, b_mag]}
                    self.raw_data_ready.emit(raw)
                    self._process_and_enqueue(ts, raw['mag'])
                    
                    elapsed = time.time() - ts
                    sleep_time = max(0, self.interval - elapsed)
                    time.sleep(sleep_time)

            except Exception as e:
                if not self._is_running: break
                logging.error(f"[Magnetometer] Fatal Error: {e}")
                self.error_occurred.emit(f"Magnetometer Error: {e}")
                
                # [핵심] 에러 발생 시 모든 객체를 완전히 파괴하여 메모리 반환
                if self.inst:
                    try: self.inst.close()
                    except: pass
                if self.rm:
                    try: self.rm.close()
                    except: pass
                self.inst = None
                self.rm = None
                
                # 에러 상황에서도 StateStore의 타이머가 굴러가도록 NaN 방출
                ts = time.time()
                nan_mag = [float('nan')] * 4
                self.raw_data_ready.emit({'mag': nan_mag})
                self._process_and_enqueue(ts, nan_mag)
                
                time.sleep(5.0)

    def _process_and_enqueue(self, ts, raw_data):
        for i in range(4):
            self.samples[i].append(raw_data[i])
        
        if len(self.samples[0]) >= int(60 / self.interval):
            # np.nanmean을 사용하여 에러(NaN) 기간 중 수신된 정상 데이터만 평균 산출
            avg_for_gui = [float(np.nanmean(ch)) if not np.all(np.isnan(ch)) else float('nan') for ch in self.samples]
            self.avg_data_ready.emit(time.time(), avg_for_gui)
            self._enqueue_db_data(ts, avg_for_gui) # raw_data 대신 1분 평균값 적재
            self.samples = [[] for _ in range(4)]

    def _enqueue_db_data(self, ts, data):
        dt_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
        d_out = [round(x, 2) if not math.isnan(x) else None for x in data]
        self.data_queue.put({'type': 'MAG', 'data': (dt_str, d_out[0], d_out[1], d_out[2], d_out[3])})

    @pyqtSlot()
    def stop(self):
        self._is_running = False
        if self.inst:
            try: self.inst.close()
            except Exception: pass
        if self.rm:
            try: self.rm.close()
            except Exception: pass