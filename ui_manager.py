# ui_manager.py (v2.1.9)

from PyQt5.QtWidgets import (QGroupBox, QGridLayout, QLabel, QFrame, QVBoxLayout, QHBoxLayout,
                             QTextEdit, QWidget, QFormLayout)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt
import pyqtgraph as pg

class UIManager:
    """UI 위젯 생성 및 레이아웃을 전담하는 클래스"""
    def __init__(self, main_win):
        self.main_win = main_win
        if not hasattr(self.main_win, 'plots'): self.main_win.plots = {}
        if not hasattr(self.main_win, 'labels'): self.main_win.labels = {}
        if not hasattr(self.main_win, 'safety_widgets'): self.main_win.safety_widgets = {}

    def create_indicator_panel(self):
        """하단 통합 상태 패널"""
        indicator_group_box = QGroupBox("🖥️ System Status Dashboard")
        indicator_group_box.setFont(QFont("Arial", 11, QFont.Bold))
        indicator_group_box.setMaximumHeight(240) 
        
        main_layout = QHBoxLayout(indicator_group_box)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        # [Left] Safety Status (20%)
        safety_frame = QFrame()
        safety_frame.setFrameShape(QFrame.StyledPanel)
        safety_frame.setStyleSheet("background-color: #d4edda; border: 3px solid #28a745; border-radius: 10px;")
        
        safety_layout = QVBoxLayout(safety_frame)
        safety_layout.setAlignment(Qt.AlignCenter)
        
        self.main_win.safety_widgets['status_lbl'] = QLabel("✅ SYSTEM\nNORMAL")
        self.main_win.safety_widgets['status_lbl'].setAlignment(Qt.AlignCenter)
        self.main_win.safety_widgets['status_lbl'].setFont(QFont("Arial", 16, QFont.Bold))
        self.main_win.safety_widgets['status_lbl'].setStyleSheet("color: #155724; border: none; background: transparent;")
        
        self.main_win.safety_widgets['guide_lbl'] = QLabel("Monitoring\nActive")
        self.main_win.safety_widgets['guide_lbl'].setAlignment(Qt.AlignCenter)
        self.main_win.safety_widgets['guide_lbl'].setFont(QFont("Arial", 10))
        self.main_win.safety_widgets['guide_lbl'].setStyleSheet("border: none; background: transparent; color: #155724;")
        
        self.main_win.safety_widgets['frame'] = safety_frame

        safety_layout.addWidget(QLabel("🛡️ SAFETY"))
        safety_layout.addStretch(1)
        safety_layout.addWidget(self.main_win.safety_widgets['status_lbl'])
        safety_layout.addWidget(self.main_win.safety_widgets['guide_lbl'])
        safety_layout.addStretch(1)
        
        # [Right] Sensors Panel (80%)
        env_widget = QWidget()
        env_layout = QGridLayout(env_widget)
        env_layout.setContentsMargins(0, 0, 0, 0)
        env_layout.setSpacing(8)

        # [수정] UPS 그룹에서 HV_Power_State 제거
        env_groups = [
            ("🌡️ LS Temp", ["L_LS_Temp", "R_LS_Temp"]),
            ("💧 LS Level", ["GdLS_level", "GCLS_level"]),
            ("🧲 Magnetometer", ["B_x", "B_y", "B_z", "B"]),
            ("☁️ TH/O2", ["TH_O2_Temp", "TH_O2_Humi", "TH_O2_Oxygen"]),
            ("📟 Arduino", ["Temp1", "Humi1", "Temp2", "Humi2", "Dist"]),
            ("☢️ Radon", ["Radon_Value"]),
            ("🔥 Flame Det.", ["Fire_Status"]),
            ("🧪 VOC Det.", ["VOC_Conc"]),
            ("🔋 UPS System", ["UPS_Status", "UPS_Charge", "UPS_TimeLeft"]), # HV_Power_State 제거됨
            ("🎛️ HV System", ["HV_Board_Temps"]) 
        ]
        
        max_cols = 5
        row, col = 0, 0
        
        for title, labels in env_groups:
            group_frame = QFrame()
            group_frame.setFrameShape(QFrame.StyledPanel)
            group_frame.setStyleSheet("background-color: #f8f9fa; border-radius: 5px; border: 1px solid #e9ecef;")
            
            g_layout = QVBoxLayout(group_frame)
            g_layout.setSpacing(1)
            g_layout.setContentsMargins(4, 4, 4, 4)
            
            g_lbl = QLabel(title)
            g_lbl.setFont(QFont("Arial", 9, QFont.Bold))
            g_lbl.setAlignment(Qt.AlignCenter)
            g_layout.addWidget(g_lbl)
            
            line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken)
            g_layout.addWidget(line)

            for name in labels:
                display_name = name.replace("TH_O2_", "").replace("_", " ")
                if name == "B": display_name = "|B|"
                if name == "B_x": display_name = "Bx"
                if name == "B_y": display_name = "By"
                if name == "B_z": display_name = "Bz"
                if name == "Fire_Status": display_name = "State"
                if name == "VOC_Conc": display_name = "Level"
                if name == "HV_Board_Temps": display_name = "Temps"
                
                lbl = QLabel(f"{display_name}: Wait...")
                lbl.setAlignment(Qt.AlignCenter)
                self.main_win.labels[name] = lbl
                
                # 폰트 10pt 고정
                base_style = "font-size: 10pt;"
                if name == "B_x": lbl.setStyleSheet(base_style + "color: #d62728; font-weight: bold;")
                elif name == "B_y": lbl.setStyleSheet(base_style + "color: #2ca02c; font-weight: bold;")
                elif name == "B_z": lbl.setStyleSheet(base_style + "color: #1f77b4; font-weight: bold;")
                elif name == "B":   lbl.setStyleSheet(base_style + "color: #000000; font-weight: bold;")
                else: lbl.setStyleSheet(base_style)
                
                lbl.setVisible(True)
                g_layout.addWidget(lbl)
                
            g_layout.addStretch(1)
            env_layout.addWidget(group_frame, row, col)
            
            col += 1
            if col >= max_cols:
                col = 0
                row += 1

        main_layout.addWidget(safety_frame, 20)
        main_layout.addWidget(env_widget, 80)
        return indicator_group_box

    def create_log_tab(self):
        container = QWidget(); layout = QVBoxLayout(container)
        self.main_win.log_viewer_text = QTextEdit(); self.main_win.log_viewer_text.setReadOnly(True); self.main_win.log_viewer_text.setFont(QFont("Consolas", 10))
        layout.addWidget(QLabel("📜 System Event Log (Real-time)")); layout.addWidget(self.main_win.log_viewer_text)
        return container

    def create_advanced_safety_panel(self):
        """고급 안전 탭"""
        container = QWidget()
        layout = QHBoxLayout(container)
        
        # --- 좌측: 상세 상태 및 SOP 가이드 ---
        left_layout = QVBoxLayout()
        
        # 1. 상세 정보 (라돈 제거)
        info_group = QGroupBox("📋 Detailed Sensor Readings")
        info_layout = QFormLayout(info_group)
        self.main_win.labels['Fire_Status_Detail'] = QLabel("N/A")
        self.main_win.labels['VOC_Conc_Detail'] = QLabel("0.000 ppm")
        self.main_win.labels['VOC_Alarm_Detail'] = QLabel("Normal")
        
        font_val = QFont("Arial", 12, QFont.Bold)
        for key in ['Fire_Status_Detail', 'VOC_Conc_Detail', 'VOC_Alarm_Detail']:
            self.main_win.labels[key].setFont(font_val)
            
        info_layout.addRow("🔥 Flame Detector:", self.main_win.labels['Fire_Status_Detail'])
        info_layout.addRow("🧪 VOC Concentration:", self.main_win.labels['VOC_Conc_Detail'])
        info_layout.addRow("🔔 VOC Alarm Status:", self.main_win.labels['VOC_Alarm_Detail'])
        
        # 2. SOP Guide (영역 확장)
        sop_group = QGroupBox("📖 Standard Operating Procedure (SOP)")
        sop_layout = QVBoxLayout(sop_group)
        self.main_win.sop_text_edit = QTextEdit()
        self.main_win.sop_text_edit.setReadOnly(True)
        self.main_win.sop_text_edit.setHtml("<h3>⏳ Initializing...</h3>")
        sop_layout.addWidget(self.main_win.sop_text_edit)

        # [수정] 비율 조정: Info(3) : SOP(7) -> SOP 영역 확대
        left_layout.addWidget(info_group, 3)
        left_layout.addWidget(sop_group, 7)
        
        # --- 우측: 그래프 ---
        graph_group = QGroupBox("📈 Safety Trends Analysis")
        graph_layout = QVBoxLayout(graph_group)
        
        voc_plot = pg.PlotWidget(title="🧪 VOC Concentration (ppm)")
        voc_plot.setBackground('w')
        voc_plot.showGrid(x=True, y=True, alpha=0.3)
        voc_plot.setAxisItems({'bottom': pg.DateAxisItem(orientation='bottom')})
        self.main_win.curves['voc_trend'] = voc_plot.plot(pen=pg.mkPen('b', width=2), name="VOC")
        
        flame_plot = pg.PlotWidget(title="🔥 Flame Sensor Level (Analog)")
        flame_plot.setBackground('w')
        flame_plot.showGrid(x=True, y=True, alpha=0.3)
        flame_plot.setAxisItems({'bottom': pg.DateAxisItem(orientation='bottom')})
        self.main_win.curves['flame_trend'] = flame_plot.plot(pen=pg.mkPen('r', width=2), name="Flame Level")
        
        graph_layout.addWidget(voc_plot)
        graph_layout.addWidget(flame_plot)

        layout.addLayout(left_layout, 4)
        layout.addWidget(graph_group, 6)
        
        return container

class PlotManager:
    # (이전과 동일)
    def __init__(self, main_win):
        self.main_win = main_win
        if not hasattr(self.main_win, 'curves'): self.main_win.curves = {}
    def create_plot_group(self, group_key, configs):
        container = QGroupBox(configs[0][1]); container.setFont(QFont("Arial", 10, QFont.Bold))
        group_layout = QVBoxLayout(container); group_layout.setContentsMargins(2, 2, 2, 2)
        default_palette = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f']
        for key, title, y_lbl, legends, _ in configs:
            plot = pg.PlotWidget(); plot.setBackground('w'); plot.showGrid(x=True, y=True, alpha=0.3)
            plot.setAxisItems({'bottom': pg.DateAxisItem(orientation='bottom')}); plot.getAxis('left').setLabel(y_lbl)
            legend = plot.addLegend(offset=(10, 10)); legend.setBrush(pg.mkBrush(255, 255, 255, 150))
            for i, name in enumerate(legends):
                if name == "Bx": pen_color = "#d62728"
                elif name == "By": pen_color = "#2ca02c"
                elif name == "Bz": pen_color = "#1f77b4"
                elif name == "|B|": pen_color = "#000000"
                else: pen_color = default_palette[i % len(default_palette)]
                self.main_win.curves[f"{key}_{name}"] = plot.plot(pen=pg.mkPen(pen_color, width=2.5), name=name)
                if hasattr(self.main_win, 'legend_to_label_map') and name in self.main_win.legend_to_label_map:
                    label_key = self.main_win.legend_to_label_map[name]
                    if hasattr(self.main_win, 'indicator_colors'): self.main_win.indicator_colors[label_key] = pen_color
            group_layout.addWidget(plot)
        self.main_win.plots[group_key] = container; container.setVisible(False)
        return container
    def create_ui_elements(self, layout: QGridLayout):
        self.main_win.plots['daq_temp'] = self.create_plot_group('daq_temp',[('daq_ls_temp',"🌡️ LS Temp (°C)","°C",["L_LS_Temp","R_LS_Temp"],[])])
        self.main_win.plots['daq_level'] = self.create_plot_group('daq_level',[('daq_ls_level',"💧 LS Level (mm)","mm",["GdLS Level","GCLS Level"],[])])
        self.main_win.plots['th_o2'] = self.create_plot_group('th_o2',[('th_o2_temp_humi',"☁️ TH/O2","Value",["Temp(°C)","Humi(%)"],[]), ('th_o2_o2',"O2","%",["Oxygen(%)"],[])])
        self.main_win.plots['arduino'] = self.create_plot_group('arduino',[('arduino_temp_humi',"📟 Arduino","Value",["T1(°C)","H1(%)"],[]), ('arduino_dist',"Dist","cm",["Dist(cm)"],[])])
        self.main_win.plots['radon'] = self.create_plot_group('radon',[('radon',"☢️ Radon","Bq/m³",["Radon (μ)"],[])])
        self.main_win.plots['mag'] = self.create_plot_group('mag',[('mag',"🧲 Magnetometer (mG)","mG",["Bx", "By", "Bz", "|B|"],[])]) 
        layout.addWidget(self.main_win.plots['daq_temp'], 0, 0); layout.addWidget(self.main_win.plots['th_o2'], 0, 1); layout.addWidget(self.main_win.plots['mag'], 0, 2)
        layout.addWidget(self.main_win.plots['daq_level'], 1, 0); layout.addWidget(self.main_win.plots['arduino'], 1, 1); layout.addWidget(self.main_win.plots['radon'], 1, 2)
        for plot_widget in self.main_win.plots.values(): plot_widget.setVisible(True)