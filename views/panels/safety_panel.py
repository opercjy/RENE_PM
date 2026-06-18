# views/panels/safety_panel.py (전체 덮어쓰기)

import pyqtgraph as pg
import numpy as np
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                             QFormLayout, QLabel, QTextEdit)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSlot
from core.event_bus import global_bus

class SafetyPanel(QWidget):
    def __init__(self, state_store):
        super().__init__()
        self.state_store = state_store
        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        left_layout = QVBoxLayout()
        
        info_group = QGroupBox("📋 Detailed Sensor Readings")
        info_layout = QFormLayout(info_group)
        self.lbl_fire = QLabel("N/A")
        self.lbl_voc_conc = QLabel("0.000 ppm")
        self.lbl_voc_alarm = QLabel("Normal")
        
        font_val = QFont("Arial", 12, QFont.Weight.Bold)
        for lbl in [self.lbl_fire, self.lbl_voc_conc, self.lbl_voc_alarm]:
            lbl.setFont(font_val)
            
        info_layout.addRow("🔥 Flame Detector:", self.lbl_fire)
        info_layout.addRow("🧪 VOC Concentration:", self.lbl_voc_conc)
        info_layout.addRow("🔔 VOC Alarm Status:", self.lbl_voc_alarm)
        
        sop_group = QGroupBox("📖 Standard Operating Procedure (SOP)")
        sop_layout = QVBoxLayout(sop_group)
        self.sop_text_edit = QTextEdit()
        self.sop_text_edit.setReadOnly(True)
        self.sop_text_edit.setHtml("<h3>⏳ Initializing...</h3>")
        sop_layout.addWidget(self.sop_text_edit)

        left_layout.addWidget(info_group, 3)
        left_layout.addWidget(sop_group, 7)
        
        graph_group = QGroupBox("📈 Safety Trends Analysis")
        graph_layout = QVBoxLayout(graph_group)
        
        self.voc_plot = pg.PlotWidget(title="🧪 VOC Concentration (ppm)")
        self.voc_plot.setBackground('w')
        self.voc_plot.showGrid(x=True, y=True, alpha=0.3)
        self.curve_voc = self.voc_plot.plot(pen=pg.mkPen('b', width=2), name="VOC")
        
        self.flame_plot = pg.PlotWidget(title="🔥 Flame Sensor Level")
        self.flame_plot.setBackground('w')
        self.flame_plot.showGrid(x=True, y=True, alpha=0.3)
        self.curve_flame = self.flame_plot.plot(pen=pg.mkPen('r', width=2), name="Flame Level")
        
        graph_layout.addWidget(self.voc_plot)
        graph_layout.addWidget(self.flame_plot)

        layout.addLayout(left_layout, 4)
        layout.addWidget(graph_group, 6)

    def _connect_signals(self):
        global_bus.safety_status_changed.connect(self._on_safety_status_changed)
        global_bus.sensor_data_updated.connect(self._on_sensor_data_updated)
        global_bus.ui_update_requested.connect(self._on_ui_update_requested)

    @pyqtSlot(str, str)
    def _on_safety_status_changed(self, phase, html_msg):
        self.sop_text_edit.setHtml(html_msg)

    @pyqtSlot(str, dict)
    def _on_sensor_data_updated(self, sensor_type, payload):
        data = payload.get('data', {})
        if sensor_type == 'fire_status':
            msg = data.get('msg', 'Wait...')
            val = data.get('status_code', 0)
            self.lbl_fire.setText(f"{msg} (Lv: {val})")
        elif sensor_type == 'voc_status':
            self.lbl_voc_conc.setText(f"{data.get('conc', 0.0):.3f} ppm")
            self.lbl_voc_alarm.setText("ALARM" if data.get('alarm', 0) > 0 else "Normal")

    @pyqtSlot()
    def _on_ui_update_requested(self):
        flags = self.state_store.plot_dirty_flags
        
        if flags.get("voc_trend_VOC"):
            voc = self.state_store.get_unrolled_data('voc', 'voc')
            if voc is not None:
                v_idx = ~np.isnan(voc[:, 0])
                if len(voc[v_idx]) > 0:
                    self.curve_voc.setData(x=voc[v_idx][:, 0], y=voc[v_idx][:, 1], connect='finite')
            flags["voc_trend_VOC"] = False
            
        if flags.get("flame_trend_Flame Level"):
            flame = self.state_store.get_unrolled_data('flame', 'flame')
            if flame is not None:
                v_idx = ~np.isnan(flame[:, 0])
                if len(flame[v_idx]) > 0:
                    self.curve_flame.setData(x=flame[v_idx][:, 0], y=flame[v_idx][:, 1], connect='finite')
            flags["flame_trend_Flame Level"] = False
