# views/panels/env_panel.py (전체 덮어쓰기)

import pyqtgraph as pg
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QGroupBox
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSlot
from core.event_bus import global_bus

class EnvPanel(QWidget):
    def __init__(self, state_store):
        super().__init__()
        self.state_store = state_store
        self.curves = {}
        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        container = QGroupBox("Environment & UPS Time-Series")
        container.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        grid_layout = QGridLayout(container)
        
        self._create_plot_group(grid_layout, 0, 0, "LS Temp (°C)", "°C", [("L_LS_Temp", "#1f77b4"), ("R_LS_Temp", "#ff7f0e")])
        self._create_plot_group(grid_layout, 0, 1, "TH/O2", "Value", [("Temp(°C)", "#1f77b4"), ("Humi(%)", "#ff7f0e"), ("Oxygen(%)", "#2ca02c")])
        self._create_plot_group(grid_layout, 0, 2, "Magnetometer", "mG", [("Bx", "#d62728"), ("By", "#2ca02c"), ("Bz", "#1f77b4"), ("|B|", "#000000")])
        self._create_plot_group(grid_layout, 1, 0, "LS Level (mm)", "mm", [("GdLS Level", "#1f77b4"), ("GCLS Level", "#ff7f0e")])
        self._create_plot_group(grid_layout, 1, 1, "Arduino", "Value", [("T1(°C)", "#1f77b4"), ("H1(%)", "#ff7f0e"), ("Dist(cm)", "#2ca02c")])
        self._create_plot_group(grid_layout, 1, 2, "Radon", "Bq/m³", [("Radon (μ)", "#1f77b4")])
        layout.addWidget(container)

    def _create_plot_group(self, grid, row, col, title, y_label, legends):
        plot = pg.PlotWidget()
        plot.setBackground('w')
        plot.setTitle(title)
        plot.showGrid(x=True, y=True, alpha=0.3)
        plot.setAxisItems({'bottom': pg.DateAxisItem(orientation='bottom')})
        plot.getAxis('left').setLabel(y_label)
        legend_item = plot.addLegend(offset=(10, 10))
        legend_item.setBrush(pg.mkBrush(255, 255, 255, 150))
        for name, color in legends:
            self.curves[name] = plot.plot(pen=pg.mkPen(color, width=2.5), name=name)
        grid.addWidget(plot, row, col)

    def _connect_signals(self):
        global_bus.ui_update_requested.connect(self._on_ui_update_requested)

    def showEvent(self, event):
        """[UX 개선] 사용자가 탭을 클릭하여 열 때 누적된 데이터를 즉시 화면에 렌더링"""
        super().showEvent(event)
        self._on_ui_update_requested()

    @pyqtSlot()
    def _on_ui_update_requested(self):
        # [핵심 최적화] 보이지 않는 탭의 그래프 렌더링을 완전히 생략 (프리징 방지)
        if not self.isVisible(): return
        
        flags = self.state_store.plot_dirty_flags
        
        if flags.get("daq_ls_temp_L_LS_Temp"):
            rtd = self.state_store.get_unrolled_data('rtd', 'daq')
            dist = self.state_store.get_unrolled_data('dist', 'daq')
            if rtd is not None:
                v_idx = ~np.isnan(rtd[:, 0])
                if len(rtd[v_idx]) > 0:
                    self.curves["L_LS_Temp"].setData(x=rtd[v_idx][:, 0], y=rtd[v_idx][:, 1], connect='finite')
                    self.curves["R_LS_Temp"].setData(x=rtd[v_idx][:, 0], y=rtd[v_idx][:, 2], connect='finite')
            if dist is not None:
                v_idx = ~np.isnan(dist[:, 0])
                if len(dist[v_idx]) > 0:
                    self.curves["GdLS Level"].setData(x=dist[v_idx][:, 0], y=dist[v_idx][:, 1], connect='finite')
                    self.curves["GCLS Level"].setData(x=dist[v_idx][:, 0], y=dist[v_idx][:, 2], connect='finite')
            flags["daq_ls_temp_L_LS_Temp"] = False
            flags["daq_ls_temp_R_LS_Temp"] = False
            flags["daq_ls_level_GdLS Level"] = False
            flags["daq_ls_level_GCLS Level"] = False
            
        if flags.get("th_o2_temp_humi_Temp(°C)"):
            th = self.state_store.get_unrolled_data('th_o2', 'th_o2')
            if th is not None:
                v_idx = ~np.isnan(th[:, 0])
                if len(th[v_idx]) > 0:
                    self.curves["Temp(°C)"].setData(x=th[v_idx][:, 0], y=th[v_idx][:, 1], connect='finite')
                    self.curves["Humi(%)"].setData(x=th[v_idx][:, 0], y=th[v_idx][:, 2], connect='finite')
                    self.curves["Oxygen(%)"].setData(x=th[v_idx][:, 0], y=th[v_idx][:, 3], connect='finite')
            flags["th_o2_temp_humi_Temp(°C)"] = False
            flags["th_o2_temp_humi_Humi(%)"] = False
            flags["th_o2_o2_Oxygen(%)"] = False
            
        if flags.get("mag_Bx"):
            mag = self.state_store.get_unrolled_data('mag', 'mag')
            if mag is not None:
                v_idx = ~np.isnan(mag[:, 0])
                if len(mag[v_idx]) > 0:
                    for i, k in enumerate(["Bx", "By", "Bz", "|B|"]):
                        self.curves[k].setData(x=mag[v_idx][:, 0], y=mag[v_idx][:, i+1], connect='finite')
            flags["mag_Bx"] = False
            flags["mag_By"] = False
            flags["mag_Bz"] = False
            flags["mag_|B|"] = False

        if flags.get("arduino_temp_humi_T1(°C)"):
            ard = self.state_store.get_unrolled_data('arduino', 'arduino')
            if ard is not None:
                v_idx = ~np.isnan(ard[:, 0])
                if len(ard[v_idx]) > 0:
                    self.curves["T1(°C)"].setData(x=ard[v_idx][:, 0], y=ard[v_idx][:, 1], connect='finite')
                    self.curves["H1(%)"].setData(x=ard[v_idx][:, 0], y=ard[v_idx][:, 2], connect='finite')
                    self.curves["Dist(cm)"].setData(x=ard[v_idx][:, 0], y=ard[v_idx][:, 9], connect='finite')
            flags["arduino_temp_humi_T1(°C)"] = False
            flags["arduino_temp_humi_H1(%)"] = False
            flags["arduino_temp_humi_T2(°C)"] = False
            flags["arduino_temp_humi_H2(%)"] = False
            flags["arduino_dist_Dist(cm)"] = False

        if flags.get("radon_Radon (μ)"):
            radon = self.state_store.get_unrolled_data('radon', 'radon')
            if radon is not None:
                v_idx = ~np.isnan(radon[:, 0])
                if len(radon[v_idx]) > 0:
                    self.curves["Radon (μ)"].setData(x=radon[v_idx][:, 0], y=radon[v_idx][:, 1], connect='finite')
            flags["radon_Radon (μ)"] = False