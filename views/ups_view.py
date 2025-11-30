from PyQt5.QtWidgets import QWidget, QVBoxLayout, QGroupBox
import pyqtgraph as pg
import numpy as np 

class UPSView(QWidget):
    def __init__(self, config, data_manager, parent=None):
        super().__init__(parent)
        self.dm = data_manager
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        group = QGroupBox("UPS Battery & Line Voltage")
        gl = QVBoxLayout(group)
        
        self.plot = pg.PlotWidget()
        self.plot.setBackground('w')
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setAxisItems({'bottom': pg.DateAxisItem(orientation='bottom')})
        self.plot.addLegend()
        
        # 커브 생성
        self.curve_line = self.plot.plot(pen='b', name="Line Voltage (V)")
        self.curve_charge = self.plot.plot(pen='g', name="Battery (%)")
        
        gl.addWidget(self.plot)
        layout.addWidget(group)

    def update_ui(self):
        # DataManager의 데이터로 그래프 갱신
        self.dm.lock.lockForRead()
        try:
            # [timestamp, linev, charge, timeleft]
            data = self.dm.ups_data
            
            # 데이터가 아직 안 찼거나 초기 상태일 경우 처리
            if data is None or len(data) == 0:
                return

            # 유효한 데이터만 슬라이싱 (NaN 제외)
            # 전체가 NaN이면 에러가 날 수 있으므로 체크
            if np.all(np.isnan(data[:, 1])):
                return

            valid_idx = ~np.isnan(data[:,1])
            
            t = data[valid_idx, 0]
            v = data[valid_idx, 1]
            c = data[valid_idx, 2]
        finally:
            self.dm.lock.unlock()
            
        if len(t) > 0:
            self.curve_line.setData(t, v)
            self.curve_charge.setData(t, c)