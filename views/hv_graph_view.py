from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
import pyqtgraph as pg
import numpy as np

class HVGraphView(QWidget):
    """
    특정 HV 슬롯(보드)의 전압/전류 시계열 그래프를 보여주는 뷰
    """
    def __init__(self, slot_id, num_channels, data_manager, parent=None):
        super().__init__(parent)
        self.slot_id = slot_id
        self.num_channels = num_channels
        self.dm = data_manager
        self.curves_v = []
        self.curves_i = []
        
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        
        # Voltage Plot
        self.plot_v = self._create_plot(f"Slot {self.slot_id} - Voltage (V)", "Voltage (V)")
        # Current Plot
        self.plot_i = self._create_plot(f"Slot {self.slot_id} - Current (uA)", "Current (uA)")
        
        # 채널별 커브 생성
        for ch in range(self.num_channels):
            # 색상 계산 (간단히 HUE 순환)
            hue = int((ch / max(1, self.num_channels)) * 255)
            color = pg.intColor(hue, alpha=200)
            
            cv = self.plot_v.plot(pen=pg.mkPen(color, width=1.5), name=f"CH{ch}")
            ci = self.plot_i.plot(pen=pg.mkPen(color, width=1.5), name=f"CH{ch}")
            self.curves_v.append(cv)
            self.curves_i.append(ci)

        layout.addWidget(self.plot_v)
        layout.addWidget(self.plot_i)

    def _create_plot(self, title, y_label):
        p = pg.PlotWidget(title=title)
        p.setBackground('w')
        p.showGrid(x=True, y=True, alpha=0.3)
        p.setAxisItems({'bottom': pg.DateAxisItem(orientation='bottom')})
        p.getAxis('left').setLabel(y_label)
        
        # 성능 최적화: 다운샘플링 및 클리핑
        p.setClipToView(True)
        p.setDownsampling(mode='peak')
        
        if self.num_channels <= 12: # 채널이 적으면 범례 표시
            p.addLegend(offset=(10, 10))
        return p

    def update_ui(self):
        """DataManager의 버퍼에서 해당 슬롯의 데이터를 가져와 그래프 갱신"""
        # 메인 윈도우 타이머에 의해 호출됨
        self.dm.lock.lockForRead()
        try:
            # hv_graph_data[slot] 구조: [timestamp, V0, I0, V1, I1, ...]
            data = self.dm.hv_graph_data.get(self.slot_id)
            if data is None: return
            
            # 유효한 데이터만 필터링 (초기 0값이나 NaN 제외 로직은 DataManager가 처리)
            # 여기서는 전체 데이터를 가져와서 그림 (NaN이 있으면 끊겨서 그려짐)
            t = data[:, 0]
            
            # 데이터가 없는 경우(모두 nan) 패스
            if np.all(np.isnan(t)): return

            for ch in range(self.num_channels):
                if ch < len(self.curves_v):
                    # V idx: 1 + ch*2, I idx: 2 + ch*2
                    v_idx = 1 + ch * 2
                    i_idx = 2 + ch * 2
                    
                    # connect='finite' 옵션으로 NaN 구간 끊어서 그리기
                    self.curves_v[ch].setData(t, data[:, v_idx], connect='finite')
                    self.curves_i[ch].setData(t, data[:, i_idx], connect='finite')

        finally:
            self.dm.lock.unlock()