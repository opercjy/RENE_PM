# workers/pid_worker.py (전체 덮어쓰기)

import time
import logging
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

logging.getLogger("pymodbus").setLevel(logging.CRITICAL)

class PidWorker(QObject):
    data_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, config, data_queue):
        super().__init__()
        self.config = config
        self.data_queue = data_queue
        self.client = None
        self.interval = float(config.get('interval_s', 2.0))
        self._is_running = False
        self.consecutive_errors = 0

    @pyqtSlot()
    def run(self):
        self._is_running = True
        logging.info(f"PID Worker (RAEGuard2) background loop started on {self.config['port']}")
        try:
            while self._is_running:
                ts = time.time()
                try:
                    if self.client is None:
                        self.client = ModbusSerialClient(
                            port=self.config['port'], baudrate=self.config.get('baudrate', 9600), 
                            parity='N', stopbits=1, bytesize=8, timeout=0.5
                        )
                    if not self.client.connect():
                        raise ConnectionError("Port disconnected")
                        
                    slave_id = self.config.get('slave_id', 50)
                    res_conc = self.client.read_holding_registers(address=8, count=2, slave=slave_id)

                    if res_conc.isError():
                        raise ModbusException("Modbus Read Error at Address 8")

                    if self.consecutive_errors > 0:
                        logging.info("PID Detector (VOC) 통신이 복구되었습니다.")
                    self.consecutive_errors = 0

                    raw_conc = (res_conc.registers[0] << 16) + res_conc.registers[1]
                    scale = self.config.get('scale_factor', 1000.0) 
                    concentration = raw_conc / scale
                    
                    ui_alarm_level = 0
                    warn_limit = self.config.get('thresholds', {}).get('warning_ppm', 10.0)
                    crit_limit = self.config.get('thresholds', {}).get('critical_ppm', 50.0)
                    
                    if concentration >= crit_limit: ui_alarm_level = 2
                    elif concentration >= warn_limit: ui_alarm_level = 1
                    
                    self.data_ready.emit({'voc_detector': {'conc': concentration, 'alarm': ui_alarm_level, 'unit': 'ppm'}})
                    self._enqueue_db_data(ts, concentration, ui_alarm_level)

                except Exception as e:
                    if not self._is_running: break
                    self.consecutive_errors += 1
                    if self.consecutive_errors % 5 == 0:
                        self.error_occurred.emit(f"PID Detector 통신 에러 ({self.consecutive_errors}회 연속 실패)")
                    
                    if self.client:
                        try: self.client.close()
                        except: pass
                        self.client = None

                    self.data_ready.emit({'voc_detector': {'conc': 0.0, 'alarm': -1, 'unit': 'ppm', 'msg': 'COMM FAULT'}})
                    self._enqueue_db_data(ts, None, -1)

                elapsed = time.time() - ts
                time.sleep(max(0, self.interval - elapsed))
        finally:
            if self.client:
                try: self.client.close()
                except: pass

    def _enqueue_db_data(self, ts, conc, alarm):
        dt_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
        conc_val = round(conc, 3) if conc is not None else None
        self.data_queue.put({'type': 'VOC', 'data': (dt_str, conc_val, alarm, 'ppm')})

    @pyqtSlot()
    def stop(self):
        self._is_running = False