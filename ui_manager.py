# ui_manager.py

from PyQt5.QtWidgets import (QGroupBox, QGridLayout, QLabel, QFrame, QVBoxLayout, QHBoxLayout,
                             QTextEdit, QWidget)
from PyQt5.QtGui import QFont
import pyqtgraph as pg

class UIManager:
    """UI 위젯 생성 및 레이아웃을 전담하는 클래스"""
    def __init__(self, main_win):
        self.main_win = main_win
        # MainWindow의 속성으로 plots와 labels를 초기화
        self.main_win.plots = {}
        self.main_win.labels = {}

    def create_indicator_panel(self):
        indicator_group_box = QGroupBox("Real-time Indicators")
        indicator_group_box.setFont(QFont("Arial", 12, QFont.Bold))
        panel_layout = QHBoxLayout(indicator_group_box)
        env_indicator_widget = QWidget()
        env_indicator_layout = QHBoxLayout(env_indicator_widget)
        env_indicator_layout.setAlignment(pg.QtCore.Qt.AlignLeft)
        env_groups = {
            "LS (NI-cDAQ)": ["L_LS_Temp", "R_LS_Temp", "GdLS_level", "GCLS_level"],
            "Magnetometer": ["B_x", "B_y", "B_z", "B"],
            "TH/O2 Sensor": ["TH_O2_Temp", "TH_O2_Humi", "TH_O2_Oxygen"],
            "Arduino": ["Temp1", "Humi1", "Temp2", "Humi2", "Dist"],
            "Radon": ["Radon_Value", "Radon_Status"]
        }
        for title, labels in env_groups.items():
            group_frame = QFrame()
            group_frame.setFrameShape(QFrame.StyledPanel)
            group_layout = QVBoxLayout(group_frame)
            g_lbl = QLabel(title)
            g_lbl.setFont(QFont("Arial", 15, QFont.Bold))
            group_layout.addWidget(g_lbl)
            for name in labels:
                lbl = QLabel(f"{name.replace('_', ' ')}: -")
                lbl.setFont(QFont("Arial", 13))
                self.main_win.labels[name] = lbl
                lbl.setVisible(False)
                group_layout.addWidget(lbl)
            group_layout.addStretch(1)
            env_indicator_layout.addWidget(group_frame)

        log_viewer_group = QGroupBox("Log Viewer")
        log_viewer_layout = QVBoxLayout(log_viewer_group)
        self.main_win.log_viewer_text = QTextEdit()
        self.main_win.log_viewer_text.setReadOnly(True)
        self.main_win.log_viewer_text.setFont(QFont("Consolas", 9))
        log_viewer_layout.addWidget(self.main_win.log_viewer_text)

        notes_group = QGroupBox("Notes")
        notes_layout = QVBoxLayout(notes_group)
        self.main_win.notes_edit = QTextEdit()
        self.main_win.notes_edit.setReadOnly(True)
        notes_layout.addWidget(self.main_win.notes_edit)
        try:
            with open("notes.md", "r", encoding="utf-8") as f:
                self.main_win.notes_edit.setMarkdown(f.read())
        except FileNotFoundError:
            self.main_win.notes_edit.setText("Project root folder에 notes.md 파일을 생성하세요.")

        panel_layout.addWidget(env_indicator_widget, 5)
        panel_layout.addWidget(log_viewer_group, 2)
        panel_layout.addWidget(notes_group, 3)
        return indicator_group_box

class PlotManager:
    """PyQtGraph 생성, 데이터 버퍼 및 업데이트 로직을 전담하는 클래스"""
    def __init__(self, main_win):
        self.main_win = main_win
        self.main_win.curves = {}

    def create_plot_group(self, group_key, configs):
        container = QGroupBox(configs[0][1])
        container.setFont(QFont("Arial", 10, QFont.Bold))
        group_layout = QVBoxLayout(container)
        group_layout.setContentsMargins(2, 2, 2, 2)
        color_palette = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
        color_index = 0
        for key, title, y_lbl, legends, _ in configs:
            plot = pg.PlotWidget()
            plot.setBackground('w')
            plot.showGrid(x=True, y=True, alpha=0.3)
            plot.setAxisItems({'bottom': pg.DateAxisItem(orientation='bottom')})
            plot.getAxis('left').setLabel(y_lbl)
            legend = plot.addLegend(offset=(10, 10))
            legend.setBrush(pg.mkBrush(255, 255, 255, 150))
            for i, name in enumerate(legends):
                pen_color = color_palette[color_index % len(color_palette)]
                self.main_win.curves[f"{key}_{name}"] = plot.plot(pen=pg.mkPen(pen_color, width=2.5), name=name)
                if name in self.main_win.legend_to_label_map:
                    label_key = self.main_win.legend_to_label_map[name]
                    self.main_win.indicator_colors[label_key] = pen_color
                color_index += 1
            group_layout.addWidget(plot)
        self.main_win.plots[group_key] = container
        container.setVisible(False)
        return container

    def create_ui_elements(self, layout: QGridLayout):
        self.main_win.plots['daq_temp'] = self.create_plot_group('daq_temp',[('daq_ls_temp',"LS Temperature (°C)","°C",["L_LS_Temp","R_LS_Temp"],[])])
        self.main_win.plots['daq_level'] = self.create_plot_group('daq_level',[('daq_ls_level',"LS Level (mm)","mm",["GdLS Level","GCLS Level"],[])])
        self.main_win.plots['th_o2'] = self.create_plot_group('th_o2',[('th_o2_temp_humi',"TH/O2 Sensor","Value",["Temp(°C)","Humi(%)"],[]), ('th_o2_o2',"O2 Concentration","%",["Oxygen(%)"],[])])
        self.main_win.plots['arduino'] = self.create_plot_group('arduino',[('arduino_temp_humi',"Arduino Sensor","Value",["T1(°C)","H1(%)","T2(°C)","H2(%)"],[]), ('arduino_dist',"Distance","cm",["Dist(cm)"],[])])
        self.main_win.plots['radon'] = self.create_plot_group('radon',[('radon',"Radon (Bq/m³)","Bq/m³",["Radon (μ)"],[])])
        self.main_win.plots['mag'] = self.create_plot_group('mag',[('mag',"Magnetometer (mG)","mG",["Bx","By","Bz","|B|"],[])])
        layout.addWidget(self.main_win.plots['daq_temp'], 0, 0); layout.addWidget(self.main_win.plots['th_o2'], 0, 1); layout.addWidget(self.main_win.plots['mag'], 0, 2)
        layout.addWidget(self.main_win.plots['daq_level'], 1, 0); layout.addWidget(self.main_win.plots['arduino'], 1, 1); layout.addWidget(self.main_win.plots['radon'], 1, 2)
        for plot_widget in self.main_win.plots.values():
            plot_widget.setVisible(True)