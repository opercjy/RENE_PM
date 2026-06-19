# workers/pid_worker.py (전체 덮어쓰기)

import time
import logging
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer

logging.getLogger("pymodbus").setLevel(logging.CRITICAL)

class PidWorker(QObject):
    data_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, config, data_queue):
        super().__init__()
        self.config = config
        self.data_queue = data_queue
        self.client = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.measure)
        self.interval = int(config.get('interval_s', 2.0) * 1000)
        self._is_running = False
        self.consecutive_errors = 0

    @pyqtSlot()
    def start_worker(self):
        try:
            self.client = ModbusSerialClient(
                port=self.config['port'], 
                baudrate=self.config.get('baudrate', 9600), 
                parity='N', stopbits=1, bytesize=8, timeout=0.5
            )
            if not self.client.connect():
                raise ConnectionError(f"Failed to connect to {self.config['port']}")
            
            self._is_running = True
            self.timer.start(self.interval)
            logging.info(f"PID Worker (RAEGuard2) started on {self.config['port']}")
        except Exception as e:
            self.error_occurred.emit(f"PID Detector Error: {e}")

    def measure(self):
        if not self._is_running: return
        try:
            ts = time.time()
            slave_id = self.config.get('slave_id', 50)
            
            res_conc = self.client.read_holding_registers(address=8, count=2, slave=slave_id)

            if res_conc.isError():
                raise ModbusException("Modbus Read Error at Address 8")

            if self.consecutive_errors >= 10:
                logging.info("PID Detector (VOC) 통신이 복구되었습니다.")
            self.consecutive_errors = 0

            raw_conc = (res_conc.registers[0] << 16) + res_conc.registers[1]
            scale = self.config.get('scale_factor', 1000.0) 
            concentration = raw_conc / scale
            
            ui_alarm_level = 0
            warn_limit = self.config.get('thresholds', {}).get('warning_ppm', 10.0)
            crit_limit = self.config.get('thresholds', {}).get('critical_ppm', 50.0)
            
            if concentration >= crit_limit:
                ui_alarm_level = 2
            elif concentration >= warn_limit:
                ui_alarm_level = 1
            
            data = {
                'voc_detector': {
                    'conc': concentration,
                    'alarm': ui_alarm_level, 
                    'unit': 'ppm'
                }
            }
            
            self.data_ready.emit(data)
            self._enqueue_db_data(ts, concentration, ui_alarm_level)

        except Exception as e:
            self.consecutive_errors += 1
            if self.consecutive_errors == 10:
                self.error_occurred.emit(f"PID Detector 통신 단절 (10회 연속 응답 없음).")
                self.data_ready.emit({
                    'voc_detector': {
                        'conc': 0.0, 'alarm': -1, 'unit': 'ppm', 'msg': 'COMM FAULT'
                    }
                })

    def _enqueue_db_data(self, ts, conc, alarm):
        dt_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
        self.data_queue.put({'type': 'VOC', 'data': (dt_str, round(conc, 3), alarm, 'ppm')})

    @pyqtSlot()
    def stop_worker(self):
        self._is_running = False
        self.timer.stop()
        if self.client:
            self.client.close()