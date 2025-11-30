import numpy as np
import queue
import time
import logging
import mariadb
from PyQt5.QtCore import QObject, QReadWriteLock

class DataManager(QObject):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.lock = QReadWriteLock()
        self._initialize_state()
        self._initialize_buffers()
        self._init_db_pool()

    def _initialize_state(self):
        self.db_queue = queue.Queue()
        self.db_pool = None
        
        # [중요] 대시보드가 참조하는 최신 값 캐시
        self.latest_readings = {
            'daq': {}, 'mag': [], 'th_o2': {}, 'arduino': {},
            'ups': {}, 'fire': {}, 'voc': {}, 'hv': {}
        }
        
        self.latest_board_temps = {}
        self.latest_ups_status = {}
        self.latest_fire_data = {'status_code': 0, 'is_fire': False, 'is_fault': False, 'msg': 'Wait...'}
        self.latest_voc_data = {'conc': 0.0, 'alarm': 0}
        self.latest_hv_values = {} 
        self.latest_radon_mu = 0.0
        self.latest_radon_sigma = 0.0
        self.latest_radon_state = "Init"
        self.latest_radon_countdown = -1
        self.is_pdu_connected = False
        self.hv_db_push_counter = 0
        self.emergency_shutdown_triggered = False
        self.pmt_map = self.config.get("pmt_position_map", {})
        self.last_analysis_df = None

    def _initialize_buffers(self):
        days = self.config.get('gui', {}).get('max_data_points_days', 31)
        m1m = days * 24 * 60; m10m = days * 24 * 6
        self.rtd_data = np.full((m1m, 3), np.nan); self.dist_data = np.full((m1m, 3), np.nan)
        self.radon_data = np.full((m10m, 2), np.nan); self.mag_data = np.full((m1m, 5), np.nan)
        self.th_o2_data = np.full((m1m, 4), np.nan); self.arduino_data = np.full((m1m, 10), np.nan)
        self.ups_data = np.full((m1m, 4), np.nan); self.voc_data = np.full((m1m, 2), np.nan)
        self.flame_data = np.full((m1m, 2), np.nan)
        
        self.hv_graph_data = {}
        if self.config.get('caen_hv', {}).get("enabled"):
            for s, b in self.config['caen_hv'].get('crate_map', {}).items():
                self.hv_graph_data[int(s)] = np.full((m1m, 1 + b.get('channels', 0)*2), np.nan)
        
        self._pointers = {'daq':0, 'radon':0, 'mag':0, 'th_o2':0, 'arduino':0, 'ups':0, 'voc':0, 'flame':0, 'hv_graph':{}}
        for s in self.hv_graph_data: self._pointers['hv_graph'][s] = 0
        self._max_lens = {'daq':m1m, 'radon':m10m, 'mag':m1m, 'th_o2':m1m, 'arduino':m1m, 'ups':m1m, 'voc':m1m, 'flame':m1m, 'hv_graph':m1m}

    def _init_db_pool(self):
        if self.config.get('database', {}).get('enabled'):
            try:
                c = self.config['database']; p = {'user':c['user'], 'password':c['password'], 'pool_name':'rene_pool', 'pool_size':3}
                if c.get('unix_socket'): p['unix_socket'] = c['unix_socket']
                else: p['host'] = c.get('host','127.0.0.1'); p['port'] = c.get('port',3306)
                self.db_pool = mariadb.ConnectionPool(**p)
            except Exception as e: logging.error(f"DB Pool Error: {e}")

    def close_db_pool(self):
        if self.db_pool: 
            try: self.db_pool.close() 
            except: pass

    def _inc_ptr(self, key):
        self._pointers[key] = (self._pointers[key] + 1) % self._max_lens[key]
        p = self._pointers[key]
        # 끊김 처리를 위한 NaN 삽입
        if key=='daq': self.rtd_data[p]=np.nan; self.dist_data[p]=np.nan
        elif key=='mag': self.mag_data[p]=np.nan
        elif key=='th_o2': self.th_o2_data[p]=np.nan
        elif key=='arduino': self.arduino_data[p]=np.nan
        elif key=='ups': self.ups_data[p]=np.nan
        elif key=='voc': self.voc_data[p]=np.nan
        elif key=='flame': self.flame_data[p]=np.nan

    # --- Update Methods (여기에 latest_readings 업데이트 추가됨) ---

    def update_daq_data(self, ts, data):
        self.lock.lockForWrite()
        try:
            # [Fix] 대시보드용 최신 값 저장
            self.latest_readings['daq'] = data 
            
            p = self._pointers['daq']
            r = data.get('rtd', []); d = data.get('dist', [])
            self.rtd_data[p] = [ts, r[0] if r else np.nan, r[1] if len(r)>1 else np.nan]
            self.dist_data[p] = [ts, d[0] if d else np.nan, d[1] if len(d)>1 else np.nan]
            self._inc_ptr('daq')
        finally: self.lock.unlock()

    def update_radon_data(self, ts, mu, sigma):
        self.lock.lockForWrite()
        try:
            p = self._pointers['radon']; self.radon_data[p] = [ts, mu]; self._inc_ptr('radon')
            self.latest_radon_mu = mu; self.latest_radon_sigma = sigma
        finally: self.lock.unlock()

    def update_mag_data(self, ts, mag):
        self.lock.lockForWrite()
        try:
            # [Fix] 대시보드용 최신 값 저장
            self.latest_readings['mag'] = mag
            
            p = self._pointers['mag']
            if len(mag)==4: self.mag_data[p] = [ts] + mag
            else: self.mag_data[p] = [ts] + [np.nan]*4
            self._inc_ptr('mag')
        finally: self.lock.unlock()

    def update_th_o2_data(self, ts, temp, humi, o2):
        self.lock.lockForWrite()
        try:
            # [Fix] 대시보드용 최신 값 저장
            self.latest_readings['th_o2'] = {'temp': temp, 'humi': humi, 'o2': o2}
            
            p = self._pointers['th_o2']; self.th_o2_data[p] = [ts, temp, humi, o2]; self._inc_ptr('th_o2')
        finally: self.lock.unlock()

    def update_arduino_data(self, ts, data):
        self.lock.lockForWrite()
        try:
            # [Fix] 대시보드용 최신 값 저장
            self.latest_readings['arduino'] = data
            
            p = self._pointers['arduino']
            self.arduino_data[p] = [
                ts, data.get('temp0'), data.get('humi0'), data.get('temp1'), data.get('humi1'),
                np.nan, np.nan, np.nan, np.nan, data.get('dist')
            ]
            self._inc_ptr('arduino')
        finally: self.lock.unlock()

    def update_ups_data(self, data):
        ts = time.time()
        self.lock.lockForWrite()
        try:
            self.latest_ups_status = data
            p = self._pointers['ups']
            self.ups_data[p] = [ts, data.get('LINEV',0), data.get('BCHARGE',0), data.get('TIMELEFT',0)]
            self._inc_ptr('ups')
        finally: self.lock.unlock()

    def update_fire_data(self, data):
        ts = time.time(); f = data.get('fire_detector', {})
        self.lock.lockForWrite()
        try:
            self.latest_fire_data = f
            p = self._pointers['flame']; self.flame_data[p] = [ts, f.get('status_code',0)]; self._inc_ptr('flame')
        finally: self.lock.unlock()

    def update_pid_data(self, data):
        ts = time.time(); v = data.get('voc_detector', {})
        self.lock.lockForWrite()
        try:
            self.latest_voc_data['conc'] = v.get('conc',0); self.latest_voc_data['alarm'] = v.get('alarm',0)
            p = self._pointers['voc']; self.voc_data[p] = [ts, v.get('conc',0)]; self._inc_ptr('voc')
        finally: self.lock.unlock()

    def update_hv_data(self, hv_data, board_temps):
        self.lock.lockForWrite()
        try:
            self.latest_board_temps.update(board_temps)
            self.latest_hv_values.update(hv_data)
        finally: self.lock.unlock()

    def sample_hv_for_graph(self):
        now = time.time()
        self.lock.lockForWrite()
        try:
            for (s, ch), v in self.latest_hv_values.items():
                if s in self.hv_graph_data:
                    p = self._pointers['hv_graph'][s]
                    if self.hv_graph_data[s][p, 0] != now: self.hv_graph_data[s][p, 0] = now
                    # V=1+ch*2, I=2+ch*2
                    if 1+ch*2 < self.hv_graph_data[s].shape[1]:
                        self.hv_graph_data[s][p, 1+ch*2] = v.get('VMon', np.nan)
                        self.hv_graph_data[s][p, 2+ch*2] = v.get('IMon', np.nan)
            
            for s in self.hv_graph_data:
                p = (self._pointers['hv_graph'][s] + 1) % self._max_lens['hv_graph']
                self._pointers['hv_graph'][s] = p
                self.hv_graph_data[s][p, :] = np.nan
        finally: self.lock.unlock()