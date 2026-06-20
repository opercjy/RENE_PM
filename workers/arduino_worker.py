# workers/arduino_worker.py (전체 덮어쓰기)

import time
import numpy as np
import logging
import serial
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer

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
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.measure)
        
        # 기본 폴링 주기를 설정 (기본값 2초 = 2000ms)
        self.interval = int(config.get('interval_s', 2.0) * 1000)
        self._is_running = False
        self.samples = {key: [] for key in self.config.get('data_mapping', {}).keys()}
        
        # [핵심] 특정 센서(temp0) 고장에 의존하지 않는 독립적인 시간 카운터
        self.tick_counter = 0 

    @pyqtSlot()
    def start_worker(self):
        try:
            self.ser = serial.Serial(port=self.config['port'], baudrate=self.config.get('baudrate', 9600), timeout=2)
            self._is_running = True
            self.timer.start(self.interval)
            logging.info(f"Arduino worker started with {self.interval}ms interval.")
        except serial.SerialException as e:
            self.error_occurred.emit(f"Arduino Error: {e}")

    def measure(self):
        if not (self.ser and self.ser.is_open): return
        try:
            ts = time.time()
            line = self.ser.readline().decode('utf-8').strip()
            if line:
                data = {}
                for pair in line.split(','):
                    if ':' in pair:
                        key, val_str = pair.split(':', 1)
                        key = key.strip()
                        val_str = val_str.strip()
                        if key in self.samples:
                            # [검증 완료] 아두이노의 'NONE' 출력을 파이썬의 None 객체로 완벽히 치환
                            data[key] = None if val_str.upper() == 'NONE' else float(val_str)
                
                if data:
                    self.raw_data_ready.emit({'arduino': data})
                    self._process_and_enqueue(ts, data)
        except Exception as e:
            logging.warning(f"Arduino parsing error: {e}. Raw: '{line}'")

    def _process_and_enqueue(self, ts, raw_data):
        for key, val in raw_data.items():
            if val is not None and key in self.samples:
                self.samples[key].append(val)
        
        self.tick_counter += 1
        # [최적화] 다른 센서들과 완벽하게 동일한 1분(60초) 렌더링/저장 주기로 동기화
        target_ticks = int(60 / (self.interval / 1000)) 
        
        if self.tick_counter >= target_ticks:
            avg_data_for_gui = {}
            for key, val_list in self.samples.items():
                if val_list: # 해당 1분 동안 한 번이라도 정상 수신된 데이터가 있다면 평균 계산
                    avg_data_for_gui[key] = float(np.mean(val_list))
            
            self.avg_data_ready.emit(time.time(), avg_data_for_gui)
            
            # [수정] 순간적인 노이즈가 섞인 단일 raw_data가 아닌, 깨끗한 1분 평균값을 DB에 적재
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
    def stop_worker(self):
        self._is_running = False
        self.timer.stop()
        if self.ser:
            self.ser.close()
            logging.info("Arduino worker stopped.")