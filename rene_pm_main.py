import sys, time, numpy as np, os, math, signal, json, logging, queue
from typing import Dict, Any

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QGridLayout, QHBoxLayout, QVBoxLayout,
                             QMessageBox, QLabel, QFrame, QStatusBar, QGroupBox, QTabWidget, QScrollArea,
                             QSystemTrayIcon, QStyle, QAction, qApp, QMenu, QTextEdit, QPushButton,
                             QDateEdit, QComboBox, QFormLayout, QSpinBox, QDoubleSpinBox, QGraphicsView,
                             QGraphicsScene, QGraphicsPixmapItem, QGraphicsTextItem, QGraphicsEllipseItem,
                             QGraphicsItemGroup, QGraphicsObject, QFileDialog, QCheckBox)
from PyQt5.QtCore import (QThread, QObject, pyqtSignal, pyqtSlot, Qt, QTimer, QMetaObject, QDate,
                          QPropertyAnimation, QEasingCurve, QSequentialAnimationGroup, QRectF)
from PyQt5.QtGui import (QFont, QColor, QPalette, QIcon, QPixmap, QTextCursor, QPainter, QBrush, QPen)

import pyqtgraph as pg
import mariadb
import pandas as pd
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import subprocess

from workers import (DatabaseWorker, DaqWorker, RadonWorker, MagnetometerWorker,
                     ThO2Worker, ArduinoWorker, HVWorker, AnalysisWorker, UPSWorker)
from workers.hardware_manager import HardwareManager
from ui_manager import UIManager, PlotManager

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
    def __init__(self, parent=None):
        super().__init__()
        QObject.__init__(self, parent)
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

class HighlightMarker(QGraphicsObject):
    def __init__(self, text=""):
        super().__init__()
        self._text = text
        self._font = QFont("Arial", 12, QFont.Bold)
        self._bounding_rect = QRectF(-30, -30, 60, 60)

    def boundingRect(self): return self._bounding_rect.adjusted(-15, -15, 15, 15)
    def paint(self, painter, option, widget):
        painter.setPen(QPen(QColor("#27AE60"), 3)); painter.setBrush(QBrush(QColor(39, 174, 96, 100)))
        painter.drawEllipse(self._bounding_rect); painter.setPen(QColor("white")); painter.setFont(self._font)
        painter.drawText(self._bounding_rect, Qt.AlignCenter, self._text)

class MainWindow(QMainWindow):
    hv_control_command = pyqtSignal(dict)
    request_hv_setpoints = pyqtSignal(int, int)

    def __init__(self, config):
        super().__init__()
        self.config = config; self.db_queue = queue.Queue(); self.db_pool = None
        self.threads = {}; self.latest_raw_values = {}; self.plot_dirty_flags = {}
        self.indicator_colors = {}; self.hv_slot_curves = {}; self.hv_slot_groupboxes = {}
        self.pmt_map = self.config.get("pmt_position_map", {}); self.guide_marker = None
        self.last_analysis_df = None; self.hv_db_push_counter = 0; self.emergency_shutdown_triggered = False
        self.latest_board_temps = {}; self.latest_ups_status = {}
        self.latest_radon_mu = 0.0; self.latest_radon_sigma = 0.0
        self.latest_radon_state = "Initializing"; self.latest_radon_countdown = -1
        self.legend_to_label_map = {
            "L_LS_Temp": "L_LS_Temp", "R_LS_Temp": "R_LS_Temp", "GdLS Level": "GdLS_level", "GCLS Level": "GCLS_level",
            "Bx": "B_x", "By": "B_y", "Bz": "B_z", "|B|": "B", "Temp(°C)": "TH_O2_Temp", "Humi(%)": "TH_O2_Humi", "Oxygen(%)": "TH_O2_Oxygen",
            "T1(°C)": "Temp1", "H1(%)": "Humi1", "T2(°C)": "Temp2", "H2(%)": "Humi2", "Dist(cm)": "Dist", "Radon (μ)": "Radon_Value"
        }
        self.ui_manager = UIManager(self); self.plot_manager = PlotManager(self); self.curves = {}
        self._init_data(); self._init_ui(); self._init_curve_data_map(); self._init_timers_and_workers()

    def _init_data(self):
        days = self.config.get('gui', {}).get('max_data_points_days', 31)
        self.m1m_len = days * 24 * 60; self.m10m_len = days * 24 * 6
        self.rtd_data = np.full((self.m1m_len, 3), np.nan); self.dist_data = np.full((self.m1m_len, 3), np.nan)
        self.radon_data = np.full((self.m10m_len, 2), np.nan); self.mag_data = np.full((self.m1m_len, 5), np.nan)
        self.th_o2_data = np.full((self.m1m_len, 4), np.nan)
        self.arduino_data = np.full((self.m1m_len, 10), np.nan)
        self.ups_data = np.full((self.m1m_len, 4), np.nan)
        self.hv_graph_data = {}
        if self.config.get('caen_hv', {}).get("enabled"):
            for slot_str, board in self.config['caen_hv']['crate_map'].items():
                self.hv_graph_data[int(slot_str)] = np.full((self.m1m_len, 1 + board['channels'] * 2), np.nan)
        self.pointers = {'daq':0,'radon':0,'mag':0,'th_o2':0,'arduino':0, 'ups':0, 'hv_graph':{}}
        for slot_str in self.hv_graph_data.keys(): self.pointers['hv_graph'][slot_str] = 0
        self.max_lens = {'daq': self.m1m_len, 'radon': self.m10m_len, 'mag': self.m1m_len, 
                         'th_o2': self.m1m_len, 'arduino': self.m1m_len, 'ups': self.m1m_len, 
                         'hv_graph': self.m1m_len}

    def _init_ui(self):
        self.setWindowTitle("RENE-PM v2.0 - Integrated Environment & HV Monitoring"); self.setGeometry(50, 50, 1920, 1080)
        self.menu_bar = self.menuBar()
        file_menu = self.menu_bar.addMenu("File")
        restart_action = QAction("Restart Program to Reload Config", self); restart_action.triggered.connect(self._restart_application); file_menu.addAction(restart_action)
        exit_action = QAction("Exit", self); exit_action.triggered.connect(self.close); file_menu.addAction(exit_action)
        self.status_bar = QStatusBar(self); self.setStatusBar(self.status_bar)
        central_widget = QWidget(); self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        title_label = QLabel("RENE-PM Integrated Monitoring System"); title_label.setFont(QFont("Arial", 20, QFont.Bold)); title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        top_panel = QWidget(); top_layout = QHBoxLayout(top_panel)
        main_layout.addWidget(top_panel, 8)
        bottom_panel = self.ui_manager.create_indicator_panel(); main_layout.addWidget(bottom_panel, 2)
        graph_tab_panel = self._create_graph_tab_panel(); hv_grid_panel = self._create_hv_grid_panel()
        top_layout.addWidget(graph_tab_panel, 7); top_layout.addWidget(hv_grid_panel, 3)
        shifter_text = self.config.get("shifter_name", "Unknown Shifter")
        self.shifter_label = QLabel(f" Shifter: {shifter_text} "); self.clock_label = QLabel()
        self.status_bar.addPermanentWidget(self.shifter_label); self.status_bar.addPermanentWidget(self.clock_label)

    def _init_curve_data_map(self):
        self.curve_data_map = {
            "daq_ls_temp_L_LS_Temp": (self.rtd_data[:, 0], self.rtd_data[:, 1]), "daq_ls_temp_R_LS_Temp": (self.rtd_data[:, 0], self.rtd_data[:, 2]),
            "daq_ls_level_GdLS Level": (self.dist_data[:, 0], self.dist_data[:, 1]), "daq_ls_level_GCLS Level": (self.dist_data[:, 0], self.dist_data[:, 2]),
            "radon_Radon (μ)": (self.radon_data[:, 0], self.radon_data[:, 1]), "mag_Bx": (self.mag_data[:, 0], self.mag_data[:, 1]),
            "mag_By": (self.mag_data[:, 0], self.mag_data[:, 2]), "mag_Bz": (self.mag_data[:, 0], self.mag_data[:, 3]),
            "mag_|B|": (self.mag_data[:, 0], self.mag_data[:, 4]), "th_o2_temp_humi_Temp(°C)": (self.th_o2_data[:, 0], self.th_o2_data[:, 1]),
            "th_o2_temp_humi_Humi(%)": (self.th_o2_data[:, 0], self.th_o2_data[:, 2]), "th_o2_o2_Oxygen(%)": (self.th_o2_data[:, 0], self.th_o2_data[:, 3]),
            "arduino_temp_humi_T1(°C)": (self.arduino_data[:, 0], self.arduino_data[:, 1]), "arduino_temp_humi_H1(%)": (self.arduino_data[:, 0], self.arduino_data[:, 2]),
            "arduino_temp_humi_T2(°C)": (self.arduino_data[:, 0], self.arduino_data[:, 3]), "arduino_temp_humi_H2(%)": (self.arduino_data[:, 0], self.arduino_data[:, 4]),
            "arduino_temp_humi_T3(°C)": (self.arduino_data[:, 0], self.arduino_data[:, 5]), "arduino_temp_humi_H3(%)": (self.arduino_data[:, 0], self.arduino_data[:, 6]),
            "arduino_temp_humi_T4(°C)": (self.arduino_data[:, 0], self.arduino_data[:, 7]), "arduino_temp_humi_H4(%)": (self.arduino_data[:, 0], self.arduino_data[:, 8]),
            "arduino_dist_Dist(cm)": (self.arduino_data[:, 0], self.arduino_data[:, 9]),
            "ups_linev": (self.ups_data[:, 0], self.ups_data[:, 1]),
            "ups_bcharge": (self.ups_data[:, 0], self.ups_data[:, 2]),
            "ups_timeleft": (self.ups_data[:, 0], self.ups_data[:, 3]),
        }

    def _init_timers_and_workers(self):
        self.ui_update_timer = QTimer(self); self.ui_update_timer.timeout.connect(self._update_gui); self.ui_update_timer.start(500)
        self.clock_timer = QTimer(self); self.clock_timer.timeout.connect(self._update_clock); self.clock_timer.start(1000)
        self.latest_hv_values = {}
        self.hv_graph_sampler_timer = QTimer(self); self.hv_graph_sampler_timer.timeout.connect(self._sample_hv_for_graph); self.hv_graph_sampler_timer.start(60000)
        self._init_tray_icon()
        if self.config.get('database',{}).get('enabled'):
            self._init_db_pool(); self._start_db_worker()
        if self.config.get('caen_hv', {}).get("enabled"): self._start_worker('caen_hv')
        self.hw_thread = QThread(); self.hw_manager = HardwareManager(self.config)
        self.hw_manager.moveToThread(self.hw_thread); self.hw_manager.device_connected.connect(self.activate_sensor)
        self.hw_thread.started.connect(self.hw_manager.start_scan); self.hw_thread.start()

    def _init_db_pool(self):
        try:
            db_config = self.config['database']
            pool_config = { 'user': db_config['user'], 'password': db_config['password'],
                'pool_name': db_config.get('pool_name', 'rene_pm_default_pool'), 'pool_size': db_config.get('pool_size', 3) }
            if db_config.get('unix_socket'): pool_config['unix_socket'] = db_config['unix_socket']
            else: pool_config['host'] = db_config.get('host', '127.0.0.1'); pool_config['port'] = db_config.get('port', 3306)
            self.db_pool = mariadb.ConnectionPool(**pool_config)
            logging.info(f"Database connection pool created.")
        except mariadb.Error as e:
            self.show_error(f"Failed to create DB connection pool: {e}"); self.db_pool = None

    # --- UI 생성 함수들 (Create) ---
    def _create_graph_tab_panel(self):
        tab_widget = QTabWidget()
        if self.config.get('caen_hv', {}).get("enabled"):
            hv_control_panel = self._create_hv_control_panel(); tab_widget.addTab(hv_control_panel, "HV Control")
        env_panel = self._create_environment_panel(); tab_widget.addTab(env_panel, "Environment Graphs")
        if self.config.get('ups', {}).get("enabled"):
            ups_panel = self._create_ups_panel(); tab_widget.addTab(ups_panel, "UPS Status")
        analysis_panel = self._create_analysis_panel(); tab_widget.addTab(analysis_panel, "Analysis")
        if self.config.get('caen_hv', {}).get("enabled"):
            for slot_str, board in self.config['caen_hv']['crate_map'].items():
                slot_panel = self._create_hv_slot_graph_panel(int(slot_str), board['channels'])
                tab_widget.addTab(slot_panel, f"HV Slot {slot_str} Graphs")
        guide_panel = self._create_guide_panel(); tab_widget.addTab(guide_panel, "Guide")
        notes_panel = self._create_notes_panel(); tab_widget.addTab(notes_panel, "Notes")
        return tab_widget
    
    def _create_notes_panel(self):
        notes_group = QGroupBox("Notes")
        notes_layout = QVBoxLayout(notes_group)
        self.notes_edit = QTextEdit()
        notes_layout.addWidget(self.notes_edit)
        try:
            with open("notes.md", "r", encoding="utf-8") as f:
                self.notes_edit.setMarkdown(f.read())
        except FileNotFoundError:
            self.notes_edit.setText("Project root folder에 notes.md 파일을 생성하세요.")
        return notes_group

    def _create_environment_panel(self):
        container = QGroupBox("Environment Time-Series"); container.setFont(QFont("Arial", 12, QFont.Bold))
        plot_layout = QGridLayout(container); self.plot_manager.create_ui_elements(plot_layout)
        return container
    
    def _create_ups_panel(self):
        container = QGroupBox("UPS Time-Series"); container.setFont(QFont("Arial", 12, QFont.Bold))
        layout = QGridLayout(container)
        plot_widget = pg.PlotWidget()
        plot_widget.setBackground('w'); plot_widget.showGrid(x=True, y=True, alpha=0.3)
        plot_widget.setAxisItems({'bottom': pg.DateAxisItem(orientation='bottom')})
        plot_widget.setLabel('left', 'Value'); plot_widget.setLabel('right', 'Time Left (min)')
        legend = plot_widget.addLegend(offset=(10, 10)); legend.setBrush(pg.mkBrush(255, 255, 255, 150))
        self.curves["ups_linev"] = plot_widget.plot(pen=pg.mkPen('#1f77b4', width=2), name="Line Voltage (V)")
        self.curves["ups_bcharge"] = plot_widget.plot(pen=pg.mkPen('#2ca02c', width=2), name="Battery Charge (%)")
        p2 = pg.ViewBox(); plot_widget.scene().addItem(p2); plot_widget.getAxis('right').linkToView(p2)
        p2.setXLink(plot_widget)
        self.curves["ups_timeleft"] = pg.PlotCurveItem(pen=pg.mkPen('#ff7f0e', width=2, style=Qt.DashLine))
        legend.addItem(self.curves["ups_timeleft"], name="Time Left (min)")
        p2.addItem(self.curves["ups_timeleft"])
        def update_views():
            p2.setGeometry(plot_widget.getViewBox().sceneBoundingRect())
            p2.linkedViewChanged(plot_widget.getViewBox(), p2.XAxis)
        plot_widget.getViewBox().sigResized.connect(update_views)
        layout.addWidget(plot_widget)
        return container

    def _create_hv_control_panel(self):
        container = QWidget(); main_layout = QHBoxLayout(container)
        control_group = QGroupBox("HV Channel Control"); control_layout = QFormLayout(control_group)
        self.control_slot_combo = QComboBox(); self.control_slot_combo.addItems(self.config['caen_hv']['crate_map'].keys())
        channel_layout = QHBoxLayout()
        self.control_ch_start = QSpinBox(); self.control_ch_start.setRange(0, 99)
        self.control_ch_end = QSpinBox(); self.control_ch_end.setRange(0, 99)
        self.single_channel_checkbox = QCheckBox("Single")
        channel_layout.addWidget(QLabel("Start:")); channel_layout.addWidget(self.control_ch_start)
        channel_layout.addWidget(QLabel("End:")); channel_layout.addWidget(self.control_ch_end)
        channel_layout.addWidget(self.single_channel_checkbox)
        self.control_v0_spinbox = QDoubleSpinBox(); self.control_v0_spinbox.setRange(0, 3000); self.control_v0_spinbox.setSuffix(" V")
        self.control_i0_spinbox = QDoubleSpinBox(); self.control_i0_spinbox.setRange(0, 1000); self.control_i0_spinbox.setSuffix(" uA")
        apply_button = QPushButton("Apply Settings"); apply_button.setStyleSheet("background-color: #3498DB; color: white;")
        apply_button.clicked.connect(self._send_hv_param_command)
        power_on_button = QPushButton("Power ON"); power_on_button.setStyleSheet("background-color: #27AE60; color: white;")
        power_on_button.clicked.connect(lambda: self._send_hv_power_command(True))
        power_off_button = QPushButton("Power OFF"); power_off_button.setStyleSheet("background-color: #C0392B; color: white;")
        power_off_button.clicked.connect(lambda: self._send_hv_power_command(False))
        control_layout.addRow("Slot:", self.control_slot_combo); control_layout.addRow("Channels:", channel_layout)
        control_layout.addRow("Set Voltage (V0Set):", self.control_v0_spinbox)
        control_layout.addRow("Set Current (I0Set):", self.control_i0_spinbox); control_layout.addRow(apply_button)
        control_layout.addRow(power_on_button, power_off_button)
        self.single_channel_checkbox.stateChanged.connect(self._toggle_single_channel_mode)
        self.control_ch_start.valueChanged.connect(lambda val: self.control_ch_end.setValue(val) if self.single_channel_checkbox.isChecked() else None)
        self.control_slot_combo.currentIndexChanged.connect(self._request_hv_setpoints)
        self.control_ch_start.valueChanged.connect(self._request_hv_setpoints)
        log_group = QGroupBox("Control Status"); log_layout = QVBoxLayout(log_group)
        self.hv_control_log = QTextEdit(); self.hv_control_log.setReadOnly(True)
        log_layout.addWidget(self.hv_control_log)
        main_layout.addWidget(control_group, 1); main_layout.addWidget(log_group, 2)
        self.single_channel_checkbox.setChecked(True)
        return container
    
    def _create_analysis_panel(self):
        container = QWidget(); main_layout = QVBoxLayout(container)
        control_panel = QFrame(); control_panel.setFrameShape(QFrame.StyledPanel)
        control_layout = QHBoxLayout(control_panel); control_layout.setAlignment(Qt.AlignLeft)
        self.analysis_mode_combo = QComboBox(); self.analysis_mode_combo.addItems(["Time Series", "Correlation"])
        self.timeseries_widget = QWidget()
        ts_layout = QHBoxLayout(self.timeseries_widget); ts_layout.setContentsMargins(0,0,0,0)
        self.analysis_combo = QComboBox()
        self.analysis_map = {
            "LS Temperature (°C)": "SELECT `datetime`, `RTD_1`, `RTD_2` FROM LS_DATA", "LS Level (mm)": "SELECT `datetime`, `DIST_1`, `DIST_2` FROM LS_DATA",
            "Magnetometer (mG)": "SELECT `datetime`, `Bx`, `By`, `Bz`, `B_mag` FROM MAGNETOMETER_DATA", "Radon (Bq/m³)": "SELECT `datetime`, `mu` FROM RADON_DATA",
            "TH/O2 Sensor": "SELECT `datetime`, `temperature`, `humidity`, `oxygen` FROM TH_O2_DATA", "Arduino Sensor": "SELECT `datetime`, `analog_1`, `analog_2`, `analog_3`, `analog_4`, `analog_5` FROM ARDUINO_DATA",
            "UPS Status": "SELECT `datetime`, `linev`, `bcharge`, `timeleft` FROM UPS_DATA", "Voltage (VMon)": "HV_QUERY", "Current (IMon)": "HV_QUERY","Board Temperature (°C)": "HV_TEMP_QUERY"
        }
        self.analysis_combo.addItems(self.analysis_map.keys())
        self.hv_specific_controls = QWidget()
        hv_spec_layout = QHBoxLayout(self.hv_specific_controls); hv_spec_layout.setContentsMargins(0,0,0,0)
        self.hv_slot_combo = QComboBox()
        if self.config.get('caen_hv', {}).get("enabled"): self.hv_slot_combo.addItems(self.config['caen_hv']['crate_map'].keys())
        self.hv_ch_start = QSpinBox(); self.hv_ch_start.setRange(0, 99); self.hv_ch_end = QSpinBox(); self.hv_ch_end.setRange(0, 99)
        self.analysis_single_channel_checkbox = QCheckBox("Single")
        hv_spec_layout.addWidget(QLabel("Slot:")); hv_spec_layout.addWidget(self.hv_slot_combo)
        hv_spec_layout.addWidget(QLabel("Ch Start:")); hv_spec_layout.addWidget(self.hv_ch_start); hv_spec_layout.addWidget(QLabel("Ch End:")); hv_spec_layout.addWidget(self.hv_ch_end)
        hv_spec_layout.addWidget(self.analysis_single_channel_checkbox)
        self.analysis_single_channel_checkbox.setChecked(True); self.hv_specific_controls.hide()
        self.board_temp_controls = QWidget()
        board_temp_layout = QHBoxLayout(self.board_temp_controls)
        board_temp_layout.setContentsMargins(0,0,0,0)
        board_temp_layout.addWidget(QLabel("Slots:"))
        self.slot_checkboxes = {}
        if self.config.get('caen_hv', {}).get("enabled"):
            for slot_str in self.config['caen_hv']['crate_map'].keys():
                checkbox = QCheckBox(f"Slot {slot_str}")
                self.slot_checkboxes[int(slot_str)] = checkbox
                board_temp_layout.addWidget(checkbox)
        self.board_temp_controls.hide()
        self.analysis_start_date = QDateEdit(QDate.currentDate().addDays(-7))
        self.analysis_end_date = QDateEdit(QDate.currentDate())
        self.analysis_start_date.setCalendarPopup(True); self.analysis_end_date.setCalendarPopup(True)
        ts_layout.addWidget(QLabel("Data:")); ts_layout.addWidget(self.analysis_combo); ts_layout.addWidget(self.hv_specific_controls); ts_layout.addWidget(self.board_temp_controls)
        ts_layout.addWidget(QLabel("Start:")); ts_layout.addWidget(self.analysis_start_date); ts_layout.addWidget(QLabel("End:")); ts_layout.addWidget(self.analysis_end_date)
        self.correlation_widget = QWidget()
        corr_layout = QHBoxLayout(self.correlation_widget); corr_layout.setContentsMargins(0,0,0,0)
        self.corr_slot_combo = QComboBox()
        if self.config.get('caen_hv', {}).get("enabled"): self.corr_slot_combo.addItems(self.config['caen_hv']['crate_map'].keys())
        self.corr_param_combo = QComboBox(); self.corr_param_combo.addItems(["VMon", "IMon"])
        self.corr_target_label = QLabel("Target: Slot 1 VMon vs LS Temp")
        self.corr_ch_start = QSpinBox(); self.corr_ch_start.setRange(0, 99); self.corr_ch_end = QSpinBox(); self.corr_ch_end.setRange(0, 99)
        self.corr_single_channel_checkbox = QCheckBox("Single")
        self.corr_start_date_edit = QDateEdit(QDate.currentDate().addDays(-7)); self.corr_end_date_edit = QDateEdit(QDate.currentDate())
        self.corr_start_date_edit.setCalendarPopup(True); self.corr_end_date_edit.setCalendarPopup(True)
        corr_layout.addWidget(QLabel("Slot:")); corr_layout.addWidget(self.corr_slot_combo); corr_layout.addWidget(QLabel("Ch Start:")); corr_layout.addWidget(self.corr_ch_start)
        corr_layout.addWidget(QLabel("Ch End:")); corr_layout.addWidget(self.corr_ch_end); corr_layout.addWidget(self.corr_single_channel_checkbox)
        corr_layout.addWidget(QLabel("Param:")); corr_layout.addWidget(self.corr_param_combo); corr_layout.addWidget(self.corr_target_label)
        corr_layout.addWidget(QLabel("Start:")); corr_layout.addWidget(self.corr_start_date_edit); corr_layout.addWidget(QLabel("End:")); corr_layout.addWidget(self.corr_end_date_edit)
        self.correlation_widget.hide()
        self.plot_button = QPushButton("Plot Data"); self.export_button = QPushButton("Export to CSV")
        control_layout.addWidget(QLabel("Mode:")); control_layout.addWidget(self.analysis_mode_combo)
        control_layout.addWidget(self.timeseries_widget); control_layout.addWidget(self.correlation_widget)
        control_layout.addStretch(1); control_layout.addWidget(self.plot_button); control_layout.addWidget(self.export_button)
        self.analysis_mode_combo.currentTextChanged.connect(self._on_analysis_mode_changed)
        self.analysis_combo.currentTextChanged.connect(self._on_analysis_type_changed)
        self.analysis_single_channel_checkbox.stateChanged.connect(self._toggle_single_channel_mode_analysis)
        self.hv_ch_start.valueChanged.connect(lambda val: self.hv_ch_end.setValue(val) if self.analysis_single_channel_checkbox.isChecked() else None)
        self.corr_slot_combo.currentTextChanged.connect(self._update_correlation_display)
        self.corr_single_channel_checkbox.stateChanged.connect(self._toggle_single_channel_mode_correlation)
        self.corr_ch_start.valueChanged.connect(lambda val: self.corr_ch_end.setValue(val) if self.corr_single_channel_checkbox.isChecked() else None)
        self.corr_single_channel_checkbox.setChecked(True)
        self.plot_button.clicked.connect(self._run_analysis); self.export_button.clicked.connect(self._export_analysis_data)
        self.analysis_canvas = FigureCanvas(Figure(figsize=(15, 6)))
        main_layout.addWidget(control_panel); main_layout.addWidget(self.analysis_canvas)
        return container
        
    def _create_hv_grid_panel(self):
        self.hv_crate_groupbox = QGroupBox("CAEN High Voltage Status"); self.hv_crate_groupbox.setFont(QFont("Arial", 12, QFont.Bold))
        hv_main_layout = QVBoxLayout(self.hv_crate_groupbox)
        self.hv_channel_widgets = {}
        caen_config = self.config.get('caen_hv', {})
        if caen_config.get("enabled"):
            crate_map = caen_config.get('crate_map', {}); display_channels = caen_config.get('display_channels', {})
            for slot_str, board_info in crate_map.items():
                slot = int(slot_str)
                slot_group = QGroupBox(f"Slot {slot}: {board_info.get('description', '')}"); slot_group.setFont(QFont("Arial", 10))
                self.hv_slot_groupboxes[slot] = slot_group
                slot_layout = QGridLayout(slot_group); slot_layout.setAlignment(Qt.AlignLeft); hv_main_layout.addWidget(slot_group)
                channels_to_display = []
                display_config = display_channels.get(slot_str)
                if display_config == "all": channels_to_display = range(board_info['channels'])
                elif isinstance(display_config, list): channels_to_display = display_config
                num_cols = 6
                for i, ch in enumerate(channels_to_display):
                    widget = ChannelWidget(slot, ch); widget.setVisible(False)
                    self.hv_channel_widgets[(slot, ch)] = widget; slot_layout.addWidget(widget, i // num_cols, i % num_cols)
        return self.hv_crate_groupbox

    def _create_hv_slot_graph_panel(self, slot, num_channels):
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
    
    def _create_guide_panel(self):
        container = QWidget()
        main_layout = QVBoxLayout(container)
        control_panel = QFrame()
        control_layout = QHBoxLayout(control_panel)
        control_layout.setAlignment(Qt.AlignLeft)
        self.guide_slot_spin = QSpinBox(); self.guide_slot_spin.setRange(1, 16)
        self.guide_ch_spin = QSpinBox(); self.guide_ch_spin.setRange(0, 47)
        search_button = QPushButton("Find PMT")
        search_button.clicked.connect(self._find_pmt_on_map)
        clear_button = QPushButton("Clear Highlight")
        clear_button.clicked.connect(self._clear_pmt_highlight)
        control_layout.addWidget(QLabel("Slot:")); control_layout.addWidget(self.guide_slot_spin)
        control_layout.addWidget(QLabel("Channel:")); control_layout.addWidget(self.guide_ch_spin)
        control_layout.addWidget(search_button); control_layout.addWidget(clear_button)
        self.guide_scene = QGraphicsScene()
        self.guide_view = QGraphicsView(self.guide_scene)
        self.guide_view.setRenderHint(QPainter.Antialiasing)
        self.guide_view.setDragMode(QGraphicsView.ScrollHandDrag)
        guide_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guide.png")
        if os.path.exists(guide_path):
            pixmap = QPixmap(guide_path)
            self.guide_pixmap_item = QGraphicsPixmapItem(pixmap)
            self.guide_scene.addItem(self.guide_pixmap_item)
            self._draw_default_pmt_markers()
            QTimer.singleShot(100, self._fit_guide_view)
        else:
            self.guide_scene.addText("Guide image (guide.png) not found.", QFont("Arial", 16))
        main_layout.addWidget(control_panel)
        main_layout.addWidget(self.guide_view)
        return container
    
    def _draw_default_pmt_markers(self):
        for slot, channels in self.pmt_map.items():
            for channel, coords in channels.items():
                x, y = coords[0], coords[1]
                default_marker = QGraphicsEllipseItem(-12, -12, 24, 24)
                default_marker.setPen(QPen(QColor("#3498DB"), 2))
                default_marker.setBrush(QBrush(QColor(52, 152, 219, 80)))
                default_marker.setPos(x, y)
                text = QGraphicsTextItem(f"S{slot}C{channel}")
                text.setFont(QFont("Arial", 11, QFont.Bold))
                text.setDefaultTextColor(QColor("#3498DB"))
                text_rect = text.boundingRect()
                text.setPos(x - text_rect.width()/2, y + 12)
                self.guide_scene.addItem(default_marker)
                self.guide_scene.addItem(text)

    # --- 누락되었던 함수들 (Slots and Helpers) ---
    def _toggle_single_channel_mode(self, state):
        is_single_mode = (state == Qt.Checked)
        self.control_ch_end.setEnabled(not is_single_mode)
        if is_single_mode:
            self.control_ch_end.setValue(self.control_ch_start.value())
            
    def _on_analysis_mode_changed(self, mode):
        if mode == "Time Series":
            self.timeseries_widget.show()
            self.correlation_widget.hide()
        elif mode == "Correlation":
            self.timeseries_widget.hide()
            self.correlation_widget.show()

    def _update_correlation_display(self, slot_str):
        if not slot_str: return
        slot = int(slot_str)
        if slot == 1:
            target_temp = "LS Temp"
        else:
            target_temp = "TH/O2 Temp"
        param = self.corr_param_combo.currentText()
        self.corr_target_label.setText(f"Target: Slot {slot} {param} vs {target_temp}")

    def _update_radon_display(self):
        """저장된 라돈 데이터를 조합하여 4줄 형식으로 라벨에 표시합니다."""
        line1 = "<b>Radon Value:</b>"
        line2 = f"{self.latest_radon_mu:.2f} &plusmn; {self.latest_radon_sigma:.2f}"
        line3 = f"<b>Status:</b> {self.latest_radon_state}"
        
        # 카운트다운 값이 유효할 때만 네 번째 줄을 만듭니다.
        line4 = f"({self.latest_radon_countdown}s left)" if self.latest_radon_countdown >= 0 else ""

        combined_text = f"{line1}<br>{line2}<br>{line3}<br>{line4}"
        self.labels["Radon_Value"].setText(combined_text)
        
    def _toggle_single_channel_mode_analysis(self, state):
        is_single_mode = (state == Qt.Checked)
        self.hv_ch_end.setEnabled(not is_single_mode)
        if is_single_mode:
            self.hv_ch_end.setValue(self.hv_ch_start.value())

    def _toggle_single_channel_mode_correlation(self, state):
        is_single_mode = (state == Qt.Checked)
        self.corr_ch_end.setEnabled(not is_single_mode)
        if is_single_mode:
            self.corr_ch_end.setValue(self.corr_ch_start.value())

    def _trigger_emergency_hv_shutdown(self):
        logging.warning("UPS BATTERY LOW. Triggering emergency HV shutdown.")
        self.hv_control_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] WARNING: UPS BATTERY LOW. SHUTTING DOWN ALL HV CHANNELS.")
        for slot_str, board_info in self.config['caen_hv']['crate_map'].items():
            slot = int(slot_str)
            channels = list(range(board_info['channels']))
            command = {'type': 'set_power', 'slot': slot, 'channels': channels, 'value': False}
            self.hv_control_command.emit(command)

    def _update_system_status_indicator(self):
        status = self.latest_ups_status.get('STATUS', 'N/A')
        timeleft = self.latest_ups_status.get('TIMELEFT', 0.0)
        
        # === 변경점: HV Status 표시 방식 변경 및 온도별 색상 적용 ===
        if self.emergency_shutdown_triggered:
            hv_status_text = "HV Status:<br><b style='color:red;'>SHUTDOWN ACTIVE</b>"
        elif "BATT" in status:
            hv_status_text = f"HV Status: <b style='color:orange;'>ON BATTERY</b><br><span style='color:orange;'>({timeleft:.0f} min left)</span>"
        else:
            hv_status_text = "HV Status: <b style='color:green;'>NORMAL</b>"
        
        temp_parts = []
        for s, t in sorted(self.latest_board_temps.items()):
            if t != -1.0:
                if t >= 70.0: temp_color = "red"
                elif t > 50.0: temp_color = "orange"
                else: temp_color = "limegreen"
                temp_parts.append(f"S{s}: <b style='color:{temp_color};'>{t:.1f}°C</b>")
        
        temp_text = " | ".join(temp_parts)
        final_text = f"{hv_status_text}<br><br>Board Temps:<br><b>{temp_text}</b>"
        self.labels['HV_Shutdown_Status'].setText(final_text)

    def _restart_application(self):
        reply = QMessageBox.question(self, 'Confirm Restart',
            "Are you sure you want to restart the application? All unsaved data will be lost.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                subprocess.Popen([sys.executable] + sys.argv)
                logging.info("Successfully launched a new process for restart.")
            except Exception as e:
                logging.error(f"Failed to launch new process: {e}")
                self.show_error(f"Could not start new process: {e}")
                return
            qApp.exit(0)

    def _request_hv_setpoints(self):
        slot = int(self.control_slot_combo.currentText())
        channel = self.control_ch_start.value()
        self.request_hv_setpoints.emit(slot, channel)

    @pyqtSlot(dict)
    def _update_hv_control_setpoints(self, data):
        self.control_v0_spinbox.setValue(data.get('V0Set', 0))
        self.control_i0_spinbox.setValue(data.get('I0Set', 0))

    def _clear_pmt_highlight(self):
        if self.guide_marker and self.guide_marker in self.guide_scene.items():
            if hasattr(self, 'highlight_anim_group') and self.highlight_anim_group:
                self.highlight_anim_group.stop()
            self.guide_scene.removeItem(self.guide_marker)
            self.guide_marker = None

    def _find_pmt_on_map(self):
        self._clear_pmt_highlight()
        slot = str(self.guide_slot_spin.value())
        channel = str(self.guide_ch_spin.value())
        if slot in self.pmt_map and channel in self.pmt_map[slot]:
            coords = self.pmt_map[slot][channel]
            x, y = coords[0], coords[1]
            marker_text = f"S{slot}\nCH{channel}"
            self.guide_marker = HighlightMarker(marker_text)
            self.guide_marker.setPos(x, y)
            self.guide_marker.setZValue(10)
            anim1 = QPropertyAnimation(self.guide_marker, b"scale"); anim1.setDuration(700)
            anim1.setStartValue(1.0); anim1.setEndValue(1.4); anim1.setEasingCurve(QEasingCurve.InOutQuad)
            anim2 = QPropertyAnimation(self.guide_marker, b"scale"); anim2.setDuration(700)
            anim2.setStartValue(1.4); anim2.setEndValue(1.0); anim2.setEasingCurve(QEasingCurve.InOutQuad)
            self.highlight_anim_group = QSequentialAnimationGroup()
            self.highlight_anim_group.addAnimation(anim1); self.highlight_anim_group.addAnimation(anim2)
            self.highlight_anim_group.setLoopCount(-1)
            self.highlight_anim_group.start()
            self.guide_scene.addItem(self.guide_marker)
        else:
            self.show_error(f"Position for Slot {slot}, Channel {channel} not found in pmt_map.json.")
            
    def _fit_guide_view(self):
        if hasattr(self, 'guide_pixmap_item'):
            visible_rect = QRectF(50, 50, 1820, 980)
            self.guide_view.fitInView(visible_rect, Qt.KeepAspectRatio)

    def _convert_daq_voltage_to_distance(self, v, mapping_index):
        try:
            daq_config = self.config.get('daq', {}); volt_module = next((mod for mod in daq_config.get('modules', []) if mod['task_type'] == 'volt'), None)
            if volt_module:
                m = volt_module['mapping'][mapping_index]
                v_min, v_max = m['volt_range']; d_min, d_max = m['dist_range_mm']
                return d_min + ((v - v_min) / (v_max - v_min)) * (d_max - d_min)
        except (IndexError, KeyError, StopIteration, TypeError) as e:
            logging.warning(f"Failed to convert voltage to distance: {e}"); return 0.0

    def _set_indicator_label(self, key, text):
        if key in self.labels:
            if key in self.indicator_colors:
                color = self.indicator_colors[key]
                self.labels[key].setStyleSheet(f"color: {color}; font-weight: bold;")
            self.labels[key].setText(text)

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
        slot = int(self.control_slot_combo.currentText()); ch_start = self.control_ch_start.value(); ch_end = self.control_ch_end.value()
        reply = QMessageBox.question(self, 'Confirm Action',
            f"Are you sure you want to turn Power {'ON' if power_state else 'OFF'} for Slot {slot}, Channels {ch_start}-{ch_end}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            channels = list(range(ch_start, ch_end + 1))
            command = {'type': 'set_power', 'slot': slot, 'channels': channels, 'value': power_state}
            self.hv_control_command.emit(command)

    def _on_analysis_type_changed(self, text):
        if "Voltage (VMon)" in text or "Current (IMon)" in text:
            self.hv_specific_controls.show()
            self.board_temp_controls.hide()
        elif "Board Temperature" in text:
            self.hv_specific_controls.hide()
            self.board_temp_controls.show()
        else:
            self.hv_specific_controls.hide()
            self.board_temp_controls.hide()

    def _run_analysis(self):
        if not self.db_pool: self.show_error("DB pool not available."); return
        self.plot_button.setEnabled(False); self.plot_button.setText("Loading...")
        mode = self.analysis_mode_combo.currentText()
        queries, params = [], []
        if mode == "Time Series":
            analysis_type = self.analysis_combo.currentText()
            query = self.analysis_map[analysis_type]
            start_date = self.analysis_start_date.date().toString("yyyy-MM-dd 00:00:00")
            end_date = self.analysis_end_date.date().toString("yyyy-MM-dd 23:59:59")
            if query == "HV_QUERY":
                slot = self.hv_slot_combo.currentText()
                ch_start = self.hv_ch_start.value()
                ch_end = self.hv_ch_end.value()
                final_query = "SELECT `datetime`, `channel`, `vmon`, `imon` FROM HV_DATA WHERE `slot` = ? AND `channel` BETWEEN ? AND ? AND `datetime` BETWEEN ? AND ?"
                queries.append(final_query)
                params.append([int(slot), ch_start, ch_end, start_date, end_date])
            elif query == "HV_TEMP_QUERY":
                selected_slots = [slot for slot, checkbox in self.slot_checkboxes.items() if checkbox.isChecked()]
                if not selected_slots:
                    self.show_error("Please select at least one slot to plot.")
                    self.plot_button.setEnabled(True); self.plot_button.setText("Plot Data")
                    return

                # 선택된 슬롯 수만큼 placeholder('?')를 생성
                placeholders = ', '.join(['?'] * len(selected_slots))
                final_query = f"SELECT DISTINCT `datetime`, `slot`, `board_temp` FROM HV_DATA WHERE `slot` IN ({placeholders}) AND `datetime` BETWEEN ? AND ?"
                
                # 파라미터 리스트 생성 (슬롯 목록 + 날짜)
                query_params = selected_slots + [start_date, end_date]
                queries.append(final_query)
                params.append(query_params)
            else:
                final_query = f"{query} WHERE `datetime` BETWEEN ? AND ?"
                queries.append(final_query)
                params.append([start_date, end_date])
        elif mode == "Correlation":
            slot = int(self.corr_slot_combo.currentText())
            ch_start = self.corr_ch_start.value()
            ch_end = self.corr_ch_end.value()
            start_date = self.corr_start_date_edit.date().toString("yyyy-MM-dd 00:00:00")
            end_date = self.corr_end_date_edit.date().toString("yyyy-MM-dd 23:59:59")
            queries.append("SELECT `datetime`, `channel`, `vmon`, `imon` FROM HV_DATA WHERE `slot` = ? AND `channel` BETWEEN ? AND ? AND `datetime` BETWEEN ? AND ?")
            params.append([slot, ch_start, ch_end, start_date, end_date])
            if slot == 1:
                queries.append("SELECT `datetime`, (`RTD_1` + `RTD_2`) / 2 as temp FROM LS_DATA WHERE `datetime` BETWEEN ? AND ? AND `RTD_1` IS NOT NULL AND `RTD_2` IS NOT NULL")
            else:
                queries.append("SELECT `datetime`, `temperature` as temp FROM TH_O2_DATA WHERE `datetime` BETWEEN ? AND ? AND `temperature` IS NOT NULL")
            params.append([start_date, end_date])
        self.analysis_thread = AnalysisWorker(self.db_pool, self.config['database'], queries, params)
        self.analysis_thread.analysis_complete.connect(self._plot_analysis_data)
        self.analysis_thread.error_occurred.connect(self.show_error)
        self.analysis_thread.finished.connect(self._on_analysis_finished)
        self.analysis_thread.start()

    def _plot_analysis_data(self, dfs: list):
        if not dfs or any(df.empty for df in dfs):
            self.show_error("No data found for the selected period or parameters."); return
        self.last_analysis_df = dfs[0]
        self.analysis_canvas.figure.clear()
        mode = self.analysis_mode_combo.currentText()
        fig = self.analysis_canvas.figure
        if mode == "Time Series":
            analysis_type = self.analysis_combo.currentText()
            fig.suptitle(f"Time Series Analysis of {analysis_type}", fontsize=16)
            df = dfs[0]
            df['datetime'] = pd.to_datetime(df['datetime'])
            if "Voltage (VMon)" in analysis_type:
                ax = fig.add_subplot(111)
                ax.set_ylabel("Voltage (VMon)")
                df_pivot = df.pivot(index='datetime', columns='channel', values='vmon')
                df_pivot.plot(ax=ax, marker='.', linestyle='-', markersize=2)
                ax.legend(title='Channel'); ax.grid(True, linestyle=':', alpha=0.7)
            elif "Current (IMon)" in analysis_type:
                ax = fig.add_subplot(111)
                ax.set_ylabel("Current (IMon, uA)")
                df_pivot = df.pivot(index='datetime', columns='channel', values='imon')
                df_pivot.plot(ax=ax, marker='.', linestyle='-', markersize=2)
                ax.legend(title='Channel'); ax.grid(True, linestyle=':', alpha=0.7)
            elif "Board Temperature" in analysis_type:
                ax = fig.add_subplot(111)
                ax.set_ylabel("Temperature (°C)")
                df.set_index('datetime', inplace=True)
                for slot in df['slot'].unique():
                    slot_df = df[df['slot'] == slot]
                    ax.plot(slot_df.index, slot_df['board_temp'], marker='.', linestyle='-', markersize=2, label=f'Slot {slot}')
                ax.legend(); ax.grid(True)
            else:
                ax = fig.add_subplot(111)
                df.set_index('datetime', inplace=True)
                y_label = analysis_type[analysis_type.find("(")+1:analysis_type.find(")")] if "(" in analysis_type else ""
                ax.set_ylabel(y_label)
                for column in df.columns:
                    if column != 'status':
                        ax.plot(df.index, df[column], marker='o', linestyle='-', markersize=2, label=column)
                ax.legend(); ax.grid(True)
        elif mode == "Correlation":
            df_hv = dfs[0]; df_temp = dfs[1]
            if df_hv.empty or df_temp.empty: self.show_error("Not enough data for correlation."); return
            df_hv['datetime'] = pd.to_datetime(df_hv['datetime'])
            df_temp['datetime'] = pd.to_datetime(df_temp['datetime'])
            merged_df = pd.merge_asof(df_hv.sort_values('datetime'), df_temp.sort_values('datetime'), on='datetime', direction='nearest', tolerance=pd.Timedelta('10min'))
            merged_df.dropna(inplace=True)
            self.last_analysis_df = merged_df
            param = self.corr_param_combo.currentText().lower()
            slot = self.corr_slot_combo.currentText()
            temp_name = "LS Temp" if int(slot) == 1 else "TH/O2 Temp"
            fig.suptitle(f"Correlation of Slot {slot} {param.upper()} vs {temp_name}", fontsize=16)
            ax = fig.add_subplot(111)
            for channel in merged_df['channel'].unique():
                channel_df = merged_df[merged_df['channel'] == channel]
                ax.scatter(channel_df['temp'], channel_df[param], alpha=0.5, label=f'Ch {channel}')
            ax.set_xlabel(f"{temp_name} (°C)"); ax.set_ylabel(f"{param.upper()} ({'V' if 'v' in param else 'uA'})")
            ax.grid(True); ax.legend(title='Channel')
            if len(merged_df) > 1:
                m, b = np.polyfit(merged_df['temp'], merged_df[param], 1)
                ax.plot(merged_df['temp'], m * merged_df['temp'] + b, color='red', linewidth=2, linestyle='--', label='Overall Trend')
                corr = merged_df['temp'].corr(merged_df[param])
                ax.text(0.05, 0.95, f'Overall Trend:\ny = {m:.3f}x + {b:.2f}\nr = {corr:.3f}', transform=ax.transAxes, fontsize=10, verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        fig.autofmt_xdate(); fig.tight_layout(rect=[0, 0.03, 1, 0.95]); self.analysis_canvas.draw()

    def _export_analysis_data(self):
        if self.last_analysis_df is None or self.last_analysis_df.empty:
            self.show_error("No data to export. Please plot data first.")
            return
        default_filename = f"RENE_PM_export_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV File", default_filename, "CSV Files (*.csv)")
        if path:
            try:
                self.last_analysis_df.to_csv(path, index=False)
                QMessageBox.information(self, "Success", f"Data successfully exported to:\n{path}")
            except Exception as e:
                self.show_error(f"Failed to export data: {e}")

    def _on_analysis_finished(self):
        self.plot_button.setEnabled(True); self.plot_button.setText("Plot Data")

    @pyqtSlot(str)
    def _update_log_viewer(self, message):
        max_lines = self.config.get('gui', {}).get('max_log_lines', 2000)
        if self.log_viewer_text.document().blockCount() > max_lines:
            cursor = self.log_viewer_text.textCursor()
            cursor.movePosition(QTextCursor.Start); cursor.select(QTextCursor.BlockUnderCursor)
            cursor.removeSelectedText(); cursor.deleteChar()
        self.log_viewer_text.append(message.strip())

    @pyqtSlot()
    def _update_clock(self): now = time.strftime('%Y-%m-%d %H:%M:%S'); self.clock_label.setText(f" {now} ")
    
    @pyqtSlot(str, int)
    def _update_radon_status(self, state, countdown):
        # 최신 상태를 클래스 변수에 저장하고 디스플레이 업데이트 함수 호출
        self.latest_radon_state = state
        self.latest_radon_countdown = countdown
        self._update_radon_display()
    
    @pyqtSlot(bool)
    def _update_hv_connection(self, is_connected):
        status = "Connected" if is_connected else "Disconnected"
        logging.info(f"HV Connection Status Changed: {status}")

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
        ui_map = {
            'daq': ([], ["L_LS_Temp","R_LS_Temp","GdLS_level","GCLS_level"]),
            'radon': ([], ["Radon_Value", "Radon_Status"]),
            'magnetometer': ([], ["B_x", "B_y", "B_z", "B"]),
            'th_o2': ([], ["TH_O2_Temp","TH_O2_Humi","TH_O2_Oxygen"]),
            'arduino': ([], ["Temp1","Humi1","Temp2","Humi2","Dist","Temp3","Humi3","Temp4","Humi4"]), 
            'ups': ([], ["UPS_Status", "UPS_Charge", "UPS_TimeLeft", "UPS_LineV", "HV_Shutdown_Status"]), 
            'caen_hv': ([], [])
        }
        if name in ui_map:
            for key in ui_map[name][1]:
                if key in self.labels: self.labels[key].setVisible(True)
        self._start_worker(name)
    
    def _start_db_worker(self):
        if 'db' in self.threads or not self.db_pool: return
        thread=QThread(); worker=DatabaseWorker(self.db_pool, self.config['database'], self.db_queue)
        worker.moveToThread(thread)
        worker.status_update.connect(self.status_bar.showMessage)
        worker.error_occurred.connect(self.show_error)
        thread.started.connect(worker.run)
        thread.start()
        self.threads['db']=(thread,worker)

    def _start_worker(self, name):
        if name in self.threads: return
        worker_map = {
            'daq': (DaqWorker, True), 'radon': (RadonWorker, False), 'magnetometer': (MagnetometerWorker, True),
            'th_o2': (ThO2Worker, False), 'arduino': (ArduinoWorker, False), 
            'caen_hv': (HVWorker, False), 'ups': (UPSWorker, False)
        }
        if name not in worker_map:
            if self.config.get(name, {}).get("enabled"): logging.warning(f"Worker for '{name}' is enabled but not defined.")
            return
        WClass, use_run = worker_map[name]; thread = QThread()
        signal_slot_map = {
            'caen_hv': { 'data_ready': self._update_hv_ui, 'connection_status': self._update_hv_connection },
            'daq': { 'avg_data_ready': self.update_daq_ui, 'raw_data_ready': self.update_raw_ui },
            'radon': { 'data_ready': self.update_radon_ui, 'radon_status_update': self._update_radon_status },
            'magnetometer': { 'avg_data_ready': self.update_mag_ui, 'raw_data_ready': self.update_raw_ui },
            'th_o2': { 'avg_data_ready': self.update_th_o2_ui, 'raw_data_ready': self.update_raw_ui },
            'arduino': { 'avg_data_ready': self.update_arduino_ui, 'raw_data_ready': self.update_raw_ui },
            'ups': { 'data_ready': self.update_ups_ui }
        }
        if name == 'caen_hv':
            worker = WClass(self.config.get(name, {}))
            self.hv_control_command.connect(worker.execute_control_command)
            worker.control_command_status.connect(self._update_hv_control_status)
            self.request_hv_setpoints.connect(worker.fetch_setpoints)
            worker.setpoints_ready.connect(self._update_hv_control_setpoints)
        else:
            worker = WClass(self.config.get(name, {}), self.db_queue)
        if hasattr(worker, 'error_occurred'): worker.error_occurred.connect(self.show_error)
        if name in signal_slot_map:
            for signal_name, slot_method in signal_slot_map[name].items():
                if hasattr(worker, signal_name): getattr(worker, signal_name).connect(slot_method)
        worker.moveToThread(thread)
        thread.started.connect(worker.run if use_run else worker.start_worker)
        thread.start()
        self.threads[name] = (thread, worker)
        logging.info(f"Worker for '{name}' started.")

    @pyqtSlot(float, dict)
    def update_daq_ui(self, ts, data):
        ptr = self.pointers['daq']; rtd, dist = data.get('rtd', []), data.get('dist', [])
        self.rtd_data[ptr] = [ts, rtd[0] if rtd else np.nan, rtd[1] if len(rtd) > 1 else np.nan]
        self.dist_data[ptr] = [ts, dist[0] if dist else np.nan, dist[1] if len(dist) > 1 else np.nan]
        self.pointers['daq'] = (ptr + 1) % self.max_lens['daq']
        self.plot_dirty_flags.update({"daq_ls_temp_L_LS_Temp": True, "daq_ls_temp_R_LS_Temp": True,"daq_ls_level_GdLS Level": True, "daq_ls_level_GCLS Level": True})

    @pyqtSlot(float, float, float)
    def update_radon_ui(self, ts, mu, sigma):
        # 그래프 데이터 업데이트 로직은 그대로 유지
        ptr = self.pointers['radon']; self.radon_data[ptr] = [ts, mu]
        self.pointers['radon'] = (ptr + 1) % self.max_lens['radon']
        self.plot_dirty_flags["radon_Radon (μ)"] = True
        
        # 최신 값을 클래스 변수에 저장하고 디스플레이 업데이트 함수 호출
        self.latest_radon_mu = mu
        self.latest_radon_sigma = sigma
        self._update_radon_display()

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
        self.arduino_data[ptr] = [ts, data.get('temp0', np.nan), data.get('humi0', np.nan), 
                                  data.get('temp1', np.nan), data.get('humi1', np.nan), 
                                  np.nan, np.nan, np.nan, np.nan, # T3, H3, T4, H4 자리는 비워둠
                                  data.get('dist', np.nan)]
        self.pointers['arduino'] = (ptr + 1) % self.max_lens['arduino']
        self.plot_dirty_flags.update({
            "arduino_temp_humi_T1(°C)": True, "arduino_temp_humi_H1(%)": True,
            "arduino_temp_humi_T2(°C)": True, "arduino_temp_humi_H2(%)": True,
            "arduino_dist_Dist(cm)": True
        })
        
    @pyqtSlot(dict)
    def update_ups_ui(self, data):
        self.latest_ups_status = data
        status = data.get('STATUS', 'N/A'); charge = data.get('BCHARGE', 0.0); timeleft = data.get('TIMELEFT', 0.0); linev = data.get('LINEV', 0.0)
        status_color = "green" if "ONLINE" in status else "orange" if "BATT" in status else "red"
        charge_color = "#2ca02c"; timeleft_color = "#ff7f0e"; linev_color = "#1f77b4"
        
        # === 변경점: Status 라벨에 줄 바꿈 적용 ===
        self.labels['UPS_Status'].setText(f"Status:<br><b style='color:{status_color};'>{status}</b>")
        self.labels['UPS_Charge'].setText(f"Charge: <b style='color:{charge_color};'>{charge:.1f} %</b>")
        self.labels['UPS_TimeLeft'].setText(f"Time Left: <b style='color:{timeleft_color};'>{timeleft:.1f} min</b>")
        self.labels['UPS_LineV'].setText(f"Line V: <b style='color:{linev_color};'>{linev:.1f} V</b>")

        ts = time.time(); ptr = self.pointers['ups']
        self.ups_data[ptr] = [ts, linev, charge, timeleft]
        self.pointers['ups'] = (ptr + 1) % self.max_lens['ups']
        self.plot_dirty_flags.update({"ups_linev": True, "ups_bcharge": True, "ups_timeleft": True})
        
        shutdown_threshold_min = 15.0 
        if "BATT" in status and timeleft < shutdown_threshold_min and not self.emergency_shutdown_triggered:
            self.emergency_shutdown_triggered = True; self._trigger_emergency_hv_shutdown()
        elif "ONLINE" in status and self.emergency_shutdown_triggered:
            logging.info("AC power restored. Resetting emergency HV shutdown flag.")
            self.emergency_shutdown_triggered = False
        
        self._update_system_status_indicator()
    
    @pyqtSlot(dict)
    def update_raw_ui(self, data):
        if 'rtd' in data or 'volt' in data:
            rtd, volt = data.get('rtd', []), data.get('volt', [])
            if len(rtd) > 0: self._set_indicator_label("L_LS_Temp", f"L LS Temp: {rtd[0]:.2f} °C")
            if len(rtd) > 1: self._set_indicator_label("R_LS_Temp", f"R LS Temp: {rtd[1]:.2f} °C")
            if len(volt) > 0: self._set_indicator_label("GdLS_level", f"GdLS level: {self._convert_daq_voltage_to_distance(volt[0], 0):.1f} mm")
            if len(volt) > 1: self._set_indicator_label("GCLS_level", f"GCLS level: {self._convert_daq_voltage_to_distance(volt[1], 1):.1f} mm")
        if 'mag' in data:
            mag = data.get('mag', []); keys = ["Bx", "By", "Bz", "|B|"]; labels_text = ["B_x", "B_y", "B_z", "B"]
            for i, key in enumerate(keys):
                if len(mag) > i: self._set_indicator_label(labels_text[i], f"{key}: {mag[i]:.2f} mG")
        if 'th_o2' in data:
            d = data['th_o2']
            if 'temp' in d: self._set_indicator_label("TH_O2_Temp", f"Temp: {d['temp']:.2f} °C")
            if 'humi' in d: self._set_indicator_label("TH_O2_Humi", f"Humi: {d['humi']:.2f} %")
            if 'o2' in d: self._set_indicator_label("TH_O2_Oxygen", f"Oxygen: {d['o2']:.2f} %")
        if 'arduino' in data:
            d = data['arduino']          
            if 'temp0' in d and d['temp0'] is not None: self._set_indicator_label("Temp1", f"Temp1: {d['temp0']:.2f} °C")
            if 'humi0' in d and d['humi0'] is not None: self._set_indicator_label("Humi1", f"Humi1: {d['humi0']:.2f} %")
            if 'temp1' in d and d['temp1'] is not None: self._set_indicator_label("Temp2", f"Temp2: {d['temp1']:.2f} °C")
            if 'humi1' in d and d['humi1'] is not None: self._set_indicator_label("Humi2", f"Humi2: {d['humi1']:.2f} %")
            if 'dist' in d and d['dist'] is not None: self._set_indicator_label("Dist", f"Dist: {d['dist']:.1f} cm")
            

    @pyqtSlot(dict)
    def _update_hv_ui(self, data):
        self.hv_db_push_counter += 1; timestamp = time.strftime('%Y-%m-%d %H:%M:%S'); db_data_to_queue = []
        for slot, slot_data in data.get('slots', {}).items():
            board_temp = slot_data.get('board_temp')
            self.latest_board_temps[slot] = board_temp
            if board_temp is not None and board_temp != -1.0 and slot in self.hv_slot_groupboxes:
                original_desc = self.config['caen_hv']['crate_map'][str(slot)].get('description', '')
                self.hv_slot_groupboxes[slot].setTitle(f"Slot {slot}: {original_desc}  [{board_temp:.1f} °C]")
            for channel, params in slot_data.get('channels', {}).items():
                key = (slot, channel)
                if key in self.hv_channel_widgets:
                    widget = self.hv_channel_widgets[key]; power_status = params.get('Pw', False)
                    if widget.isVisible() != power_status: widget.setVisible(power_status)
                    if power_status: widget.update_status(params)
                self.latest_hv_values[key] = {'VMon': params.get('VMon', np.nan), 'IMon': params.get('IMon', np.nan)}
                if self.hv_db_push_counter >= 60:
                    db_data_to_queue.append({'type': 'HV', 'data': (timestamp, slot, channel, params.get('Pw'), params.get('VMon'), params.get('IMon'), params.get('V0Set'), params.get('I0Set'), params.get('Status'), board_temp)})
        if db_data_to_queue:
            for item in db_data_to_queue: self.db_queue.put(item)
        if self.hv_db_push_counter >= 60: self.hv_db_push_counter = 0
        self._update_system_status_indicator()

    # --- 누락되었던 함수들 (Slots and Helpers) ---
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
        
    def show_error(self, msg):
        if msg is not None:
            logging.error(f"GUI Error: {msg}")
            QTimer.singleShot(0, lambda: QMessageBox.critical(self, "Error", str(msg)))

    def _init_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
        if os.path.exists(icon_path): self.tray_icon.setIcon(QIcon(icon_path))
        else: self.tray_icon.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        show_action = QAction("Show", self); quit_action = QAction("Exit", self)
        show_action.triggered.connect(self.showNormal)
        quit_action.triggered.connect(qApp.quit)
        tray_menu = QMenu(); tray_menu.addAction(show_action); tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu); self.tray_icon.show()

    def closeEvent(self, event):
        logging.info("Application closing sequence initiated...")
        self.status_bar.showMessage("Shutting down all components, please wait...")
        self.setEnabled(False)
        self.tray_icon.hide()
        QApplication.processEvents()
        threads_to_stop = []
        if hasattr(self, 'hw_thread') and self.hw_thread.isRunning():
            threads_to_stop.append(("HardwareManager", self.hw_thread, self.hw_manager))
        for name, (thread, worker) in self.threads.items():
            if thread.isRunning():
                threads_to_stop.append((name, thread, worker))
        for name, thread, worker in threads_to_stop:
            stop_method_name = 'stop' if hasattr(worker, 'stop') else 'stop_worker'
            if hasattr(worker, stop_method_name):
                logging.info(f"Sending stop signal to '{name}' worker...")
                if name in ['daq', 'magnetometer']:
                    getattr(worker, stop_method_name)()
                else:
                    QMetaObject.invokeMethod(worker, stop_method_name, Qt.QueuedConnection)
        all_threads_stopped = True
        for name, thread, worker in threads_to_stop:
            logging.info(f"Waiting for '{name}' thread to terminate...")
            thread.quit()
            if not thread.wait(5000):
                logging.warning(f"Thread '{name}' did not terminate gracefully within 5 seconds.")
                all_threads_stopped = False
            else:
                logging.info(f"Thread '{name}' has stopped successfully.")
        if self.db_pool:
            logging.info("Closing database connection pool...")
            self.db_pool.close()
            logging.info("Database connection pool closed.")
        if all_threads_stopped:
            logging.info("All components shut down successfully.")
        else:
            logging.warning("Some components may not have shut down cleanly.")
        event.accept()
        logging.info("Terminating application event loop and exiting.")
        qApp.exit(0)

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
    
    timer = QTimer(app); timer.start(500); timer.timeout.connect(lambda: None)
    
    main_win = MainWindow(config=CONFIG)
    
    log_gui_handler = LogHandler(app)
    log_gui_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    log_gui_handler.new_log_message.connect(main_win._update_log_viewer)
    logging.getLogger().addHandler(log_gui_handler)
    
    main_win.show()
    
    sys.exit(app.exec_())