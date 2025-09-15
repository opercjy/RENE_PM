import sys, time, numpy as np, os, math, signal, json, logging, queue
from typing import Dict, Any

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QGridLayout, QHBoxLayout, QVBoxLayout,
                             QMessageBox, QLabel, QFrame, QStatusBar, QGroupBox, QTabWidget, QScrollArea,
                             QSystemTrayIcon, QStyle, QAction, qApp, QMenu, QTextEdit, QPushButton, 
                             QDateEdit, QComboBox, QFormLayout, QSpinBox, QDoubleSpinBox)
from PyQt5.QtCore import QThread, QObject, pyqtSignal, pyqtSlot, Qt, QTimer, QMetaObject, QDate
from PyQt5.QtGui import QFont, QColor, QPalette, QIcon, QPixmap
import pyqtgraph as pg

import mariadb 

import pandas as pd
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.dates as mdates

from workers import (DatabaseWorker, DaqWorker, RadonWorker, MagnetometerWorker, 
                     ThO2Worker, ArduinoWorker, HVWorker, AnalysisWorker)
from workers.hardware_manager import HardwareManager

CONFIG = {}
def load_config(config_file="config_v2.json"):
    global CONFIG; script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
    config_path = os.path.join(script_dir, config_file)
    if not os.path.exists(config_path): print(f"Error: Config file not found: {config_path}"); sys.exit(1)
    try:
        with open(config_path, 'r', encoding='utf-8') as f: CONFIG = json.load(f)
        return CONFIG
    except json.JSONDecodeError as e: print(f"Error decoding JSON from {config_path}: {e}"); sys.exit(1)

class LogHandler(logging.Handler, QObject):
    new_log_message = pyqtSignal(str)
    def __init__(self):
        super().__init__()
        QObject.__init__(self)
    def emit(self, record):
        msg = self.format(record)
        self.new_log_message.emit(msg)

class ChannelWidget(QFrame):
    def __init__(self, slot, channel):
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel); self.setLineWidth(1); self.setMinimumSize(80, 50)
        layout = QVBoxLayout(self); layout.setContentsMargins(2, 2, 2, 2); layout.setSpacing(1)
        self.name_label = QLabel(f"S{slot}CH{channel}"); self.vmon_label = QLabel("--- V"); self.imon_label = QLabel("--- uA")
        font = QFont("Arial", 8, QFont.Bold); self.name_label.setFont(font); self.vmon_label.setFont(font); self.imon_label.setFont(font)
        self.name_label.setAlignment(Qt.AlignCenter); self.vmon_label.setAlignment(Qt.AlignCenter); self.imon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.name_label); layout.addWidget(self.vmon_label); layout.addWidget(self.imon_label)
        self.setAutoFillBackground(True); self.update_status({'Pw': False})

    def update_status(self, params):
        power = params.get('Pw', False); vmon = params.get('VMon', 0.0); imon = params.get('IMon', 0.0); v0set = params.get('V0Set', 0.0)
        palette = self.palette()
        if not power:
            color = QColor('#95A5A6'); text_color = QColor('white'); self.vmon_label.setText("Power Off"); self.imon_label.setText("")
        else:
            diff_percent = (abs(vmon - v0set) / v0set) * 100 if v0set > 0 else 0
            if diff_percent <= 5: color = QColor('#27AE60'); text_color = QColor('white')
            elif diff_percent <= 10: color = QColor('#F1C40F'); text_color = QColor('black')
            else: color = QColor('#C0392B'); text_color = QColor('white')
            self.vmon_label.setText(f"{vmon:.1f} V"); self.imon_label.setText(f"{imon:.2f} uA")
        palette.setColor(self.backgroundRole(), color); palette.setColor(QPalette.WindowText, text_color); self.setPalette(palette)

class MainWindow(QMainWindow):
    hv_control_command = pyqtSignal(dict)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.db_queue = queue.Queue()
        self.db_pool = None
        self.threads = {}
        self.latest_raw_values = {}
        self.plot_dirty_flags = {}
        self.indicator_colors = {}
        self.legend_to_label_map = {
            "L_LS_Temp": "L_LS_Temp", "R_LS_Temp": "R_LS_Temp", "GdLS Level": "GdLS_level", "GCLS Level": "GCLS_level",
            "Bx": "B_x", "By": "B_y", "Bz": "B_z", "|B|": "B", "Temp(°C)": "TH_O2_Temp", "Humi(%)": "TH_O2_Humi", "Oxygen(%)": "TH_O2_Oxygen",
            "T1(°C)": "Temp1", "H1(%)": "Humi1", "T2(°C)": "Temp2", "H2(%)": "Humi2", "Dist(cm)": "Dist"
        }
        self.ui_update_timer = QTimer(self); self.ui_update_timer.timeout.connect(self._update_gui); self.ui_update_timer.start(500)
        self.clock_timer = QTimer(self); self.clock_timer.timeout.connect(self._update_clock); self.clock_timer.start(1000)
        self.latest_hv_values = {}
        self.hv_graph_sampler_timer = QTimer(self); self.hv_graph_sampler_timer.timeout.connect(self._sample_hv_for_graph); self.hv_graph_sampler_timer.start(60000)
        self._init_data()
        self._init_ui()
        self._init_curve_data_map()
        self._init_tray_icon()
        if self.config.get('database',{}).get('enabled'):
            self._init_db_pool() # 풀 생성 메서드 호출
            self._start_db_worker()
        if self.config.get('caen_hv', {}).get("enabled"): self._start_worker('caen_hv')
        self.hw_thread = QThread(); self.hw_manager = HardwareManager(self.config)
        self.hw_manager.moveToThread(self.hw_thread); self.hw_manager.device_connected.connect(self.activate_sensor)
        self.hw_thread.started.connect(self.hw_manager.start_scan); self.hw_thread.start()

    def _init_db_pool(self):
        try:
            db_config = self.config['database']
            pool_config = {
                'user': db_config['user'],
                'password': db_config['password'],
                'pool_name': db_config.get('pool_name', 'rene_pm_default_pool'),
                'pool_size': db_config.get('pool_size', 3)
            }
            if db_config.get('unix_socket'):
                pool_config['unix_socket'] = db_config['unix_socket']
            else:
                pool_config['host'] = db_config.get('host', '127.0.0.1')
                pool_config['port'] = db_config.get('port', 3306)

            self.db_pool = mariadb.ConnectionPool(**pool_config)
            logging.info(f"Database connection pool '{pool_config['pool_name']}' created with size {pool_config['pool_size']}.")
        except mariadb.Error as e:
            self.show_error(f"Failed to create DB connection pool: {e}")
            self.db_pool = None

    def _init_data(self):
        # ... (이전과 동일)
        days = self.config.get('gui', {}).get('max_data_points_days', 31)
        self.m1m_len = days * 24 * 60; self.m10m_len = days * 24 * 6
        self.rtd_data = np.full((self.m1m_len, 3), np.nan); self.dist_data = np.full((self.m1m_len, 3), np.nan)
        self.radon_data = np.full((self.m10m_len, 2), np.nan); self.mag_data = np.full((self.m1m_len, 5), np.nan)
        self.th_o2_data = np.full((self.m1m_len, 4), np.nan); self.arduino_data = np.full((self.m1m_len, 6), np.nan)
        self.hv_graph_data = {}
        if self.config.get('caen_hv', {}).get("enabled"):
            for slot_str, board in self.config['caen_hv']['crate_map'].items():
                num_channels = board['channels']
                self.hv_graph_data[int(slot_str)] = np.full((self.m1m_len, 1 + num_channels * 2), np.nan)
        self.pointers = {'daq':0,'radon':0,'mag':0,'th_o2':0,'arduino':0,'hv_graph':{}}
        for slot_str in self.hv_graph_data.keys(): self.pointers['hv_graph'][slot_str] = 0
        self.max_lens = {'daq': self.m1m_len, 'radon': self.m10m_len, 'mag': self.m1m_len, 'th_o2': self.m1m_len, 'arduino': self.m1m_len, 'hv_graph': self.m1m_len}

    def _init_ui(self):
        # ... (이전과 동일)
        self.setWindowTitle("RENE-PM v2.0 - Integrated Environment & HV Monitoring")
        self.setGeometry(50, 50, 1920, 1080)
        self.status_bar = QStatusBar(self); self.setStatusBar(self.status_bar)
        central_widget = QWidget(); self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        self.plots, self.curves, self.labels, self.hv_slot_curves = {}, {}, {}, {}
        title_label = QLabel("RENE-PM Integrated Monitoring System")
        title_label.setFont(QFont("Arial", 20, QFont.Bold)); title_label.setAlignment(Qt.AlignCenter)
        title_label.setContentsMargins(10,10,10,10); main_layout.addWidget(title_label)
        top_panel = QWidget()
        top_layout = QHBoxLayout(top_panel)
        main_layout.addWidget(top_panel, 8)
        bottom_panel = self._create_indicator_panel()
        main_layout.addWidget(bottom_panel, 2)
        graph_tab_panel = self._create_graph_tab_panel()
        hv_grid_panel = self._create_hv_grid_panel()
        top_layout.addWidget(graph_tab_panel, 7)
        top_layout.addWidget(hv_grid_panel, 3)
        shifter_text = self.config.get("shifter_name", "Unknown Shifter")
        self.shifter_label = QLabel(f" Shifter: {shifter_text} "); self.clock_label = QLabel()
        self.status_bar.addPermanentWidget(self.shifter_label); self.status_bar.addPermanentWidget(self.clock_label)
        self._update_clock()
    
    def _init_curve_data_map(self):
        # ... (이전과 동일)
        self.curve_data_map = {
            "daq_ls_temp_L_LS_Temp": (self.rtd_data[:, 0], self.rtd_data[:, 1]), "daq_ls_temp_R_LS_Temp": (self.rtd_data[:, 0], self.rtd_data[:, 2]),
            "daq_ls_level_GdLS Level": (self.dist_data[:, 0], self.dist_data[:, 1]), "daq_ls_level_GCLS Level": (self.dist_data[:, 0], self.dist_data[:, 2]),
            "radon_Radon (μ)": (self.radon_data[:, 0], self.radon_data[:, 1]), "mag_Bx": (self.mag_data[:, 0], self.mag_data[:, 1]), 
            "mag_By": (self.mag_data[:, 0], self.mag_data[:, 2]), "mag_Bz": (self.mag_data[:, 0], self.mag_data[:, 3]), 
            "mag_|B|": (self.mag_data[:, 0], self.mag_data[:, 4]), "th_o2_temp_humi_Temp(°C)": (self.th_o2_data[:, 0], self.th_o2_data[:, 1]),
            "th_o2_temp_humi_Humi(%)": (self.th_o2_data[:, 0], self.th_o2_data[:, 2]), "th_o2_o2_Oxygen(%)": (self.th_o2_data[:, 0], self.th_o2_data[:, 3]),
            "arduino_temp_humi_T1(°C)": (self.arduino_data[:, 0], self.arduino_data[:, 1]), "arduino_temp_humi_H1(%)": (self.arduino_data[:, 0], self.arduino_data[:, 2]),
            "arduino_temp_humi_T2(°C)": (self.arduino_data[:, 0], self.arduino_data[:, 3]), "arduino_temp_humi_H2(%)": (self.arduino_data[:, 0], self.arduino_data[:, 4]),
            "arduino_dist_Dist(cm)": (self.arduino_data[:, 0], self.arduino_data[:, 5]),
        }

    def _create_graph_tab_panel(self):
        # ... (이전과 동일)
        tab_widget = QTabWidget()
        if self.config.get('caen_hv', {}).get("enabled"):
            hv_control_panel = self._create_hv_control_panel()
            tab_widget.addTab(hv_control_panel, "HV Control")
        env_panel = self._create_environment_panel()
        tab_widget.addTab(env_panel, "Environment Graphs")
        analysis_panel = self._create_analysis_panel()
        tab_widget.addTab(analysis_panel, "Analysis")
        if self.config.get('caen_hv', {}).get("enabled"):
            crate_map = self.config['caen_hv']['crate_map']
            for slot_str, board in crate_map.items():
                slot_panel = self._create_hv_slot_graph_panel(int(slot_str), board['channels'])
                tab_widget.addTab(slot_panel, f"HV Slot {slot_str} Graphs")
        guide_panel = self._create_guide_panel()
        tab_widget.addTab(guide_panel, "Guide")
        return tab_widget

    def _create_environment_panel(self):
        # ... (이전과 동일)
        container = QGroupBox("Environment Time-Series"); container.setFont(QFont("Arial", 12, QFont.Bold))
        plot_layout = QGridLayout(container)
        self._create_ui_elements(plot_layout)
        return container

    # === 변경점 1: HV Control 버튼 스타일 및 확인창 로직 추가 ===
    def _create_hv_control_panel(self):
        container = QWidget()
        main_layout = QHBoxLayout(container)
        control_group = QGroupBox("HV Channel Control"); control_layout = QFormLayout(control_group)
        self.control_slot_combo = QComboBox(); self.control_slot_combo.addItems(self.config['caen_hv']['crate_map'].keys())
        self.control_ch_start = QSpinBox(); self.control_ch_start.setRange(0, 99)
        self.control_ch_end = QSpinBox(); self.control_ch_end.setRange(0, 99)
        self.control_v0_spinbox = QDoubleSpinBox(); self.control_v0_spinbox.setRange(0, 3000); self.control_v0_spinbox.setSuffix(" V")
        self.control_i0_spinbox = QDoubleSpinBox(); self.control_i0_spinbox.setRange(0, 1000); self.control_i0_spinbox.setSuffix(" uA")
        
        apply_button = QPushButton("Apply Settings")
        apply_button.setStyleSheet("background-color: #3498DB; color: white;") # 파란색 스타일 적용
        apply_button.clicked.connect(self._send_hv_param_command)
        
        power_on_button = QPushButton("Power ON"); power_on_button.setStyleSheet("background-color: #27AE60; color: white;")
        power_on_button.clicked.connect(lambda: self._send_hv_power_command(True))
        power_off_button = QPushButton("Power OFF"); power_off_button.setStyleSheet("background-color: #C0392B; color: white;")
        power_off_button.clicked.connect(lambda: self._send_hv_power_command(False))
        
        control_layout.addRow("Slot:", self.control_slot_combo); control_layout.addRow("Channel Start:", self.control_ch_start)
        control_layout.addRow("Channel End:", self.control_ch_end); control_layout.addRow("Set Voltage (V0Set):", self.control_v0_spinbox)
        control_layout.addRow("Set Current (I0Set):", self.control_i0_spinbox); control_layout.addRow(apply_button)
        control_layout.addRow(power_on_button, power_off_button)
        log_group = QGroupBox("Control Status"); log_layout = QVBoxLayout(log_group)
        self.hv_control_log = QTextEdit(); self.hv_control_log.setReadOnly(True)
        log_layout.addWidget(self.hv_control_log)
        main_layout.addWidget(control_group, 1); main_layout.addWidget(log_group, 2)
        return container

    def _create_analysis_panel(self):
        container = QWidget()
        main_layout = QVBoxLayout(container)
        control_panel = QFrame(); control_panel.setFrameShape(QFrame.StyledPanel)
        control_layout = QHBoxLayout(control_panel)
        self.analysis_combo = QComboBox()
        
        # === 변경점 2: SQL 예약어 문제를 피하기 위해 모든 컬럼명에 백틱(`) 추가 ===
        self.analysis_map = {
            "LS Temperature (°C)": "SELECT `datetime`, `RTD_1`, `RTD_2` FROM LS_DATA",
            "LS Level (mm)": "SELECT `datetime`, `DIST_1`, `DIST_2` FROM LS_DATA",
            "Magnetometer (mG)": "SELECT `datetime`, `Bx`, `By`, `Bz`, `B_mag` FROM MAGNETOMETER_DATA",
            "Radon (Bq/m³)": "SELECT `datetime`, `mu` FROM RADON_DATA",
            "TH/O2 Sensor": "SELECT `datetime`, `temperature`, `humidity`, `oxygen` FROM TH_O2_DATA",
            "Arduino Sensor": "SELECT `datetime`, `analog_1`, `analog_2`, `analog_3`, `analog_4`, `analog_5` FROM ARDUINO_DATA",
            "High Voltage (HV)": "HV_QUERY"
        }

        self.analysis_combo.addItems(self.analysis_map.keys())
        self.analysis_combo.currentTextChanged.connect(self._on_analysis_type_changed)
        self.env_control_widget = QWidget()
        env_layout = QFormLayout(self.env_control_widget)
        self.start_date_edit = QDateEdit(QDate.currentDate().addDays(-7)); self.end_date_edit = QDateEdit(QDate.currentDate())
        self.start_date_edit.setCalendarPopup(True); self.end_date_edit.setCalendarPopup(True)
        env_layout.addRow("Start Date:", self.start_date_edit); env_layout.addRow("End Date:", self.end_date_edit)
        self.hv_control_widget = QWidget()
        hv_layout = QFormLayout(self.hv_control_widget)
        self.hv_slot_combo = QComboBox()
        if self.config.get('caen_hv', {}).get("enabled"): self.hv_slot_combo.addItems(self.config['caen_hv']['crate_map'].keys())
        self.hv_ch_start = QSpinBox(); self.hv_ch_start.setRange(0, 99); self.hv_ch_end = QSpinBox(); self.hv_ch_end.setRange(0, 99)
        hv_layout.addRow("Slot:", self.hv_slot_combo); hv_layout.addRow("Channel Start:", self.hv_ch_start); hv_layout.addRow("Channel End:", self.hv_ch_end)
        self.hv_control_widget.hide()
        self.plot_button = QPushButton("Plot Data"); self.plot_button.clicked.connect(self._run_analysis)
        type_layout = QFormLayout(); type_layout.addRow("Data Type:", self.analysis_combo)
        control_layout.addLayout(type_layout); control_layout.addWidget(self.env_control_widget); control_layout.addWidget(self.hv_control_widget)
        control_layout.addWidget(self.plot_button); control_layout.addStretch()
        self.analysis_canvas = FigureCanvas(Figure(figsize=(15, 6)))
        main_layout.addWidget(control_panel); main_layout.addWidget(self.analysis_canvas)
        return container
        
    def _create_hv_grid_panel(self):
        # ... (이전과 동일)
        hv_container_group = QGroupBox("CAEN High Voltage Status"); hv_container_group.setFont(QFont("Arial", 12, QFont.Bold))
        hv_main_layout = QVBoxLayout(hv_container_group)
        self.hv_channel_widgets = {}
        caen_config = self.config.get('caen_hv', {})
        if caen_config.get("enabled"):
            crate_map = caen_config.get('crate_map', {}); display_channels = caen_config.get('display_channels', {})
            for slot_str, board_info in crate_map.items():
                slot = int(slot_str)
                slot_group = QGroupBox(f"Slot {slot}: {board_info.get('description', '')}"); slot_group.setFont(QFont("Arial", 10))
                slot_layout = QGridLayout(slot_group); slot_layout.setAlignment(Qt.AlignLeft)
                hv_main_layout.addWidget(slot_group)
                channels_to_display = []
                display_config = display_channels.get(slot_str)
                if display_config == "all": channels_to_display = range(board_info['channels'])
                elif isinstance(display_config, list): channels_to_display = display_config
                num_cols = 6
                for i, ch in enumerate(channels_to_display):
                    widget = ChannelWidget(slot, ch); widget.setVisible(False)
                    self.hv_channel_widgets[(slot, ch)] = widget
                    slot_layout.addWidget(widget, i // num_cols, i % num_cols)
        return hv_container_group
    
    def _create_hv_slot_graph_panel(self, slot, num_channels):
        # ... (이전과 동일)
        container = QWidget(); layout = QHBoxLayout(container)
        def style_plot(plot_widget, title, y_label):
            plot_widget.setBackground('w'); plot_widget.setTitle(title, size='12pt')
            if num_channels <= 16: plot_widget.addLegend()
            plot_widget.showGrid(x=True, y=True, alpha=0.3); plot_widget.setAxisItems({'bottom': pg.DateAxisItem(orientation='bottom')})
            plot_widget.getAxis('left').setLabel(y_label); plot_widget.getAxis('bottom').setLabel('Time')
        v_plot = pg.PlotWidget(); style_plot(v_plot, f"Slot {slot} - Voltage (VMon)", "Voltage (V)")
        i_plot = pg.PlotWidget(); style_plot(i_plot, f"Slot {slot} - Current (IMon)", "Current (uA)")
        layout.addWidget(v_plot); layout.addWidget(i_plot)
        self.hv_slot_curves[slot] = []
        cmap = pg.colormap.get('viridis'); colors = cmap.getLookupTable(nPts=num_channels)
        for ch in range(num_channels):
            color = colors[ch]
            v_curve = v_plot.plot(pen=pg.mkPen(color=color, width=2), name=f"CH{ch}")
            i_curve = i_plot.plot(pen=pg.mkPen(color=color, width=2), name=f"CH{ch}")
            self.hv_slot_curves[slot].append({'v': v_curve, 'i': i_curve})
        return container

    def _create_indicator_panel(self):
        # ... (이전과 동일)
        indicator_group_box = QGroupBox("Real-time Indicators"); indicator_group_box.setFont(QFont("Arial", 12, QFont.Bold))
        panel_layout = QHBoxLayout(indicator_group_box)
        env_indicator_widget = QWidget(); env_indicator_layout = QHBoxLayout(env_indicator_widget)
        env_indicator_layout.setAlignment(Qt.AlignLeft)
        env_groups = {"LS (NI-cDAQ)":["L_LS_Temp","R_LS_Temp","GdLS_level","GCLS_level"],"Magnetometer":["B_x","B_y","B_z","B"],"TH/O2 Sensor":["TH_O2_Temp","TH_O2_Humi","TH_O2_Oxygen"], "Arduino":["Temp1","Humi1","Temp2","Humi2","Dist"],"Radon":["Radon_Value","Radon_Status"]}
        for title, labels in env_groups.items():
            group_frame = QFrame(); group_frame.setFrameShape(QFrame.StyledPanel); group_layout = QVBoxLayout(group_frame)
            g_lbl = QLabel(title); g_lbl.setFont(QFont("Arial", 15, QFont.Bold)); group_layout.addWidget(g_lbl)
            for name in labels:
                lbl = QLabel(f"{name.replace('_', ' ')}: -"); lbl.setFont(QFont("Arial", 13))
                self.labels[name] = lbl; lbl.setVisible(False); group_layout.addWidget(lbl)
            group_layout.addStretch(1); env_indicator_layout.addWidget(group_frame)
        log_viewer_group = QGroupBox("Log Viewer"); log_viewer_layout = QVBoxLayout(log_viewer_group)
        self.log_viewer_text = QTextEdit(); self.log_viewer_text.setReadOnly(True); self.log_viewer_text.setFont(QFont("Consolas", 9))
        log_viewer_layout.addWidget(self.log_viewer_text)
        notes_group = QGroupBox("Notes"); notes_layout = QVBoxLayout(notes_group)
        self.notes_edit = QTextEdit(); self.notes_edit.setReadOnly(True); notes_layout.addWidget(self.notes_edit)
        try:
            with open("notes.md", "r", encoding="utf-8") as f: self.notes_edit.setMarkdown(f.read())
        except FileNotFoundError: self.notes_edit.setText("Project root folder에 notes.md 파일을 생성하세요.")
        panel_layout.addWidget(env_indicator_widget, 5); panel_layout.addWidget(log_viewer_group, 2); panel_layout.addWidget(notes_group, 3)
        return indicator_group_box
    
    def _create_guide_panel(self):
        # ... (이전과 동일)
        guide_label = QLabel(); guide_label.setAlignment(Qt.AlignCenter); guide_label.setScaledContents(True)
        guide_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guide.png")
        if os.path.exists(guide_path):
            pixmap = QPixmap(guide_path); guide_label.setPixmap(pixmap)
        else:
            guide_label.setText("Guide image (guide.png) not found in project root folder."); guide_label.setFont(QFont("Arial", 16))
        scroll = QScrollArea(); scroll.setWidget(guide_label); scroll.setWidgetResizable(True)
        return scroll

    def _create_plot_group(self, group_key, configs):
        # ... (이전과 동일)
        container = QGroupBox(configs[0][1]); container.setFont(QFont("Arial", 10, QFont.Bold))
        group_layout = QVBoxLayout(container); group_layout.setContentsMargins(2, 2, 2, 2)
        color_palette = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
        color_index = 0
        for key, title, y_lbl, legends, _ in configs:
            plot = pg.PlotWidget(); plot.setBackground('w'); plot.showGrid(x=True,y=True,alpha=0.3)
            plot.setAxisItems({'bottom':pg.DateAxisItem(orientation='bottom')}); plot.getAxis('left').setLabel(y_lbl)
            legend = plot.addLegend(offset=(10,10)); legend.setBrush(pg.mkBrush(255, 255, 255, 150))
            for i, name in enumerate(legends):
                pen_color = color_palette[color_index % len(color_palette)]
                self.curves[f"{key}_{name}"] = plot.plot(pen=pg.mkPen(pen_color, width=2.5), name=name)
                if name in self.legend_to_label_map:
                    label_key = self.legend_to_label_map[name]
                    self.indicator_colors[label_key] = pen_color
                color_index += 1
            group_layout.addWidget(plot)
        self.plots[group_key] = container; container.setVisible(False)
        return container

    def _create_ui_elements(self, layout: QGridLayout):
        # ... (이전과 동일)
        self.plots['daq_temp'] = self._create_plot_group('daq_temp',[('daq_ls_temp',"LS Temperature (°C)","°C",["L_LS_Temp","R_LS_Temp"],[])])
        self.plots['daq_level'] = self._create_plot_group('daq_level',[('daq_ls_level',"LS Level (mm)","mm",["GdLS Level","GCLS Level"],[])])
        self.plots['th_o2'] = self._create_plot_group('th_o2',[('th_o2_temp_humi',"TH/O2 Sensor","Value",["Temp(°C)","Humi(%)"],[]), ('th_o2_o2',"O2 Concentration","%",["Oxygen(%)"],[])])
        self.plots['arduino'] = self._create_plot_group('arduino',[('arduino_temp_humi',"Arduino Sensor","Value",["T1(°C)","H1(%)","T2(°C)","H2(%)"],[]), ('arduino_dist',"Distance","cm",["Dist(cm)"],[])])
        self.plots['radon'] = self._create_plot_group('radon',[('radon',"Radon (Bq/m³)","Bq/m³",["Radon (μ)"],[])])
        self.plots['mag'] = self._create_plot_group('mag',[('mag',"Magnetometer (mG)","mG",["Bx","By","Bz","|B|"],[])])
        layout.addWidget(self.plots['daq_temp'], 0, 0); layout.addWidget(self.plots['th_o2'], 0, 1); layout.addWidget(self.plots['mag'], 0, 2)
        layout.addWidget(self.plots['daq_level'], 1, 0); layout.addWidget(self.plots['arduino'], 1, 1); layout.addWidget(self.plots['radon'], 1, 2)
        for plot_widget in self.plots.values(): plot_widget.setVisible(True)

    def _convert_daq_voltage_to_distance(self, v, mapping_index):
        # ... (이전과 동일)
        try:
            daq_config = self.config.get('daq', {}); volt_module = next((mod for mod in daq_config.get('modules', []) if mod['task_type'] == 'volt'), None)
            if volt_module:
                m = volt_module['mapping'][mapping_index]
                v_min, v_max = m['volt_range']; d_min, d_max = m['dist_range_mm']
                return d_min + ((v - v_min) / (v_max - v_min)) * (d_max - d_min)
        except (IndexError, KeyError, StopIteration, TypeError) as e:
            logging.warning(f"Failed to convert voltage to distance: {e}"); return 0.0

    @pyqtSlot(str)
    def _update_hv_control_status(self, message):
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        self.hv_control_log.append(f"[{timestamp}] {message}")

    def _send_hv_param_command(self):
        slot = int(self.control_slot_combo.currentText()); ch_start = self.control_ch_start.value(); ch_end = self.control_ch_end.value()
        v0 = self.control_v0_spinbox.value(); i0 = self.control_i0_spinbox.value()
        
        reply = QMessageBox.question(self, 'Confirm Action', 
            f"Apply V0Set={v0}V, I0Set={i0}uA to Slot {slot}, Channels {ch_start}-{ch_end}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            channels = list(range(ch_start, ch_end + 1))
            params_to_set = {'V0Set': v0, 'I0Set': i0}
            command = {'type': 'set_params', 'slot': slot, 'channels': channels, 'params': params_to_set}
            self.hv_control_command.emit(command)

    def _send_hv_power_command(self, power_state):
        # ... (이전과 동일)
        slot = int(self.control_slot_combo.currentText()); ch_start = self.control_ch_start.value(); ch_end = self.control_ch_end.value()
        reply = QMessageBox.question(self, 'Confirm Action', 
            f"Are you sure you want to turn Power {'ON' if power_state else 'OFF'} for Slot {slot}, Channels {ch_start}-{ch_end}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            channels = list(range(ch_start, ch_end + 1))
            command = {'type': 'set_power', 'slot': slot, 'channels': channels, 'value': power_state}
            self.hv_control_command.emit(command)

    def _on_analysis_type_changed(self, text):
        # ... (이전과 동일)
        if text == "High Voltage (HV)":
            self.env_control_widget.hide(); self.hv_control_widget.show()
        else:
            self.hv_control_widget.hide(); self.env_control_widget.show()

    def _run_analysis(self):
        if not self.db_pool:
            self.show_error("Database connection pool is not available.")
            return
        
        self.plot_button.setEnabled(False); self.plot_button.setText("Loading...")
        
        analysis_type = self.analysis_combo.currentText()
        query = self.analysis_map[analysis_type]
        
        if query == "HV_QUERY":
            slot = self.hv_slot_combo.currentText(); ch_start = self.hv_ch_start.value(); ch_end = self.hv_ch_end.value()
            query = f"SELECT `datetime`, `channel`, `vmon`, `imon` FROM HV_DATA WHERE `slot` = ? AND `channel` BETWEEN ? AND ?"
            params = [int(slot), ch_start, ch_end]
        else:
            start_date = self.start_date_edit.date().toString("yyyy-MM-dd 00:00:00")
            end_date = self.end_date_edit.date().toString("yyyy-MM-dd 23:59:59")
            query = f"{query} WHERE `datetime` BETWEEN ? AND ?"
            params = [start_date, end_date]
            
        # === 변경점: AnalysisWorker에 db_config 추가 전달 ===
        self.analysis_thread = AnalysisWorker(self.db_pool, self.config['database'], query, params)
        self.analysis_thread.analysis_complete.connect(self._plot_analysis_data)
        self.analysis_thread.error_occurred.connect(self.show_error)
        self.analysis_thread.finished.connect(self._on_analysis_finished)
        self.analysis_thread.start()

    def _plot_analysis_data(self, df):
        # ... (이전과 동일)
        if df.empty:
            self.show_error("No data found for the selected period."); return
        self.analysis_canvas.figure.clear()
        df['datetime'] = pd.to_datetime(df['datetime'])
        analysis_type = self.analysis_combo.currentText()
        if analysis_type == "High Voltage (HV)":
            v_ax, i_ax = self.analysis_canvas.figure.subplots(2, 1, sharex=True)
            self.analysis_canvas.figure.suptitle(f"Analysis of {analysis_type}", fontsize=16)
            v_ax.set_ylabel("Voltage (VMon)"); i_ax.set_ylabel("Current (IMon)")
            df_v_pivot = df.pivot(index='datetime', columns='channel', values='vmon')
            df_i_pivot = df.pivot(index='datetime', columns='channel', values='imon')
            for channel in df_v_pivot.columns:
                v_ax.plot(df_v_pivot.index, df_v_pivot[channel], marker='o', linestyle='-', markersize=2, label=f'Ch {channel}')
            for channel in df_i_pivot.columns:
                i_ax.plot(df_i_pivot.index, df_i_pivot[channel], marker='o', linestyle='-', markersize=2, label=f'Ch {channel}')
            v_ax.legend(); i_ax.legend()
            v_ax.grid(True); i_ax.grid(True)
        else:
            ax = self.analysis_canvas.figure.add_subplot(111)
            ax.set_title(f"Analysis of {analysis_type}", fontsize=16)
            df.set_index('datetime', inplace=True)
            ax.set_ylabel(analysis_type.split(' ')[-1])
            for column in df.columns:
                ax.plot(df.index, df[column], marker='o', linestyle='-', markersize=2, label=column)
            ax.legend()
            ax.grid(True)
        self.analysis_canvas.figure.autofmt_xdate()
        self.analysis_canvas.figure.tight_layout(rect=[0, 0, 1, 0.96])
        self.analysis_canvas.draw()

    def _on_analysis_finished(self):
        # ... (이전과 동일)
        self.plot_button.setEnabled(True); self.plot_button.setText("Plot Data")
    
    # ... (나머지 모든 코드는 이전과 동일)
    @pyqtSlot(str)
    def _update_log_viewer(self, message): self.log_viewer_text.append(message.strip())
    @pyqtSlot()
    def _update_clock(self): now = time.strftime('%Y-%m-%d %H:%M:%S'); self.clock_label.setText(f" {now} ")
    @pyqtSlot(str)
    def _update_radon_status(self, status_text):
        if "Radon_Status" in self.labels: self.labels["Radon_Status"].setText(f"Status: {status_text}")
    @pyqtSlot(dict)
    def _update_hv_ui(self, data):
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S'); db_data_to_queue = []
        for slot, slot_data in data.items():
            for channel, params in slot_data.items():
                key = (slot, channel)
                if key in self.hv_channel_widgets:
                    widget = self.hv_channel_widgets[key]; power_status = params.get('Pw', False)
                    if widget.isVisible() != power_status: widget.setVisible(power_status)
                    if power_status: widget.update_status(params)
                self.latest_hv_values[key] = {'VMon': params.get('VMon', np.nan), 'IMon': params.get('IMon', np.nan)}
                db_data_to_queue.append({'type': 'HV', 'data': (timestamp, slot, channel, params.get('Pw'), params.get('VMon'), params.get('IMon'), params.get('V0Set'), params.get('I0Set'), params.get('Status'))})
        for item in db_data_to_queue: self.db_queue.put(item)
    @pyqtSlot(bool)
    def _update_hv_connection(self, is_connected): status = "Connected" if is_connected else "Disconnected"; logging.info(f"HV Connection Status Changed: {status}")
    @pyqtSlot()
    def _sample_hv_for_graph(self):
        current_time = time.time()
        for (slot, ch), values in self.latest_hv_values.items():
            if slot in self.hv_graph_data:
                ptr = self.pointers['hv_graph'].get(slot, 0)
                self.hv_graph_data[slot][ptr, 0] = current_time
                self.hv_graph_data[slot][ptr, 1 + ch * 2] = values['VMon']
                self.hv_graph_data[slot][ptr, 2 + ch * 2] = values['IMon']
        for slot in self.hv_graph_data.keys():
            self.pointers['hv_graph'][slot] = (self.pointers['hv_graph'].get(slot, 0) + 1) % self.max_lens['hv_graph']
            self.plot_dirty_flags[f"hv_slot_{slot}"] = True
    @pyqtSlot(str)
    def activate_sensor(self, name):
        ui_map = {'daq': (['daq_temp', 'daq_level'], ["L_LS_Temp","R_LS_Temp","GdLS_level","GCLS_level"]),'radon': (['radon'], ["Radon_Value", "Radon_Status"]),'magnetometer': (['mag'], ["B_x", "B_y", "B_z", "B"]),'th_o2': (['th_o2'], ["TH_O2_Temp","TH_O2_Humi","TH_O2_Oxygen"]),'arduino': (['arduino'], ["Temp1","Humi1","Temp2","Humi2","Dist"]), 'caen_hv': ([], [])}
        if name in ui_map:
            for key in ui_map[name][1]:
                if key in self.labels: self.labels[key].setVisible(True)
        self._start_worker(name)
    def _start_db_worker(self):
        if 'db' in self.threads or not self.db_pool: return
        
        thread=QThread()
        # === 변경점: DatabaseWorker에 db_config 추가 전달 ===
        worker=DatabaseWorker(self.db_pool, self.config['database'], self.db_queue)
        
        worker.moveToThread(thread)
        worker.status_update.connect(self.status_bar.showMessage)
        worker.error_occurred.connect(self.show_error)
        thread.started.connect(worker.run)
        thread.start()
        self.threads['db']=(thread,worker)
    def _start_worker(self, name):
        if name in self.threads: return
        worker_map = {'daq':(DaqWorker,True),'radon':(RadonWorker,False),'magnetometer':(MagnetometerWorker,True),'th_o2':(ThO2Worker,False),'arduino':(ArduinoWorker,False), 'caen_hv':(HVWorker, False)}
        if name not in worker_map: 
            if self.config.get(name, {}).get("enabled"): logging.warning(f"Worker for '{name}' is enabled but not defined.")
            return
        WClass, use_run = worker_map[name]; thread = QThread()
        if name == 'caen_hv':
            worker = WClass(self.config.get('caen_hv', {}))
            self.hv_control_command.connect(worker.execute_control_command)
            worker.control_command_status.connect(self._update_hv_control_status)
            if hasattr(worker, 'data_ready'): worker.data_ready.connect(self._update_hv_ui)
            if hasattr(worker, 'connection_status'): worker.connection_status.connect(self._update_hv_connection)
        else:
            worker = WClass(self.config.get(name, {}), self.db_queue)
            s_map = {'daq':'avg_data_ready','radon':'data_ready','magnetometer':'avg_data_ready','th_o2':'avg_data_ready','arduino':'avg_data_ready'}
            slot_map = {'daq':self.update_daq_ui,'radon':self.update_radon_ui,'magnetometer':self.update_mag_ui,'th_o2':self.update_th_o2_ui,'arduino':self.update_arduino_ui}
            if name in s_map and hasattr(worker, s_map[name]): getattr(worker, s_map[name]).connect(slot_map[name])
            if name in ['daq', 'magnetometer', 'th_o2', 'arduino'] and hasattr(worker, 'raw_data_ready'): worker.raw_data_ready.connect(self.update_raw_ui)
        worker.moveToThread(thread)
        if hasattr(worker, 'error_occurred'): worker.error_occurred.connect(self.show_error)
        if name == 'radon' and hasattr(worker, 'radon_status_update'): worker.radon_status_update.connect(self._update_radon_status)
        elif hasattr(worker, 'status_update'): worker.status_update.connect(self.status_bar.showMessage)
        thread.started.connect(worker.run if use_run else worker.start_worker)
        thread.start(); self.threads[name] = (thread, worker)
    @pyqtSlot(float, dict)
    def update_daq_ui(self, ts, data):
        ptr = self.pointers['daq']; rtd, dist = data.get('rtd', []), data.get('dist', [])
        self.rtd_data[ptr] = [ts, rtd[0] if len(rtd) > 0 else np.nan, rtd[1] if len(rtd) > 1 else np.nan]
        self.dist_data[ptr] = [ts, dist[0] if len(dist) > 0 else np.nan, dist[1] if len(dist) > 1 else np.nan]
        self.pointers['daq'] = (ptr + 1) % self.max_lens['daq']
        self.plot_dirty_flags.update({"daq_ls_temp_L_LS_Temp": True, "daq_ls_temp_R_LS_Temp": True,"daq_ls_level_GdLS Level": True, "daq_ls_level_GCLS Level": True})
    @pyqtSlot(float, float, float)
    def update_radon_ui(self, ts, mu, sigma):
        ptr = self.pointers['radon']; self.radon_data[ptr] = [ts, mu]
        self.pointers['radon'] = (ptr + 1) % self.max_lens['radon']
        self.plot_dirty_flags["radon_Radon (μ)"] = True
        self.latest_raw_values["Radon_Value"] = f"Value: {mu:.2f} ± {sigma:.2f}"
    @pyqtSlot(dict)
    def update_radon_data(self, data):
        ts = data['ts']; mu = data['mu']; sigma = data['sigma']
        ptr = self.pointers['radon']; self.radon_data[ptr] = [ts, mu]
        self.pointers['radon'] = (ptr + 1) % self.max_lens['radon']
        self.plot_dirty_flags["radon_Radon (μ)"] = True
        self.latest_raw_values["Radon_Value"] = f"Radon Value: {mu:.2f} Bq/m³"; self.latest_raw_values["Radon_Status"] = f"Status: Measured"
    @pyqtSlot(float, list)
    def update_mag_ui(self, ts, mag):
        ptr = self.pointers['mag']; self.mag_data[ptr] = [ts] + mag
        self.pointers['mag'] = (ptr + 1) % self.max_lens['mag']
        self.plot_dirty_flags.update({"mag_Bx": True, "mag_By": True, "mag_Bz": True, "mag_|B|": True})
    @pyqtSlot(float, float, float, float)
    def update_th_o2_ui(self, ts, temp, humi, o2):
        ptr = self.pointers['th_o2']; self.th_o2_data[ptr] = [ts, temp, humi, o2]
        self.pointers['th_o2'] = (ptr + 1) % self.max_lens['th_o2']
        self.plot_dirty_flags.update({"th_o2_temp_humi_Temp(°C)": True, "th_o2_temp_humi_Humi(%)": True, "th_o2_o2_Oxygen(%)": True})
    @pyqtSlot(float, dict)
    def update_arduino_ui(self, ts, data):
        ptr = self.pointers['arduino']
        self.arduino_data[ptr] = [ts, data.get('temp0', np.nan), data.get('humi0', np.nan), data.get('temp1', np.nan), data.get('humi1', np.nan), data.get('dist', np.nan)]
        self.pointers['arduino'] = (ptr + 1) % self.max_lens['arduino']
        self.plot_dirty_flags.update({"arduino_temp_humi_T1(°C)": True, "arduino_temp_humi_H1(%)": True,"arduino_temp_humi_T2(°C)": True, "arduino_temp_humi_H2(%)": True,"arduino_dist_Dist(cm)": True})
    @pyqtSlot(dict)
    def update_raw_ui(self, data):
        def set_label_style_and_text(key, text):
            if key in self.labels:
                if key in self.indicator_colors:
                    color = self.indicator_colors[key]
                    self.labels[key].setStyleSheet(f"color: {color}; font-weight: bold;")
                self.labels[key].setText(text)
        if 'rtd' in data or 'volt' in data:
            rtd, volt = data.get('rtd', []), data.get('volt', [])
            if len(rtd) > 0: set_label_style_and_text("L_LS_Temp", f"L LS Temp: {rtd[0]:.2f} °C")
            if len(rtd) > 1: set_label_style_and_text("R_LS_Temp", f"R LS Temp: {rtd[1]:.2f} °C")
            if len(volt) > 0: set_label_style_and_text("GdLS_level", f"GdLS level: {self._convert_daq_voltage_to_distance(volt[0], 0):.1f} mm")
            if len(volt) > 1: set_label_style_and_text("GCLS_level", f"GCLS level: {self._convert_daq_voltage_to_distance(volt[1], 1):.1f} mm")
        if 'mag' in data:
            mag = data.get('mag', []); keys = ["Bx", "By", "Bz", "|B|"]; labels_text = ["B_x", "B_y", "B_z", "B"]
            for i, key in enumerate(keys):
                if len(mag) > i: set_label_style_and_text(labels_text[i], f"{key}: {mag[i]:.2f} mG")
        if 'th_o2' in data:
            d = data['th_o2']
            if 'temp' in d: set_label_style_and_text("TH_O2_Temp", f"Temp: {d['temp']:.2f} °C")
            if 'humi' in d: set_label_style_and_text("TH_O2_Humi", f"Humi: {d['humi']:.2f} %")
            if 'o2' in d: set_label_style_and_text("TH_O2_Oxygen", f"Oxygen: {d['o2']:.2f} %")
        if 'arduino' in data:
            d = data['arduino']
            if 'temp0' in d and d['temp0'] is not None: set_label_style_and_text("Temp1", f"Temp1: {d['temp0']:.2f} °C")
            if 'humi0' in d and d['humi0'] is not None: set_label_style_and_text("Humi1", f"Humi1: {d['humi0']:.2f} %")
            if 'temp1' in d and d['temp1'] is not None: set_label_style_and_text("Temp2", f"Temp2: {d['temp1']:.2f} °C")
            if 'humi1' in d and d['humi1'] is not None: set_label_style_and_text("Humi2", f"Humi2: {d['humi1']:.2f} %")
            if 'dist' in d and d['dist'] is not None: set_label_style_and_text("Dist", f"Dist: {d['dist']:.1f} cm")
    @pyqtSlot()
    def _update_gui(self):
        dirty_keys = [key for key, dirty in self.plot_dirty_flags.items() if dirty]
        if not dirty_keys: return
        for key in dirty_keys:
            if key.startswith("hv_slot_"):
                slot = int(key.split('_')[-1])
                plot_data = self.hv_graph_data.get(slot); curves = self.hv_slot_curves.get(slot)
                if plot_data is not None and curves is not None:
                    num_channels = self.config['caen_hv']['crate_map'][str(slot)]['channels']
                    for ch in range(num_channels):
                        if ch < len(curves):
                            curves[ch]['v'].setData(x=plot_data[:, 0], y=plot_data[:, 1 + ch * 2], connect='finite')
                            curves[ch]['i'].setData(x=plot_data[:, 0], y=plot_data[:, 2 + ch * 2], connect='finite')
            elif key in self.curves and key in self.curve_data_map:
                x_data, y_data = self.curve_data_map[key]
                self.curves[key].setData(x=x_data, y=y_data, connect='finite')
        self.plot_dirty_flags.clear()
    def show_error(self, msg): logging.error(f"GUI Error: {msg}"); QTimer.singleShot(0, lambda: QMessageBox.critical(self, "Error", msg))
    def _init_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
        if os.path.exists(icon_path): self.tray_icon.setIcon(QIcon(icon_path))
        else: self.tray_icon.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        show_action = QAction("Show", self); quit_action = QAction("Exit", self)
        show_action.triggered.connect(self.showNormal); quit_action.triggered.connect(self.close)
        tray_menu = QMenu(); tray_menu.addAction(show_action); tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu); self.tray_icon.show()
    def closeEvent(self, event):
        logging.info("Application closing...")
        self.tray_icon.hide()
        active_threads = list(self.threads.keys())
        for name in active_threads:
            thread, worker = self.threads.get(name, (None, None))
            if worker:
                stop_method_name = 'stop' if hasattr(worker, 'stop') else 'stop_worker'
                if hasattr(worker, stop_method_name):
                    QMetaObject.invokeMethod(worker, stop_method_name, Qt.QueuedConnection)
        for name in active_threads:
            thread, worker = self.threads.get(name, (None, None))
            if thread and not thread.wait(4000):
                logging.warning(f"{name} worker thread did not finish cleanly.")
        if hasattr(self, 'hw_thread'):
            QMetaObject.invokeMethod(self.hw_manager, "stop_scan", Qt.QueuedConnection)
            self.hw_thread.quit()
            if not self.hw_thread.wait(3000): logging.warning("HardwareManager thread did not finish cleanly.")
        if self.db_pool:
            self.db_pool.close()
            logging.info("Database connection pool closed.")
        logging.info("All threads stopped. Exiting."); event.accept()

if __name__ == '__main__':
    load_config()
    log_level = CONFIG.get('logging_level', 'INFO').upper()
    log_filename = "rene_pm.log"
    file_handler = logging.FileHandler(log_filename, 'w'); stream_handler = logging.StreamHandler()
    logging.basicConfig(level=getattr(logging, log_level, logging.INFO), 
                        format='%(asctime)s - %(levelname)s - [%(threadName)s] - %(message)s', 
                        handlers=[file_handler, stream_handler])
    logging.info("="*50 + "\nRENE-PM Integrated Monitoring System Starting\n" + "="*50)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    signal.signal(signal.SIGINT, lambda s, f: QApplication.quit())
    timer = QTimer(); timer.start(500); timer.timeout.connect(lambda: None)
    main_win = MainWindow(config=CONFIG)
    log_gui_handler = LogHandler()
    log_gui_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    log_gui_handler.new_log_message.connect(main_win._update_log_viewer)
    logging.getLogger().addHandler(log_gui_handler)
    main_win.show()
    sys.exit(app.exec_())