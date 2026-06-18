# core/state_store.py (전체 덮어쓰기)

import time
import numpy as np
from PyQt6.QtCore import QObject, pyqtSlot
from core.event_bus import global_bus

class StateStore(QObject):
    def __init__(self, config):
        super().__init__()
        self.config = config
        
        self.pointers = {}
        self.max_lens = {}
        self.plot_dirty_flags = {}
        
        self.latest_raw_values = {}
        self.latest_ups_status = {}
        self.latest_board_temps = {}
        self.latest_hv_values = {}
        self.latest_fire_data = {'status_code': 0, 'is_fire': False, 'is_fault': False, 'msg': 'Wait...'}
        self.latest_voc_data = {'conc': 0.0, 'alarm': 0}
        self.latest_radon_data = {'mu': 0.0, 'sigma': 0.0}
        
        self.hv_graph_counter = 0  # [핵심] HV 그래프 업데이트 주기용 카운터

        self._init_data_arrays()
        global_bus.sensor_data_updated.connect(self._on_sensor_data_updated)

    def _init_data_arrays(self):
        days = self.config.get('gui', {}).get('max_data_points_days', 31)
        self.m1m_len = days * 24 * 60
        self.m10m_len = days * 24 * 6
        
        self.rtd_data = np.full((self.m1m_len, 3), np.nan)
        self.dist_data = np.full((self.m1m_len, 3), np.nan)
        self.radon_data = np.full((self.m10m_len, 2), np.nan)
        self.mag_data = np.full((self.m1m_len, 5), np.nan)
        self.th_o2_data = np.full((self.m1m_len, 4), np.nan)
        self.arduino_data = np.full((self.m1m_len, 10), np.nan)
        self.ups_data = np.full((self.m1m_len, 4), np.nan)
        self.voc_data = np.full((self.m1m_len, 2), np.nan)
        self.flame_data = np.full((self.m1m_len, 2), np.nan)
        
        self.hv_graph_data = {}
        if self.config.get('caen_hv', {}).get("enabled"):
            for slot_str, board in self.config['caen_hv'].get('crate_map', {}).items():
                slot = int(slot_str)
                channels = board.get('channels', 0)
                self.hv_graph_data[slot] = np.full((self.m1m_len, 1 + channels * 2), np.nan)
        
        self.pointers = {
            'daq': 0, 'radon': 0, 'mag': 0, 'th_o2': 0, 'arduino': 0, 
            'ups': 0, 'voc': 0, 'flame': 0, 'hv_graph': {}
        }
        for slot in self.hv_graph_data.keys():
            self.pointers['hv_graph'][slot] = 0
            
        self.max_lens = {
            'daq': self.m1m_len, 'radon': self.m10m_len, 'mag': self.m1m_len, 
            'th_o2': self.m1m_len, 'arduino': self.m1m_len, 'ups': self.m1m_len, 
            'voc': self.m1m_len, 'flame': self.m1m_len, 'hv_graph': self.m1m_len
        }

    def get_unrolled_data(self, array_prefix, ptr_key=None):
        ptr_key = ptr_key or array_prefix
        if ptr_key not in self.pointers: return None
        ptr = self.pointers[ptr_key]
        arr = getattr(self, f"{array_prefix}_data", None)
        if arr is None: return None
        if np.isnan(arr[ptr, 0]):
            return arr[:ptr]
        else:
            return np.concatenate((arr[ptr:], arr[:ptr]), axis=0)

    def get_unrolled_hv_data(self, slot):
        ptr = self.pointers['hv_graph'].get(slot, 0)
        arr = self.hv_graph_data.get(slot)
        if arr is None: return None
        if np.isnan(arr[ptr, 0]):
            return arr[:ptr]
        else:
            return np.concatenate((arr[ptr:], arr[:ptr]), axis=0)

    @pyqtSlot(str, dict)
    def _on_sensor_data_updated(self, sensor_type, payload):
        ts = payload.get('ts', time.time())
        data = payload.get('data', {})

        if sensor_type == 'daq_avg': self._update_daq_data(ts, data)
        elif sensor_type == 'radon_avg': self._update_radon_data(ts, data)
        elif sensor_type == 'mag_avg': self._update_mag_data(ts, data)
        elif sensor_type == 'th_o2_avg': self._update_th_o2_data(ts, data)
        elif sensor_type == 'arduino_avg': self._update_arduino_data(ts, data)
        elif sensor_type == 'ups_status': self._update_ups_data(ts, data)
        elif sensor_type == 'fire_status': self._update_fire_data(ts, data)
        elif sensor_type == 'voc_status': self._update_voc_data(ts, data)
        elif sensor_type == 'hv_status': self._update_hv_data(ts, data)
        elif sensor_type == 'raw_data': self.latest_raw_values.update(data)

    def _update_daq_data(self, ts, data):
        ptr = self.pointers['daq']
        rtd, dist = data.get('rtd', []), data.get('dist', [])
        self.rtd_data[ptr] = [ts, rtd[0] if rtd else np.nan, rtd[1] if len(rtd) > 1 else np.nan]
        self.dist_data[ptr] = [ts, dist[0] if dist else np.nan, dist[1] if len(dist) > 1 else np.nan]
        self.pointers['daq'] = (ptr + 1) % self.max_lens['daq']
        self.plot_dirty_flags.update({"daq_ls_temp_L_LS_Temp": True, "daq_ls_temp_R_LS_Temp": True,
                                      "daq_ls_level_GdLS Level": True, "daq_ls_level_GCLS Level": True})

    def _update_radon_data(self, ts, data):
        mu, sigma = data.get('mu', 0.0), data.get('sigma', 0.0)
        self.latest_radon_data = {'mu': mu, 'sigma': sigma}
        ptr = self.pointers['radon']
        self.radon_data[ptr] = [ts, mu]
        self.pointers['radon'] = (ptr + 1) % self.max_lens['radon']
        self.plot_dirty_flags["radon_Radon (μ)"] = True

    def _update_mag_data(self, ts, mag):
        ptr = self.pointers['mag']
        self.mag_data[ptr] = [ts] + mag
        self.pointers['mag'] = (ptr + 1) % self.max_lens['mag']
        self.plot_dirty_flags.update({"mag_Bx": True, "mag_By": True, "mag_Bz": True, "mag_|B|": True})

    def _update_th_o2_data(self, ts, data):
        ptr = self.pointers['th_o2']
        self.th_o2_data[ptr] = [ts, data.get('temp', np.nan), data.get('humi', np.nan), data.get('o2', np.nan)]
        self.pointers['th_o2'] = (ptr + 1) % self.max_lens['th_o2']
        self.plot_dirty_flags.update({"th_o2_temp_humi_Temp(°C)": True, "th_o2_temp_humi_Humi(%)": True, "th_o2_o2_Oxygen(%)": True})

    def _update_arduino_data(self, ts, data):
        ptr = self.pointers['arduino']
        self.arduino_data[ptr] = [ts, data.get('temp0', np.nan), data.get('humi0', np.nan), data.get('temp1', np.nan), data.get('humi1', np.nan), np.nan, np.nan, np.nan, np.nan, data.get('dist', np.nan)]
        self.pointers['arduino'] = (ptr + 1) % self.max_lens['arduino']
        self.plot_dirty_flags.update({"arduino_temp_humi_T1(°C)": True, "arduino_temp_humi_H1(%)": True, "arduino_temp_humi_T2(°C)": True, "arduino_temp_humi_H2(%)": True, "arduino_dist_Dist(cm)": True})

    def _update_ups_data(self, ts, data):
        self.latest_ups_status = data
        ptr = self.pointers['ups']
        self.ups_data[ptr] = [ts, data.get('LINEV', 0.0), data.get('BCHARGE', 0.0), data.get('TIMELEFT', 0.0)]
        self.pointers['ups'] = (ptr + 1) % self.max_lens['ups']
        self.plot_dirty_flags.update({"ups_linev": True, "ups_bcharge": True, "ups_timeleft": True})

    def _update_fire_data(self, ts, data):
        self.latest_fire_data = data
        ptr = self.pointers['flame']
        self.flame_data[ptr] = [ts, data.get('status_code', 0)]
        self.pointers['flame'] = (ptr + 1) % self.max_lens['flame']
        self.plot_dirty_flags["flame_trend_Flame Level"] = True

    def _update_voc_data(self, ts, data):
        self.latest_voc_data = data
        ptr = self.pointers['voc']
        self.voc_data[ptr] = [ts, data.get('conc', 0.0)]
        self.pointers['voc'] = (ptr + 1) % self.max_lens['voc']
        self.plot_dirty_flags["voc_trend_VOC"] = True

    def _update_hv_data(self, ts, data):
        """[핵심 추가] 최신값 갱신 및 1분마다 그래프 배열(hv_graph_data) 업데이트"""
        for slot, slot_data in data.get('slots', {}).items():
            board_temp = slot_data.get('board_temp')
            self.latest_board_temps[slot] = board_temp
            for channel, params in slot_data.get('channels', {}).items():
                self.latest_hv_values[(slot, channel)] = params

        self.hv_graph_counter += 1
        if self.hv_graph_counter >= 60:
            current_time = time.time()
            for (s, c), p in self.latest_hv_values.items():
                if s in self.hv_graph_data:
                    ptr = self.pointers['hv_graph'].get(s, 0)
                    self.hv_graph_data[s][ptr, 0] = current_time
                    self.hv_graph_data[s][ptr, 1 + c * 2] = p.get('VMon', np.nan)
                    self.hv_graph_data[s][ptr, 2 + c * 2] = p.get('IMon', np.nan)
            
            for s in self.hv_graph_data.keys():
                self.pointers['hv_graph'][s] = (self.pointers['hv_graph'].get(s, 0) + 1) % self.max_lens['hv_graph']
                self.plot_dirty_flags[f"hv_slot_{s}"] = True
            
            self.hv_graph_counter = 0
