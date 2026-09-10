# workers/th_o2_worker.py (전체 덮어쓰기)

import time
import numpy as np
import logging
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

logging.getLogger("pymodbus").setLevel(logging.CRITICAL)

class ThO2Worker(QObject):
    avg_data_ready = pyqtSignal(float, float, float, float)
    raw_data_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, config, data_queue):
        super().__init__()
        self.config = config
        self.data_queue = data_queue
        self.client = None
        self.interval = float(config.get('interval_s', 2.0))
        self._is_running = False
        self.samples = {'temp': [], 'humi': [], 'o2': []}
        self.consecutive_errors = 0

    @pyqtSlot()
    def run(self):
        self._is_running = True
        logging.info(f"TH/O2 worker background loop started on {self.config['port']}")
        try:
            while self._is_running:
                ts = time.time()
                try:
                    if self.client is None:
                        self.client = ModbusSerialClient(
                            port=self.config['port'], baudrate=self.config.get('baudrate', 4800), 
                            timeout=1.0, parity='N', stopbits=1, bytesize=8
                        )
                    if not self.client.connect():
                        raise ConnectionError("Connection failed")
                    
                    res = self.client.read_holding_registers(address=0, count=3, slave=self.config['modbus_id'])
                    if res.isError():
                        raise ModbusException("Response Error")
                    
                    if self.consecutive_errors > 0:
                        logging.info("TH/O2 Sensor 통신이 복구되었습니다.")
                    self.consecutive_errors = 0
                    
                    h = res.registers[0] / 10.0
                    t_raw = res.registers[1]
                    t = ((t_raw - 65536) / 10.0) if t_raw > 32767 else (t_raw / 10.0)
                    o = res.registers[2] / 10.0
                    
                    self.raw_data_ready.emit({'th_o2': {'temp': t, 'humi': h, 'o2': o}})
                    self._process_and_enqueue(ts, t, h, o)

                except Exception as e:
                    if not self._is_running: break
                    self.consecutive_errors += 1
                    if self.consecutive_errors % 5 == 0:
                        self.error_occurred.emit(f"TH/O2 Sensor 통신 에러 ({self.consecutive_errors}회 실패)")
                    if self.client:
                        try: self.client.close()
                        except: pass
                        self.client = None
                        
                elapsed = time.time() - ts
                time.sleep(max(0, self.interval - elapsed))
        finally:
            if self.client:
                try: self.client.close()
                except: pass
    
    def _process_and_enqueue(self, ts, temp, humi, o2):
        self.samples['temp'].append(temp)
        self.samples['humi'].append(humi)
        self.samples['o2'].append(o2)
        
        if len(self.samples['temp']) >= (60 / self.interval):
            avg_t = float(np.mean(self.samples['temp']))
            avg_h = float(np.mean(self.samples['humi']))
            avg_o = float(np.mean(self.samples['o2']))
            self.avg_data_ready.emit(time.time(), avg_t, avg_h, avg_o)
            self._enqueue_db_data(ts, avg_t, avg_h, avg_o)
            self.samples = {'temp': [], 'humi': [], 'o2': []}

    def _enqueue_db_data(self, ts, t, h, o):
        dt_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
        self.data_queue.put({'type': 'TH_O2', 'data': (dt_str, round(t, 2), round(h, 2), round(o, 2))})

    @pyqtSlot()
    def stop(self):
        self._is_running = False