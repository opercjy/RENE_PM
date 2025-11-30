from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QGridLayout, QLabel, QFrame, QScrollArea, QSizePolicy)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPalette, QFont

class ChannelWidget(QFrame):
    def __init__(self, slot, channel):
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel)
        self.setFixedSize(60, 45)
        self.setStyleSheet("background-color: #ecf0f1; border-radius: 4px;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0); layout.setSpacing(0)
        
        self.lbl_id = QLabel(f"{channel}"); self.lbl_id.setFont(QFont("Arial", 8))
        self.lbl_v = QLabel("-"); self.lbl_v.setFont(QFont("Arial", 9, QFont.Bold))
        self.lbl_i = QLabel("-"); self.lbl_i.setFont(QFont("Arial", 7))
        
        for l in [self.lbl_id, self.lbl_v, self.lbl_i]:
            l.setAlignment(Qt.AlignCenter); layout.addWidget(l)
            
        self._is_on = False

    def update_state(self, pw, v, i, vset):
        # 상태가 꺼져있으면 숨김 (공간 절약)
        if not pw:
            if self.isVisible(): 
                self.setVisible(False)
                self._is_on = False
            return

        # 켜져있으면 표시 및 값 갱신
        if not self.isVisible(): 
            self.setVisible(True)
            self._is_on = True

        diff = abs(v - vset) / vset * 100 if vset > 0 else 0
        if diff <= 5: col = "#2ECC71"; txt = "white"      # Green
        elif diff <= 10: col = "#F1C40F"; txt = "black"   # Yellow
        else: col = "#E74C3C"; txt = "white"              # Red
        
        self.setStyleSheet(f"background-color: {col}; border-radius: 4px; color: {txt};")
        self.lbl_v.setText(f"{int(v)}V")
        self.lbl_i.setText(f"{i:.1f}u")

class SlotGroup(QGroupBox):
    def __init__(self, slot_id, channel_count):
        super().__init__(f"Slot {slot_id}")
        self.slot_id = slot_id
        self.channel_widgets = []
        self.setFont(QFont("Arial", 10, QFont.Bold))
        self.setStyleSheet("QGroupBox { margin-top: 1.2em; font-weight: bold; border: 1px solid #bbb; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }")
        
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(2, 15, 2, 2); self.grid.setSpacing(4)
        
        cols = 4 # 우측 패널 폭에 맞춰 4열
        for i in range(channel_count):
            w = ChannelWidget(slot_id, i)
            self.channel_widgets.append(w)
            self.grid.addWidget(w, i // cols, i % cols)
            w.setVisible(False) # 기본 숨김

    def update_summary(self):
        # 활성 채널 수 확인
        active_count = sum(1 for w in self.channel_widgets if w._is_on)
        
        if active_count == 0:
            self.setTitle(f"Slot {self.slot_id} (OFF)")
            # 높이를 줄여서 한 줄처럼 보이게 함 (스타일 변경)
            self.setStyleSheet("QGroupBox { border: 1px solid #eee; background: #f9f9f9; color: #aaa; max-height: 30px; }")
        else:
            self.setTitle(f"Slot {self.slot_id} ({active_count} Active)")
            self.setStyleSheet("QGroupBox { border: 1px solid #999; background: white; color: black; }")

class HVGridView(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.slot_groups = {}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget(); self.main_layout = QVBoxLayout(container); self.main_layout.setAlignment(Qt.AlignTop)
        
        crate = self.config.get('caen_hv', {}).get('crate_map', {})
        for s_str in sorted(crate.keys(), key=int):
            slot = int(s_str)
            ch_cnt = crate[s_str].get('channels', 12)
            group = SlotGroup(slot, ch_cnt)
            self.slot_groups[slot] = group
            self.main_layout.addWidget(group)
            
        scroll.setWidget(container)
        layout.addWidget(QLabel("⚡ Active HV Channels", alignment=Qt.AlignCenter))
        layout.addWidget(scroll)

    def update_status(self, slot, channel, params):
        if slot in self.slot_groups:
            group = self.slot_groups[slot]
            if channel < len(group.channel_widgets):
                group.channel_widgets[channel].update_state(
                    params.get('Pw', False), params.get('VMon', 0), 
                    params.get('IMon', 0), params.get('V0Set', 0)
                )
    
    def refresh_structure(self):
        """주기적으로 호출되어 그룹 모양 갱신"""
        for group in self.slot_groups.values():
            group.update_summary()