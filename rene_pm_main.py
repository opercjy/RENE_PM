import sys
import os
import time
import logging
import json
import signal
import numpy as np

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QTabWidget, QStatusBar, QLabel, QMessageBox, QTextEdit)
from PyQt5.QtCore import QTimer, pyqtSlot, QThread, Qt, pyqtSignal, QDate, QTime
from PyQt5.QtGui import QFont, QIcon

# --- [Managers] ---
from managers.data_manager import DataManager
from managers.plot_manager import PlotManager

# --- [Views] ---
from views.safety_view import SafetyView
from views.pdu_view import PDUView
from views.hv_view import HVControlView
from views.hv_grid_view import HVGridView
from views.dashboard_view import DashboardView
from views.analysis_view import AnalysisView
from views.ups_view import UPSView
from views.hv_graph_view import HVGraphView
from views.guide_view import GuideView

# --- [Workers] ---
from workers import (DatabaseWorker, DaqWorker, RadonWorker, MagnetometerWorker,
                     ThO2Worker, ArduinoWorker, HVWorker, AnalysisWorker, UPSWorker, PDUWorker,
                     FireWorker, PidWorker)
from workers.hardware_manager import HardwareManager

try:
    import sip
except ImportError:
    sip = None

CONFIG = {}

def load_config(config_file="config_v2.json"):
    global CONFIG
    if not os.path.exists(config_file):
        print(f"Error: Config file not found: {config_file}")
        sys.exit(1)
    with open(config_file, 'r', encoding='utf-8') as f:
        CONFIG = json.load(f)
    return CONFIG

class LogHandler(logging.Handler):
    def __init__(self, log_signal):
        super().__init__()
        self.sig = log_signal

    def emit(self, record):
        msg = self.format(record)
        self.sig.emit(msg)

class MainWindow(QMainWindow):
    sig_log = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        
        # 1. Managers
        self.data_manager = DataManager(self.config)
        self.plot_manager = PlotManager(self, self.data_manager)
        
        # 2. UI Setup
        self.labels = {}          
        self.safety_widgets = {}  
        self.curves = {}          
        self.plots = {}           
        self.hv_graph_views = []
        
        # 뷰 변수 초기화 (AttributeError 방지)
        self.view_safety = None
        self.view_pdu = None
        self.view_hv = None
        self.view_env = None
        self.view_ups = None
        self.view_hv_grid = None
        
        self.init_ui()
        self._init_curve_data_map()
        
        # 3. Workers
        self.threads = {}
        self.workers = {}
        self.plot_dirty_flags = {}
        
        self.init_workers()
        
        # 4. Timers (Dual Timer - 반응성 핵심)
        # Light: 1초 (텍스트, 상태값)
        self.timer_light = QTimer(self)
        self.timer_light.timeout.connect(self.update_gui_light)
        self.timer_light.start(1000)
        
        # Heavy: 3초 (그래프, 그리드 구조)
        self.timer_heavy = QTimer(self)
        self.timer_heavy.timeout.connect(self.update_gui_heavy)
        self.timer_heavy.start(3000)
        
        # 5. Logging
        lh = LogHandler(self.sig_log)
        lh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(lh)
        if hasattr(self, 'view_log'):
            self.sig_log.connect(self.view_log.append)

    def init_ui(self):
        self.setWindowTitle("RENE-PM v2.5 (Golden Master)")
        self.setGeometry(50, 50, 1920, 1080)
        
        central = QWidget(); self.setCentralWidget(central)
        main_vbox = QVBoxLayout(central)
        
        # [Header]
        lbl_title = QLabel("RENE-PM Integrated Monitoring System")
        lbl_title.setFont(QFont("Arial", 22, QFont.Bold))
        lbl_title.setAlignment(Qt.AlignCenter)
        main_vbox.addWidget(lbl_title)
        
        # [Middle]
        middle_hbox = QHBoxLayout()
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabBar::tab { min-width: 80px; padding: 6px; font-size: 11pt; font-weight: bold; }
            QTabBar::tab:selected { background-color: #e0e0e0; }
        """)
        
        # Tab Creation
        self.view_safety = SafetyView(self.config, self.data_manager)
        self.tabs.addTab(self.view_safety, "🛡️ Safety")
        
        if self.config.get('netio_pdu', {}).get('enabled'):
            self.view_pdu = PDUView(self.config, self.data_manager)
            self.tabs.addTab(self.view_pdu, "⚡ PDU")

        if self.config.get('caen_hv', {}).get("enabled"):
            self.view_hv = HVControlView(self.config)
            self.tabs.addTab(self.view_hv, "🎛️ HV Control")
            # HV Graphs
            crate = self.config['caen_hv'].get('crate_map', {})
            for s_str in sorted(crate.keys(), key=int):
                s_id = int(s_str); n_ch = crate[s_str].get('channels', 12)
                hv_g = HVGraphView(s_id, n_ch, self.data_manager)
                self.tabs.addTab(hv_g, f"📈 HV S{s_id}")
                self.hv_graph_views.append(hv_g)

        self.view_env = QWidget(); self.env_layout = QGridLayout(self.view_env)
        self.plot_manager.create_ui_elements(self.env_layout) 
        self.tabs.addTab(self.view_env, "🌡️ Graphs")
        
        self.view_ups = UPSView(self.config, self.data_manager)
        self.tabs.addTab(self.view_ups, "🔋 UPS")

        self.view_analysis = AnalysisView(self.config, self.data_manager)
        self.tabs.addTab(self.view_analysis, "🔍 Data")

        self.view_guide = GuideView()
        self.tabs.addTab(self.view_guide, "🗺️ Guide")

        self.view_log = QTextEdit(); self.view_log.setReadOnly(True); self.view_log.setFont(QFont("Consolas", 10))
        self.tabs.addTab(self.view_log, "📜 Logs")

        middle_hbox.addWidget(self.tabs, 75)
        
        if self.config.get('caen_hv', {}).get("enabled"):
            self.view_hv_grid = HVGridView(self.config)
            middle_hbox.addWidget(self.view_hv_grid, 25)
        else:
            middle_hbox.addStretch(0)

        main_vbox.addLayout(middle_hbox, 8)
        
        # [Footer]
        self.dashboard = DashboardView(self.config, self.data_manager)
        self.labels = self.dashboard.labels; self.dashboard.main_win = self 
        main_vbox.addWidget(self.dashboard, 2)
        
        # [Status Bar]
        self.status_bar = QStatusBar(); self.setStatusBar(self.status_bar)
        shifter = self.config.get("shifter_name", "Unknown")
        self.status_bar.addPermanentWidget(QLabel(f" 👤 Shifter: {shifter} "))
        self.lbl_clock = QLabel("00:00:00"); self.lbl_clock.setFont(QFont("Arial", 10))
        self.status_bar.addPermanentWidget(self.lbl_clock)
        
        logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
        
        # [중요] 탭 변경 시그널 연결 (UI 생성 완료 후)
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _init_curve_data_map(self):
        dm = self.data_manager
        self.curve_data_map = {
            "daq_ls_temp_L_LS_Temp": (dm.rtd_data[:, 0], dm.rtd_data[:, 1]),
            "daq_ls_temp_R_LS_Temp": (dm.rtd_data[:, 0], dm.rtd_data[:, 2]),
            "daq_ls_level_GdLS Level": (dm.dist_data[:, 0], dm.dist_data[:, 1]),
            "daq_ls_level_GCLS Level": (dm.dist_data[:, 0], dm.dist_data[:, 2]),
            "radon_Radon (μ)": (dm.radon_data[:, 0], dm.radon_data[:, 1]),
            "mag_Bx": (dm.mag_data[:, 0], dm.mag_data[:, 1]),
            "mag_By": (dm.mag_data[:, 0], dm.mag_data[:, 2]),
            "mag_Bz": (dm.mag_data[:, 0], dm.mag_data[:, 3]),
            "mag_|B|": (dm.mag_data[:, 0], dm.mag_data[:, 4]),
            "th_o2_temp_humi_Temp(°C)": (dm.th_o2_data[:, 0], dm.th_o2_data[:, 1]),
            "th_o2_temp_humi_Humi(%)": (dm.th_o2_data[:, 0], dm.th_o2_data[:, 2]),
            "th_o2_o2_Oxygen(%)": (dm.th_o2_data[:, 0], dm.th_o2_data[:, 3]),
            "arduino_temp_humi_T1(°C)": (dm.arduino_data[:, 0], dm.arduino_data[:, 1]),
            "arduino_temp_humi_H1(%)": (dm.arduino_data[:, 0], dm.arduino_data[:, 2]),
            "arduino_temp_humi_T2(°C)": (dm.arduino_data[:, 0], dm.arduino_data[:, 3]),
            "arduino_temp_humi_H2(%)": (dm.arduino_data[:, 0], dm.arduino_data[:, 4]),
            "arduino_dist_Dist(cm)": (dm.arduino_data[:, 0], dm.arduino_data[:, 9]),
            "ups_linev": (dm.ups_data[:, 0], dm.ups_data[:, 1]),
            "ups_bcharge": (dm.ups_data[:, 0], dm.ups_data[:, 2]),
            "voc_trend_VOC": (dm.voc_data[:, 0], dm.voc_data[:, 1]),
            "flame_trend_Flame Level": (dm.flame_data[:, 0], dm.flame_data[:, 1])
        }
        self.plot_manager.main_win.curve_data_map = self.curve_data_map

    def init_workers(self):
        # 1. HV
        if self.config.get('caen_hv', {}).get("enabled"):
            w = HVWorker(self.config['caen_hv'])
            self.view_hv.send_command.connect(w.execute_control_command)
            self.view_hv.request_setpoints.connect(w.fetch_setpoints)
            w.control_command_status.connect(self.view_hv.append_log)
            w.setpoints_ready.connect(self.view_hv.update_setpoints)
            w.data_ready.connect(self._on_hv_data)
            # [복원] 연결 상태 로그
            w.connection_status.connect(lambda c: logging.info(f"HV Connection: {'Connected' if c else 'Disconnected'}"))
            self._launch_worker('caen_hv', w)

        # 2. PDU
        if self.config.get('netio_pdu', {}).get('enabled'):
            w = PDUWorker(self.config['netio_pdu'])
            self.view_pdu.sig_control.connect(w.control_single_port)
            self.view_pdu.sig_control_all.connect(w.control_all_ports)
            w.sig_status_updated.connect(self.view_pdu.update_ui)
            w.sig_connection_changed.connect(self._on_pdu_conn) # DataManager & View Update
            w.sig_log_message.connect(self.view_pdu.append_log)
            w.sig_queue_data.connect(self.data_manager.db_queue.put)
            self._launch_worker('netio_pdu', w)

        # 3. Safety
        if self.config.get('fire_detector', {}).get('enabled'):
            w = FireWorker(self.config['fire_detector'], self.data_manager.db_queue)
            w.data_ready.connect(self._on_fire_data)
            self._launch_worker('fire_detector', w)
        
        if self.config.get('voc_detector', {}).get('enabled'):
            w = PidWorker(self.config['voc_detector'], self.data_manager.db_queue)
            w.data_ready.connect(self._on_voc_data)
            self._launch_worker('voc_detector', w)

        # 4. Env
        for name, WClass in [('daq', DaqWorker), ('radon', RadonWorker), ('magnetometer', MagnetometerWorker),
                             ('th_o2', ThO2Worker), ('arduino', ArduinoWorker), ('ups', UPSWorker)]:
            if self.config.get(name, {}).get('enabled'):
                w = WClass(self.config.get(name, {}), self.data_manager.db_queue)
                if name == 'daq': w.avg_data_ready.connect(self._on_daq_data)
                elif name == 'radon': w.data_ready.connect(self._on_radon_data)
                elif name == 'magnetometer': w.avg_data_ready.connect(self._on_mag_data)
                elif name == 'th_o2': w.avg_data_ready.connect(self._on_th_o2_data)
                elif name == 'arduino': w.avg_data_ready.connect(self._on_arduino_data)
                elif name == 'ups': w.data_ready.connect(self._on_ups_data)
                
                self._launch_worker(name, w)

        # 5. Hardware
        self.hw_thread = QThread()
        self.hw = HardwareManager(self.config)
        self.hw.moveToThread(self.hw_thread)
        # [복원] 하드웨어 감지 시 로그 출력
        self.hw.device_connected.connect(lambda n: logging.info(f"Hardware Detected: {n}"))
        self.hw_thread.started.connect(self.hw.start_scan)
        self.hw_thread.start()

        # 6. Database
        if self.config.get('database', {}).get('enabled'):
            w = DatabaseWorker(self.data_manager.db_pool, self.config['database'], self.data_manager.db_queue)
            self._launch_worker('db', w)

    def _launch_worker(self, name, worker):
        t = QThread(); worker.moveToThread(t)
        t.started.connect(worker.start_worker if hasattr(worker, 'start_worker') else worker.run)
        if hasattr(worker, 'error_occurred'): worker.error_occurred.connect(self._log_worker_error)
        t.start(); self.workers[name] = worker; self.threads[name] = t
        logging.info(f"Worker '{name}' launched.")

    # --- Slots ---
    @pyqtSlot(dict)
    def _on_hv_data(self, data):
        temps = {slot: d.get('board_temp') for slot, d in data.get('slots', {}).items()}
        self.data_manager.update_hv_data({}, temps)
        if hasattr(self, 'view_hv_grid'):
             for s, sd in data.get('slots', {}).items():
                 for c, p in sd.get('channels', {}).items(): self.view_hv_grid.update_status(s, c, p)
    
    @pyqtSlot(bool)
    def _on_pdu_conn(self, c):
        self.data_manager.lock.lockForWrite(); self.data_manager.is_pdu_connected = c; self.data_manager.lock.unlock()
        self.view_pdu.update_connection(c)

    @pyqtSlot(float, dict)
    def _on_daq_data(self, ts, d): self.data_manager.update_daq_data(ts, d); self.plot_dirty_flags['daq'] = True
    @pyqtSlot(float, float, float)
    def _on_radon_data(self, ts, mu, sigma): self.data_manager.update_radon_data(ts, mu, sigma); self.plot_dirty_flags['radon'] = True
    @pyqtSlot(float, list)
    def _on_mag_data(self, ts, m): self.data_manager.update_mag_data(ts, m); self.plot_dirty_flags['mag'] = True
    @pyqtSlot(float, float, float, float)
    def _on_th_o2_data(self, ts, t, h, o): self.data_manager.update_th_o2_data(ts, t, h, o); self.plot_dirty_flags['th_o2'] = True
    @pyqtSlot(float, dict)
    def _on_arduino_data(self, ts, d): self.data_manager.update_arduino_data(ts, d); self.plot_dirty_flags['arduino'] = True
    @pyqtSlot(dict)
    def _on_ups_data(self, d): self.data_manager.update_ups_data(d); self.plot_dirty_flags['ups'] = True
    @pyqtSlot(dict)
    def _on_fire_data(self, d): self.data_manager.update_fire_data(d); self.plot_dirty_flags['flame'] = True
    @pyqtSlot(dict)
    def _on_voc_data(self, d): self.data_manager.update_pid_data(d); self.plot_dirty_flags['voc'] = True

    @pyqtSlot(str)
    def _log_worker_error(self, msg): logging.error(msg); self.view_log.append(f"[ERROR] {msg}")

    # --- Loops ---
    @pyqtSlot()
    def update_gui_light(self):
        self.dashboard.update_ui()
        c = self.tabs.currentWidget()
        if c == self.view_safety: self.view_safety.update_ui()
        elif c == self.view_ups: self.view_ups.update_ui()
        self.lbl_clock.setText(QDate.currentDate().toString("yyyy-MM-dd") + " " + QTime.currentTime().toString("HH:mm:ss"))

    @pyqtSlot()
    def update_gui_heavy(self):
        if hasattr(self, 'view_hv_grid'): self.view_hv_grid.refresh_structure()
        c = self.tabs.currentWidget()
        if c == self.view_env:
            if self.plot_dirty_flags: self.plot_manager.update_plots(self.plot_dirty_flags); self.plot_dirty_flags.clear()
        elif c in self.hv_graph_views: c.update_ui()

    @pyqtSlot(int)
    def _on_tab_changed(self, i): self.update_gui_heavy()

    @pyqtSlot()
    def delayed_init(self): logging.info("System Ready")
    def closeEvent(self, e): self.data_manager.close_db_pool(); e.accept()

if __name__ == '__main__':
    load_config()
    app = QApplication(sys.argv)
    app.setStyleSheet("QWidget{font-size:12pt; font-family:'Arial';} QGroupBox{font-weight:bold; font-size:13pt;}")
    win = MainWindow(CONFIG)
    win.show()
    QTimer.singleShot(100, win.delayed_init)
    sys.exit(app.exec_())