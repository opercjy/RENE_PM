# workers/pid_worker.py

import time
import logging
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer

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

    @pyqtSlot()
    def start_worker(self):
        try:
            self.client = ModbusSerialClient(
                port=self.config['port'], 
                baudrate=self.config.get('baudrate', 9600), 
                parity='N', stopbits=1, bytesize=8, timeout=1
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
            slave_id = self.config.get('slave_id', 2)
            
            rr_conc = self.client.read_holding_registers(address=8, count=2, slave=slave_id)
            rr_alarm = self.client.read_holding_registers(address=34, count=1, slave=slave_id)

            if rr_conc.isError() or rr_alarm.isError():
                raise ModbusException("Modbus Read Error")

            raw_conc = (rr_conc.registers[0] << 16) + rr_conc.registers[1]
            scale = self.config.get('scale_factor', 1000.0) 
            concentration = raw_conc / scale
            
            alarm_val = rr_alarm.registers[0]
            
            data = {
                'voc_detector': {
                    'conc': concentration,
                    'alarm': alarm_val,
                    'unit': 'ppm'
                }
            }
            
            self.data_ready.emit(data)
            self._enqueue_db_data(ts, concentration, alarm_val)

        except Exception as e:
            self.error_occurred.emit(f"PID Detector Comm Error: {e}")

    def _enqueue_db_data(self, ts, conc, alarm):
        dt_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
        self.data_queue.put({'type': 'VOC', 'data': (dt_str, round(conc, 3), alarm, 'ppm')})

    @pyqtSlot()
    def stop_worker(self):
        self._is_running = False
        self.timer.stop()
        if self.client: self.client.close()