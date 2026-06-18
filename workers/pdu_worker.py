# workers/pdu_worker.py

import time
import logging
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException, ConnectionException

MODBUS_SLAVE_ID = 1 

class PDUWorker(QObject):
    sig_status_updated = pyqtSignal(dict)
    sig_log_message = pyqtSignal(str, str)
    sig_connection_changed = pyqtSignal(bool)
    sig_queue_data = pyqtSignal(dict)
    finished = pyqtSignal()

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.ip = self.config.get('ip_address')
        self.port = self.config.get('port', 502)
        self.timeout = self.config.get('timeout_sec', 3)
        self.polling_interval_ms = self.config.get('polling_interval_sec', 5) * 1000
        self.logger = logging.getLogger(__name__)

        self.is_running = False
        self.is_connected = None

    def get_client(self):
        return ModbusTcpClient(self.ip, port=self.port, timeout=self.timeout)

    @pyqtSlot()
    def start_worker(self):
        if not self.is_running:
            self.is_running = True
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.poll_data)
            self.timer.start(self.polling_interval_ms)
            self.sig_log_message.emit("INFO", f"PDU Worker started. Polling {self.ip}...")
            self.poll_data()

    @pyqtSlot()
    def stop_worker(self):
        if self.is_running:
            self.is_running = False
            if hasattr(self, 'timer'):
                self.timer.stop()
            self.sig_log_message.emit("INFO", "PDU Worker stopping.")
            self.set_connection_status(False, force_log=False) 
        self.finished.emit()

    def set_connection_status(self, status, force_log=True):
        if self.is_connected != status:
            previous_status = self.is_connected
            self.is_connected = status
            self.sig_connection_changed.emit(status)
            
            if force_log and previous_status is not None:
                if status:
                    self.sig_log_message.emit("INFO", "PDU Reconnected.")
                else:
                    self.sig_log_message.emit("ERROR", "PDU Connection Lost.")

    @pyqtSlot()
    def poll_data(self):
        if not self.is_running: return

        data_gui = {'global': {}, 'outputs': {}}
        db_payloads = []
        timestamp = datetime.now()
        timestamp_db = timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        try:
            with self.get_client() as client:
                if not client.connect():
                    self.sig_log_message.emit("WARNING", "Failed to connect to PDU for polling.")
                    self.set_connection_status(False)
                    return

                self.set_connection_status(True)
                
                rr_gv = client.read_input_registers(address=0, count=2, slave=MODBUS_SLAVE_ID)
                rr_gp = client.read_input_registers(address=200, count=1, slave=MODBUS_SLAVE_ID)
                
                if rr_gv and not rr_gv.isError() and rr_gp and not rr_gp.isError():
                    data_gui['global']['freq'] = rr_gv.registers[0] / 100.0
                    data_gui['global']['volt'] = rr_gv.registers[1] / 10.0
                    data_gui['global']['power'] = rr_gp.registers[0]
                
                rr_curr = client.read_input_registers(address=101, count=8, slave=MODBUS_SLAVE_ID)
                rr_watts = client.read_input_registers(address=201, count=8, slave=MODBUS_SLAVE_ID)
                rr_energy = client.read_input_registers(address=301, count=8, slave=MODBUS_SLAVE_ID)

                if (not rr_curr or rr_curr.isError() or not rr_watts or rr_watts.isError()):
                    self.sig_log_message.emit("ERROR", "Failed to read PDU Port Measurement data.")
                    return

                for i in range(8):
                    port_num = i + 1
                    try:
                        rr_state_single = client.read_coils(address=100 + port_num, count=1, slave=MODBUS_SLAVE_ID)
                        if rr_state_single and not rr_state_single.isError():
                            state_bool = rr_state_single.bits[0]
                        else:
                            state_bool = (rr_watts.registers[i] > 0)
                    except Exception:
                        state_bool = False

                    current_ma = rr_curr.registers[i]
                    power_w = rr_watts.registers[i]
                    
                    if rr_energy and not rr_energy.isError() and len(rr_energy.registers) > i:
                         energy_wh = rr_energy.registers[i]
                    else:
                         energy_wh = 0.0

                    data_gui['outputs'][port_num] = {
                        'state_bool': state_bool,
                        'power': power_w,
                        'current': current_ma,
                        'energy': energy_wh
                    }
                    db_payloads.append((timestamp_db, port_num, state_bool, float(power_w), current_ma, float(energy_wh)))
                
                self.sig_status_updated.emit(data_gui)
                if db_payloads:
                    self.sig_queue_data.emit({'type': 'PDU', 'data': db_payloads})

        except ConnectionException as e:
             self.logger.error(f"PDU Connection Error during polling: {e}")
             self.sig_log_message.emit("CRITICAL", f"Connection Error: {e}")
             self.set_connection_status(False)
        except ModbusException as e:
            self.logger.error(f"Modbus Exception during PDU polling: {e}")
            self.sig_log_message.emit("CRITICAL", f"Modbus Exception: {e}")
            self.set_connection_status(False)
        except Exception as e:
             self.logger.error(f"Unexpected Exception during PDU polling: {e}", exc_info=True)
             self.sig_log_message.emit("CRITICAL", f"Polling Error: {e}")
             self.set_connection_status(False)

    @pyqtSlot(int, bool)
    def control_single_port(self, port_num, state):
        if not (1 <= port_num <= 8): return

        address = 100 + port_num
        action_str = "ON" if state else "OFF"
        self.sig_log_message.emit("INFO", f"Attempting to turn Port {port_num} {action_str}...")

        try:
            with self.get_client() as client:
                if not client.connect():
                    self.sig_log_message.emit("ERROR", f"Failed to connect for control (Port {port_num}).")
                    return
                
                result = client.write_coil(address=address, value=state, slave=MODBUS_SLAVE_ID)
                if result and not result.isError():
                    self.sig_log_message.emit("SUCCESS", f"[OK] Port {port_num} successfully turned {action_str}.")
                    QTimer.singleShot(500, self.poll_data)
                else:
                    self.sig_log_message.emit("ERROR", f"[ERR] Failed to control Port {port_num}. Modbus Error: {result}")

        except ConnectionException as e:
             self.logger.error(f"PDU Connection Error during single port control: {e}")
             self.sig_log_message.emit("CRITICAL", f"Connection Error during control: {e}")
        except Exception as e:
            self.logger.error(f"Exception during PDU single port control: {e}", exc_info=True)
            self.sig_log_message.emit("CRITICAL", f"Exception during control: {e}")

    @pyqtSlot(bool)
    def control_all_ports(self, state):
        action_str = "ON" if state else "OFF"
        self.sig_log_message.emit("INFO", f"[INFO] Starting sequence to turn ALL ports {action_str}...")

        try:
            with self.get_client() as client:
                if not client.connect():
                    self.sig_log_message.emit("ERROR", "Failed to connect for ALL control.")
                    return

                for i in range(8):
                    port_num = i + 1
                    address = 100 + port_num
                    result = client.write_coil(address=address, value=state, slave=MODBUS_SLAVE_ID)
                    if result and result.isError():
                         self.sig_log_message.emit("WARNING", f"Failed setting Port {port_num} during ALL control.")
                    time.sleep(0.15)
                
                self.sig_log_message.emit("SUCCESS", f"[DONE] ALL ports {action_str} sequence complete.")
                QTimer.singleShot(500, self.poll_data)

        except ConnectionException as e:
             self.logger.error(f"PDU Connection Error during all port control: {e}")
             self.sig_log_message.emit("CRITICAL", f"Connection Error during ALL control: {e}")
        except Exception as e:
            self.logger.error(f"Exception during PDU all port control: {e}", exc_info=True)
            self.sig_log_message.emit("CRITICAL", f"Exception during all port control: {e}")