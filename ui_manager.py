# ui_manager.py

from PyQt5.QtWidgets import (QGroupBox, QGridLayout, QLabel, QFrame, QVBoxLayout, QHBoxLayout,
                             QTextEdit, QWidget)
from PyQt5.QtGui import QFont
import pyqtgraph as pg

class UIManager:
    """UI 위젯 생성 및 레이아웃을 전담하는 클래스"""
    def __init__(self, main_win):
        self.main_win = main_win
        # 메인 윈도우의 속성 초기화 (MainWindow에서 사용됨)
        if not hasattr(self.main_win, 'plots'):
            self.main_win.plots = {}
        if not hasattr(self.main_win, 'labels'):
            self.main_win.labels = {}

    def create_indicator_panel(self):
        indicator_group_box = QGroupBox("Real-time Indicators")
        indicator_group_box.setFont(QFont("Arial", 12, QFont.Bold))
        panel_layout = QHBoxLayout(indicator_group_box)
        
        env_indicator_widget = QWidget()
        env_indicator_layout = QHBoxLayout(env_indicator_widget)
        # PyQtGraph의 QtCore 래퍼를 사용하여 Alignment 설정 (v2.0 방식 유지)
        env_indicator_layout.setAlignment(pg.QtCore.Qt.AlignLeft)
        
        # === 변경점: 모든 그룹을 하나의 딕셔너리로 통합 (이전 방식으로 롤백) ===
        env_groups = {
            "LS (NI-cDAQ)": ["L_LS_Temp", "R_LS_Temp", "GdLS_level", "GCLS_level"],
            "Magnetometer": ["B_x", "B_y", "B_z", "B"],
            "TH/O2 Sensor": ["TH_O2_Temp", "TH_O2_Humi", "TH_O2_Oxygen"],
            "Arduino": ["Temp1", "Humi1", "Temp2", "Humi2", "Dist"],
            "Radon": ["Radon_Value"],
            "UPS": ["UPS_Status", "UPS_Charge", "UPS_TimeLeft", "UPS_LineV"],
            "System Status": ["HV_Shutdown_Status"]
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
                # 생성된 라벨을 메인 윈도우의 labels 딕셔너리에 저장
                self.main_win.labels[name] = lbl
                # 초기에는 비활성화 상태로 두고, HardwareManager가 활성화 신호를 보낼 때 켜짐
                lbl.setVisible(False)
                group_layout.addWidget(lbl)
            group_layout.addStretch(1)
            env_indicator_layout.addWidget(group_frame)

        log_viewer_group = QGroupBox("Log Viewer")
        log_viewer_layout = QVBoxLayout(log_viewer_group)
        # 로그 뷰어 텍스트 에디터 생성 및 메인 윈도우 속성으로 저장
        self.main_win.log_viewer_text = QTextEdit()
        self.main_win.log_viewer_text.setReadOnly(True)
        self.main_win.log_viewer_text.setFont(QFont("Consolas", 9))
        log_viewer_layout.addWidget(self.main_win.log_viewer_text)

        panel_layout.addWidget(env_indicator_widget, 7)
        panel_layout.addWidget(log_viewer_group, 3)
        
        return indicator_group_box

class PlotManager:
    """PyQtGraph 생성, 데이터 버퍼 및 업데이트 로직을 전담하는 클래스"""
    def __init__(self, main_win):
        self.main_win = main_win
        # 메인 윈도우의 curves 속성 초기화
        if not hasattr(self.main_win, 'curves'):
            self.main_win.curves = {}

    def create_plot_group(self, group_key, configs):
        # configs는 (key, title, y_lbl, legends, _) 형태의 튜플 리스트임
        container = QGroupBox(configs[0][1])
        container.setFont(QFont("Arial", 10, QFont.Bold))
        group_layout = QVBoxLayout(container)
        group_layout.setContentsMargins(2, 2, 2, 2)
        
        # 그래프 색상 팔레트 정의
        color_palette = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
        color_index = 0
        
        for key, title, y_lbl, legends, _ in configs:
            plot = pg.PlotWidget()
            plot.setBackground('w')
            plot.showGrid(x=True, y=True, alpha=0.3)
            # 시간 축 설정
            plot.setAxisItems({'bottom': pg.DateAxisItem(orientation='bottom')})
            plot.getAxis('left').setLabel(y_lbl)
            
            # 범례 설정
            legend = plot.addLegend(offset=(10, 10))
            legend.setBrush(pg.mkBrush(255, 255, 255, 150)) # 범례 배경 반투명 처리
            
            for i, name in enumerate(legends):
                pen_color = color_palette[color_index % len(color_palette)]
                # 커브 생성 및 메인 윈도우에 등록
                self.main_win.curves[f"{key}_{name}"] = plot.plot(pen=pg.mkPen(pen_color, width=2.5), name=name)
                
                # 인디케이터 라벨 색상 매핑 (MainWindow의 legend_to_label_map 활용)
                if hasattr(self.main_win, 'legend_to_label_map') and name in self.main_win.legend_to_label_map:
                    label_key = self.main_win.legend_to_label_map[name]
                    # MainWindow의 indicator_colors 딕셔너리에 색상 정보 저장
                    if hasattr(self.main_win, 'indicator_colors'):
                         self.main_win.indicator_colors[label_key] = pen_color
                
                color_index += 1
            group_layout.addWidget(plot)
            
        self.main_win.plots[group_key] = container
        # 초기에는 그래프를 숨김 상태로 설정 (필요시 활성화)
        container.setVisible(False)
        return container

    def create_ui_elements(self, layout: QGridLayout):
        # 환경 그래프 탭의 UI 요소 생성 및 배치
        self.main_win.plots['daq_temp'] = self.create_plot_group('daq_temp',[('daq_ls_temp',"LS Temperature (°C)","°C",["L_LS_Temp","R_LS_Temp"],[])])
        self.main_win.plots['daq_level'] = self.create_plot_group('daq_level',[('daq_ls_level',"LS Level (mm)","mm",["GdLS Level","GCLS Level"],[])])
        self.main_win.plots['th_o2'] = self.create_plot_group('th_o2',[('th_o2_temp_humi',"TH/O2 Sensor","Value",["Temp(°C)","Humi(%)"],[]), ('th_o2_o2',"O2 Concentration","%",["Oxygen(%)"],[])])
        self.main_win.plots['arduino'] = self.create_plot_group('arduino',[('arduino_temp_humi',"Arduino Sensor","Value",["T1(°C)","H1(%)","T2(°C)","H2(%)"],[]), ('arduino_dist',"Distance","cm",["Dist(cm)"],[])])
        self.main_win.plots['radon'] = self.create_plot_group('radon',[('radon',"Radon (Bq/m³)","Bq/m³",["Radon (μ)"],[])])
        self.main_win.plots['mag'] = self.create_plot_group('mag',[('mag',"Magnetometer (mG)","mG",["Bx","By","Bz","|B|"],[])])
        
        # 그리드 레이아웃에 배치 (2행 3열)
        layout.addWidget(self.main_win.plots['daq_temp'], 0, 0); layout.addWidget(self.main_win.plots['th_o2'], 0, 1); layout.addWidget(self.main_win.plots['mag'], 0, 2)
        layout.addWidget(self.main_win.plots['daq_level'], 1, 0); layout.addWidget(self.main_win.plots['arduino'], 1, 1); layout.addWidget(self.main_win.plots['radon'], 1, 2)
        
        # 모든 플롯 위젯 활성화
        for plot_widget in self.main_win.plots.values():
            plot_widget.setVisible(True)