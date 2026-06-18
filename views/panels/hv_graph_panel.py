# views/panels/hv_graph_panel.py (전체 덮어쓰기)

import pyqtgraph as pg
import numpy as np
from PyQt6.QtWidgets import QWidget, QHBoxLayout
from PyQt6.QtCore import pyqtSlot
from core.event_bus import global_bus

class HVGraphPanel(QWidget):
    def __init__(self, slot, num_channels, state_store):
        super().__init__()
        self.slot = slot
        self.num_channels = num_channels
        self.state_store = state_store
        self.curves = []
        self._init_ui()
        global_bus.ui_update_requested.connect(self._on_update)

    def _init_ui(self):
        layout = QHBoxLayout(self)
        v_plot = pg.PlotWidget(title=f"Slot {self.slot} - Voltage (VMon)")
        i_plot = pg.PlotWidget(title=f"Slot {self.slot} - Current (IMon)")
        
        for p, y_label in [(v_plot, "Voltage (V)"), (i_plot, "Current (uA)")]:
            p.setBackground('w')
            if self.num_channels <= 16: 
                p.addLegend()
            p.showGrid(x=True, y=True, alpha=0.3)
            p.setAxisItems({'bottom': pg.DateAxisItem(orientation='bottom')})
            p.getAxis('left').setLabel(y_label)
            layout.addWidget(p)

        cmap = pg.colormap.get('viridis')
        colors = cmap.getLookupTable(nPts=self.num_channels)
        
        for ch in range(self.num_channels):
            c = colors[ch]
            # [핵심] 점 데이터도 렌더링되게 symbol 파라미터 삽입
            v_curve = v_plot.plot(pen=pg.mkPen(color=c, width=2), symbol='o', symbolSize=3, symbolBrush=c, name=f"CH{ch}")
            i_curve = i_plot.plot(pen=pg.mkPen(color=c, width=2), symbol='o', symbolSize=3, symbolBrush=c, name=f"CH{ch}")
            self.curves.append({'v': v_curve, 'i': i_curve})

    @pyqtSlot()
    def _on_update(self):
        flags = self.state_store.plot_dirty_flags
        if flags.get(f"hv_slot_{self.slot}"):
            unrolled = self.state_store.get_unrolled_hv_data(self.slot)
            if unrolled is not None and len(unrolled) > 0:
                v_idx = ~np.isnan(unrolled[:, 0])
                c_data = unrolled[v_idx]
                if len(c_data) > 0:
                    for ch in range(self.num_channels):
                        if ch < len(self.curves):
                            self.curves[ch]['v'].setData(x=c_data[:, 0], y=c_data[:, 1 + ch * 2], connect='finite')
                            self.curves[ch]['i'].setData(x=c_data[:, 0], y=c_data[:, 2 + ch * 2], connect='finite')
            flags[f"hv_slot_{self.slot}"] = False