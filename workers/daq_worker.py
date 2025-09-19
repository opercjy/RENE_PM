# workers/daq_worker.py (수정 완료)

import time
import numpy as np
import logging
import queue
import nidaqmx
from nidaqmx.constants import (RTDType, ResistanceConfiguration, TerminalConfiguration,
                               ExcitationSource, AcquisitionType)
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

class DaqWorker(QObject):
    avg_data_ready = pyqtSignal(float, dict)
    raw_data_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, daq_config, data_queue: queue.Queue):
        super().__init__()
        self._is_running = True
        self.config = daq_config
        self.data_queue = data_queue
        self.sampling_rate = self.config.get('sampling_rate', 1000)
        self.active_modules = []
        self.channel_map = {'rtd': [], 'volt': []}
        self.db_samples = {}
        # === 변경점 1: task 객체를 클래스 멤버로 관리 ===
        self.task = None

    def _find_modules_by_sn(self):
        try:
            connected_devices = {dev.serial_num: dev.name for dev in nidaqmx.system.System.local().devices}
            for module_config in self.config.get('modules', []):
                sn_str = module_config['serial_number']
                sn_int = int(sn_str, 16)
                if sn_int in connected_devices:
                    dev_name = connected_devices[sn_int]
                    module_info = module_config.copy(); module_info['device_name'] = dev_name
                    self.active_modules.append(module_info)
                    full_ch_names = [f"{dev_name}/{ch}" for ch in module_config['channels']]
                    self.channel_map[module_config['task_type']].extend(full_ch_names)
                    for ch in full_ch_names: self.db_samples[ch] = []
                    logging.info(f"Activated module {module_config['role']} (SN: {sn_str}) as {dev_name}")
            if not self.active_modules: raise RuntimeError("No DAQ modules specified in the config were found.")
            return True
        except Exception as e:
            self.error_occurred.emit(f"DAQ module scan error: {e}"); return False

    @pyqtSlot()
    def run(self):
        if not self._find_modules_by_sn(): return
        while self._is_running:
            try:
                # === 변경점 2: with 구문 대신 self.task에 직접 할당 ===
                self.task = nidaqmx.Task()
                self._configure_task(self.task)
                self.task.start()
                self._read_loop(self.task)
            except nidaqmx.errors.DaqError as e:
                # 종료 신호를 받은 상태에서 에러가 발생하면 루프 즉시 탈출
                if not self._is_running: break
                # 에러 코드 -200479는 task.read()가 task.close()에 의해 중단될 때 발생하므로, 정상적인 종료 과정으로 간주
                if e.error_code == -200479:
                    logging.info("DAQ read was correctly interrupted by task closure.")
                    break
                self.error_occurred.emit(f"NI-DAQ Error: {e}. Retrying in 10 seconds..."); time.sleep(10)
            except Exception as e:
                if not self._is_running: break
                self.error_occurred.emit(f"NI-DAQ Fatal Error: {e}"); break
            finally:
                # === 변경점 3: 루프가 끝나거나 예외 발생 시 반드시 task를 닫도록 finally 구문 추가 ===
                if self.task is not None:
                    self.task.close()
                    self.task = None
                    logging.info("DAQ task closed in finally block.")
    
    def _configure_task(self, task):
        if self.channel_map['rtd']: task.ai_channels.add_ai_rtd_chan(','.join(self.channel_map['rtd']), rtd_type=RTDType.PT_3851, resistance_config=ResistanceConfiguration.THREE_WIRE, current_excit_source=ExcitationSource.INTERNAL, current_excit_val=0.001)
        if self.channel_map['volt']: task.ai_channels.add_ai_voltage_chan(','.join(self.channel_map['volt']), min_val=0.0, max_val=10.0, terminal_config=TerminalConfiguration.DEFAULT)
        task.timing.cfg_samp_clk_timing(rate=self.sampling_rate, sample_mode=AcquisitionType.CONTINUOUS, samps_per_chan=self.sampling_rate)
    
    def _read_loop(self, task):
        all_channels = self.channel_map['rtd'] + self.channel_map['volt']
        while self._is_running:
            ts = time.time()
            data = task.read(number_of_samples_per_channel=self.sampling_rate)
            means = [np.mean(ch) for ch in data]
            raw_data_dict = dict(zip(all_channels, means))
            raw_data_for_ui = {'rtd': [], 'volt': []}
            for mod in self.active_modules:
                for ch_name in mod['channels']:
                    full_ch_name = f"{mod['device_name']}/{ch_name}"
                    if full_ch_name in raw_data_dict: raw_data_for_ui[mod['task_type']].append(raw_data_dict[full_ch_name])
            self.raw_data_ready.emit(raw_data_for_ui)
            self._process_and_enqueue(ts, raw_data_dict)

    def _process_and_enqueue(self, ts, raw_dict):
        for ch, val in raw_dict.items(): self.db_samples[ch].append(val)
        first_ch = next(iter(self.db_samples), None)
        if first_ch and len(self.db_samples[first_ch]) >= 60:
            avg_data_for_gui = {ch: np.mean(s) for ch, s in self.db_samples.items()}
            self._emit_avg_data(avg_data_for_gui)
            rtd_vals = [raw_dict[ch] for ch in self.channel_map['rtd'] if ch in raw_dict]
            volt_vals = [raw_dict[ch] for ch in self.channel_map['volt'] if ch in raw_dict]
            distances = []
            volt_idx = 0
            for mod in self.active_modules:
                if mod['task_type'] == 'volt':
                    for i in range(len(mod['channels'])):
                        distances.append(self.convert_voltage_to_distance(volt_vals[volt_idx], mod['mapping'][i]))
                        volt_idx += 1
            self._enqueue_db_data(ts, rtd_vals, distances)
            for ch in self.db_samples: self.db_samples[ch].clear()

    def _emit_avg_data(self, avg_data):
        avg_rtd_volt = {'rtd': [], 'volt': []}
        for mod in self.active_modules:
            for ch in mod['channels']:
                full_ch_name = f"{mod['device_name']}/{ch}"
                if full_ch_name in avg_data: avg_rtd_volt[mod['task_type']].append(avg_data[full_ch_name])
        distances, volt_idx = [], 0
        for mod in self.active_modules:
            if mod['task_type'] == 'volt':
                for i in range(len(mod['channels'])):
                    distances.append(self.convert_voltage_to_distance(avg_rtd_volt['volt'][volt_idx], mod['mapping'][i]))
                    volt_idx += 1
        avg_rtd_volt['dist'] = distances
        self.avg_data_ready.emit(time.time(), avg_rtd_volt)

    def _enqueue_db_data(self, ts, rtd_vals, dist_vals):
        data = (time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts)),
                round(rtd_vals[0], 2) if rtd_vals else None,
                round(rtd_vals[1], 2) if len(rtd_vals) > 1 else None,
                round(dist_vals[0], 1) if dist_vals else None,
                round(dist_vals[1], 1) if len(dist_vals) > 1 else None)
        self.data_queue.put({'type': 'DAQ', 'data': data})

    def convert_voltage_to_distance(self, v, m):
        try:
            v_min, v_max = m['volt_range']; d_min, d_max = m['dist_range_mm']
            return d_min + ((v - v_min) / (v_max - v_min)) * (d_max - d_min)
        except: return 0.0
            
    @pyqtSlot()
    def stop(self):
        # === 변경점 4: stop 메서드가 task를 직접, 명시적으로 닫도록 수정 ===
        logging.info("DAQWorker stop method called.")
        self._is_running = False
        if self.task is not None:
            try:
                logging.info("Explicitly closing DAQ task from stop() method...")
                self.task.close()
                self.task = None
                logging.info("DAQ task closed successfully from stop() method.")
            except Exception as e:
                logging.error(f"Error while explicitly closing DAQ task: {e}")