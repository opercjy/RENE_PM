# workers/hv_worker.py

import logging
import time
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer

try:
    from caen_libs import caenhvwrapper as hv
except ImportError:
    hv = None

class HVWorker(QObject):
    data_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    connection_status = pyqtSignal(bool)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.device = None
        self._is_running = False
        self.polling_timer = QTimer(self)
        self.polling_timer.timeout.connect(self.poll_data)
        self.parameters_to_fetch = ['Pw', 'VMon', 'IMon', 'V0Set', 'I0Set', 'Status']
        self.crate_map = {int(k): v for k, v in self.config.get('crate_map', {}).items()}

    @pyqtSlot()
    def start_worker(self):
        if not hv:
            self.error_occurred.emit("caenhvwrapper library not found.")
            return

        self._is_running = True
        try:
            system_type = getattr(hv.SystemType, self.config["system_type"])
            link_type = getattr(hv.LinkType, self.config["link_type"])
            
            logging.info(f"Connecting to CAEN HV at {self.config['ip_address']}...")
            self.device = hv.Device.open(
                system_type, link_type, self.config["ip_address"],
                self.config["username"], self.config["password"]
            )
            logging.info("Successfully connected to CAEN HV system.")
            self.connection_status.emit(True)
            self.polling_timer.start(self.config["polling_interval_ms"])

        except Exception as e:
            logging.error(f"Failed to connect to CAEN HV system: {e}")
            self.error_occurred.emit(f"CAEN Connection Error: {e}")
            self.connection_status.emit(False)

    def poll_data(self):
        if not self._is_running or not self.device:
            return
        
        try:
            collected_data = {}
            for slot, board_info in self.crate_map.items():
                channel_list = list(range(board_info['channels']))
                slot_data = {ch: {} for ch in channel_list}

                for param in self.parameters_to_fetch:
                    values = self.device.get_ch_param(slot, channel_list, param)
                    for ch, value in zip(channel_list, values):
                        # float 또는 int로 타입 안정화
                        try:
                            if '.' in str(value): slot_data[ch][param] = float(value)
                            else: slot_data[ch][param] = int(value)
                        except (ValueError, TypeError):
                            slot_data[ch][param] = value

                collected_data[slot] = slot_data
            
            self.data_ready.emit(collected_data)

        except Exception as e:
            logging.error(f"Error fetching CAEN data: {e}")
            self.error_occurred.emit(f"CAEN Communication Error: {e}")
            self.polling_timer.stop()
            self.connection_status.emit(False)


    def stop_worker(self):
        self._is_running = False
        self.polling_timer.stop()
        if self.device:
            try:
                self.device.close()
                logging.info("CAEN device closed.")
            except Exception as e:
                logging.error(f"Error closing CAEN device: {e}")