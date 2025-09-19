# workers/hardware_manager.py 파일을 아래 코드로 전체 교체합니다.

import logging
import serial
import nidaqmx
import pyvisa
import re
import subprocess # subprocess 모듈 추가
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer

class HardwareManager(QObject):
    device_connected = pyqtSignal(str)
    device_disconnected = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.scan)
        self.online = set()
        self.pyvisa_rm = None

    @pyqtSlot()
    def start_scan(self):
        logging.info("HardwareManager scan started in a new thread.")
        if self.config.get('magnetometer', {}).get('enabled') and pyvisa:
            try:
                self.pyvisa_rm = pyvisa.ResourceManager(self.config['magnetometer'].get('library_path', ''))
            except Exception as e:
                logging.error(f"PyVISA ResourceManager init failed: {e}")
        self.scan()
        self.timer.start(5000)

    @pyqtSlot()
    def scan(self):
        newly_detected = self._detect_offline_devices()
        for device_name in newly_detected:
            if device_name not in self.online:
                self.online.add(device_name)
                self.device_connected.emit(device_name)

    def _detect_offline_devices(self):
        newly_detected = set()
        # === 변경점 1: 스캔할 장치 목록에 'ups' 추가 ===
        device_names = ['daq', 'radon', 'th_o2', 'arduino', 'magnetometer', 'ups']
        for name in device_names:
            if name not in self.online and self.config.get(name, {}).get('enabled'):
                if name == 'daq' and nidaqmx:
                    try:
                        if nidaqmx.system.System.local().devices: newly_detected.add('daq')
                    except: pass

                elif name == 'magnetometer' and self.pyvisa_rm:
                    try:
                        target_vid_int = int(self.config[name].get('idVendor', '0'), 16)
                        target_pid_int = int(self.config[name].get('idProduct', '0'), 16)
                        if not target_vid_int or not target_pid_int: continue
                        for res in self.pyvisa_rm.list_resources():
                            if 'USB' not in res: continue
                            try:
                                parts = res.split('::')
                                if len(parts) < 3: continue
                                res_vid_int = int(parts[1], 0)
                                res_pid_int = int(parts[2], 0)
                                if res_vid_int == target_vid_int and res_pid_int == target_pid_int:
                                    newly_detected.add('magnetometer')
                                    break
                            except (ValueError, IndexError):
                                continue
                    except Exception as e:
                        logging.warning(f"An exception occurred during magnetometer scan: {e}")
                
                # === 변경점 2: UPS 감지 로직 추가 ===
                elif name == 'ups':
                    try:
                        # apcaccess 명령을 실행하여 apcupsd 데몬이 응답하는지 확인
                        result = subprocess.run(['apcaccess'], capture_output=True, text=True, timeout=2)
                        if result.returncode == 0 and 'STATUS' in result.stdout:
                            newly_detected.add('ups')
                    except (FileNotFoundError, subprocess.TimeoutExpired):
                        pass # apcaccess 명령이 없거나 응답이 없으면 무시

                elif name in ['radon', 'th_o2', 'arduino'] and serial:
                    if self.config[name].get('port') and self._check_serial(self.config[name]['port']):
                        newly_detected.add(name)
        return newly_detected

    def _check_serial(self, port):
        try:
            s = serial.Serial(port)
            s.close()
            return True
        except serial.SerialException:
            return False

    @pyqtSlot()
    def stop_scan(self):
        self.timer.stop()
        if self.pyvisa_rm:
            try:
                self.pyvisa_rm.close()
            except Exception as e:
                logging.warning(f"Error closing PyVISA RM: {e}")