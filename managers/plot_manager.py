from PyQt5.QtWidgets import QGroupBox, QVBoxLayout
from PyQt5.QtGui import QFont
import pyqtgraph as pg
import numpy as np

class PlotManager:
    def __init__(self, main_win, data_manager):
        self.main_win = main_win
        self.dm = data_manager
        if not hasattr(self.main_win, 'curves'): self.main_win.curves = {}
        
        # [성능 최적화] 전역 설정
        pg.setConfigOptions(antialias=False) # 안티앨리어싱 끄기 (속도 향상)

    def create_plot_group(self, group_key, configs):
        container = QGroupBox(configs[0][1])
        container.setFont(QFont("Arial", 10, QFont.Bold))
        group_layout = QVBoxLayout(container)
        group_layout.setContentsMargins(2, 2, 2, 2)
        
        default_palette = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f']
        
        for key, title, y_lbl, legends, _ in configs:
            plot = pg.PlotWidget()
            plot.setBackground('w')
            plot.showGrid(x=True, y=True, alpha=0.3)
            plot.setAxisItems({'bottom': pg.DateAxisItem(orientation='bottom')})
            plot.getAxis('left').setLabel(y_lbl)
            
            # [성능 최적화] 다운샘플링 활성화
            plot.setClipToView(True)
            plot.setDownsampling(mode='peak') 
            
            legend = plot.addLegend(offset=(10, 10))
            legend.setBrush(pg.mkBrush(255, 255, 255, 150))
            
            for i, name in enumerate(legends):
                if name == "Bx": pen_color = "#d62728"
                elif name == "By": pen_color = "#2ca02c"
                elif name == "Bz": pen_color = "#1f77b4"
                elif name == "|B|": pen_color = "#000000"
                else: pen_color = default_palette[i % len(default_palette)]
                
                # [성능 최적화] skipFiniteCheck=True (NaN 처리는 DataManager에서 하므로)
                self.main_win.curves[f"{key}_{name}"] = plot.plot(
                    pen=pg.mkPen(pen_color, width=1.5), 
                    name=name,
                    autoDownsample=True,
                    clipToView=True
                )
            group_layout.addWidget(plot)
            
        self.main_win.plots[group_key] = container
        container.setVisible(True)
        return container

    def create_ui_elements(self, layout):
        """환경 그래프 탭의 모든 그래프 생성 및 레이아웃 배치"""
        
        # 1. DAQ Temperature
        self.main_win.plots['daq_temp'] = self.create_plot_group('daq_temp', [
            ('daq_ls_temp', "🌡️ LS Temp (°C)", "°C", ["L_LS_Temp", "R_LS_Temp"], [])
        ])
        
        # 2. DAQ Level
        self.main_win.plots['daq_level'] = self.create_plot_group('daq_level', [
            ('daq_ls_level', "💧 LS Level (mm)", "mm", ["GdLS Level", "GCLS Level"], [])
        ])
        
        # 3. TH/O2
        self.main_win.plots['th_o2'] = self.create_plot_group('th_o2', [
            ('th_o2_temp_humi', "☁️ TH/O2", "Value", ["Temp(°C)", "Humi(%)"], []),
            ('th_o2_o2', "O2", "%", ["Oxygen(%)"], [])
        ])
        
        # 4. Arduino
        self.main_win.plots['arduino'] = self.create_plot_group('arduino', [
            ('arduino_temp_humi', "📟 Arduino", "Value", ["T1(°C)", "H1(%)", "T2(°C)", "H2(%)"], []),
            ('arduino_dist', "Dist", "cm", ["Dist(cm)"], [])
        ])
        
        # 5. Radon
        self.main_win.plots['radon'] = self.create_plot_group('radon', [
            ('radon', "☢️ Radon", "Bq/m³", ["Radon (μ)"], [])
        ])
        
        # 6. Magnetometer
        self.main_win.plots['mag'] = self.create_plot_group('mag', [
            ('mag', "🧲 Magnetometer (mG)", "mG", ["Bx", "By", "Bz", "|B|"], [])
        ]) 
        
        # 그리드 배치 (2행 3열)
        layout.addWidget(self.main_win.plots['daq_temp'], 0, 0)
        layout.addWidget(self.main_win.plots['th_o2'], 0, 1)
        layout.addWidget(self.main_win.plots['mag'], 0, 2)
        
        layout.addWidget(self.main_win.plots['daq_level'], 1, 0)
        layout.addWidget(self.main_win.plots['arduino'], 1, 1)
        layout.addWidget(self.main_win.plots['radon'], 1, 2)

    def update_plots(self, dirty_flags):
        """
        변경된 데이터만 그래프에 반영합니다.
        DataManager의 Lock을 사용하여 스레드 안전성을 보장합니다.
        """
        self.dm.lock.lockForRead()
        try:
            curves = self.main_win.curves
            
            # 1. DAQ (RTD & Distance)
            if dirty_flags.get('daq'):
                # rtd_data: [time, temp1, temp2]
                t_rtd = self.dm.rtd_data[:, 0]
                curves['daq_ls_temp_L_LS_Temp'].setData(t_rtd, self.dm.rtd_data[:, 1], connect='finite')
                curves['daq_ls_temp_R_LS_Temp'].setData(t_rtd, self.dm.rtd_data[:, 2], connect='finite')
                
                # dist_data: [time, dist1, dist2]
                t_dist = self.dm.dist_data[:, 0]
                curves['daq_ls_level_GdLS Level'].setData(t_dist, self.dm.dist_data[:, 1], connect='finite')
                curves['daq_ls_level_GCLS Level'].setData(t_dist, self.dm.dist_data[:, 2], connect='finite')

            # 2. Magnetometer
            if dirty_flags.get('mag'):
                # mag_data: [time, Bx, By, Bz, B_mag]
                t = self.dm.mag_data[:, 0]
                curves['mag_Bx'].setData(t, self.dm.mag_data[:, 1], connect='finite')
                curves['mag_By'].setData(t, self.dm.mag_data[:, 2], connect='finite')
                curves['mag_Bz'].setData(t, self.dm.mag_data[:, 3], connect='finite')
                curves['mag_|B|'].setData(t, self.dm.mag_data[:, 4], connect='finite')

            # 3. Radon
            if dirty_flags.get('radon'):
                t = self.dm.radon_data[:, 0]
                curves['radon_Radon (μ)'].setData(t, self.dm.radon_data[:, 1], connect='finite')

            # 4. TH/O2
            if dirty_flags.get('th_o2'):
                # th_o2_data: [time, temp, humi, o2]
                t = self.dm.th_o2_data[:, 0]
                curves['th_o2_temp_humi_Temp(°C)'].setData(t, self.dm.th_o2_data[:, 1], connect='finite')
                curves['th_o2_temp_humi_Humi(%)'].setData(t, self.dm.th_o2_data[:, 2], connect='finite')
                curves['th_o2_o2_Oxygen(%)'].setData(t, self.dm.th_o2_data[:, 3], connect='finite')

            # 5. Arduino
            if dirty_flags.get('arduino'):
                # arduino_data: [time, T1, H1, T2, H2, T3, H3, T4, H4, Dist]
                t = self.dm.arduino_data[:, 0]
                curves['arduino_temp_humi_T1(°C)'].setData(t, self.dm.arduino_data[:, 1], connect='finite')
                curves['arduino_temp_humi_H1(%)'].setData(t, self.dm.arduino_data[:, 2], connect='finite')
                curves['arduino_temp_humi_T2(°C)'].setData(t, self.dm.arduino_data[:, 3], connect='finite')
                curves['arduino_temp_humi_H2(%)'].setData(t, self.dm.arduino_data[:, 4], connect='finite')
                curves['arduino_dist_Dist(cm)'].setData(t, self.dm.arduino_data[:, 9], connect='finite')

        finally:
            self.dm.lock.unlock()