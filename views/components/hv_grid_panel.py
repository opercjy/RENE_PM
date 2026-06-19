# views/components/hv_grid_panel.py (전체 덮어쓰기)

from PyQt6.QtWidgets import QGroupBox, QVBoxLayout, QGridLayout, QFrame, QLabel
from PyQt6.QtGui import QFont, QColor, QPalette
from PyQt6.QtCore import Qt, pyqtSlot
from core.event_bus import global_bus

class ChannelWidget(QFrame):
    def __init__(self, slot, channel):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setLineWidth(1)
        self.setMinimumSize(80, 50)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(1)
        
        self.name_label = QLabel(f"S{slot}CH{channel}")
        self.vmon_label = QLabel("--- V")
        self.imon_label = QLabel("--- uA")
        
        self.name_label.setStyleSheet("font-size: 9pt; font-weight: bold;")
        self.vmon_label.setStyleSheet("font-size: 9pt;")
        self.imon_label.setStyleSheet("font-size: 9pt;")
        
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vmon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.imon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(self.name_label)
        layout.addWidget(self.vmon_label)
        layout.addWidget(self.imon_label)
        self.setAutoFillBackground(True)
        
        # [핵심] 렌더링 병목 방지용 상태 캐시
        self._last_v_text = ""
        self._last_i_text = ""
        self._last_bg_color = None
        self._last_text_color = None

    def update_status(self, params):
        power = params.get('Pw', False)
        vmon = params.get('VMon', 0.0)
        imon = params.get('IMon', 0.0)
        v0set = params.get('V0Set', 0.0)
        
        if not power:
            color = QColor('#95A5A6')
            text_color = QColor('white')
            v_text = "Power Off"
            i_text = ""
        else:
            diff_percent = (abs(vmon - v0set) / v0set) * 100 if v0set > 0 else 0
            if diff_percent <= 5: 
                color = QColor('#27AE60')
                text_color = QColor('white')
            elif diff_percent <= 10: 
                color = QColor('#F1C40F')
                text_color = QColor('black')
            else: 
                color = QColor('#C0392B')
                text_color = QColor('white')
                
            v_text = f"{vmon:.1f} V"
            i_text = f"{imon:.2f} uA"

        # [핵심 최적화] 값이 실제로 변했을 때만 UI 업데이트 수행 (Repaint 최소화)
        if self._last_bg_color != color or self._last_text_color != text_color:
            palette = self.palette()
            palette.setColor(self.backgroundRole(), color)
            palette.setColor(QPalette.ColorRole.WindowText, text_color)
            self.setPalette(palette)
            self._last_bg_color = color
            self._last_text_color = text_color

        if self._last_v_text != v_text:
            self.vmon_label.setText(v_text)
            self._last_v_text = v_text

        if self._last_i_text != i_text:
            self.imon_label.setText(i_text)
            self._last_i_text = i_text


class HVGridPanel(QGroupBox):
    def __init__(self, config):
        super().__init__("CAEN High Voltage Status")
        self.config = config
        self.channel_widgets = {}
        self.slot_groupboxes = {}
        self._last_titles = {} # 타이틀 갱신 캐시
        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        self.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        main_layout = QVBoxLayout(self)
        
        caen_config = self.config.get('caen_hv', {})
        crate_map = caen_config.get('crate_map', {})
        display_channels = caen_config.get('display_channels', {})
        
        for slot_str, board_info in crate_map.items():
            slot = int(slot_str)
            initial_title = f"Slot {slot}: {board_info.get('description', '')}"
            slot_group = QGroupBox(initial_title)
            slot_group.setFont(QFont("Arial", 10))
            self.slot_groupboxes[slot] = slot_group
            self._last_titles[slot] = initial_title
            
            slot_layout = QGridLayout(slot_group)
            slot_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
            main_layout.addWidget(slot_group)
            
            channels_to_display = []
            display_config = display_channels.get(slot_str)
            if display_config == "all": 
                channels_to_display = range(board_info['channels'])
            elif isinstance(display_config, list): 
                channels_to_display = display_config
                
            num_cols = 6
            for i, ch in enumerate(channels_to_display):
                widget = ChannelWidget(slot, ch)
                widget.setVisible(False)
                self.channel_widgets[(slot, ch)] = widget
                slot_layout.addWidget(widget, i // num_cols, i % num_cols)

    def _connect_signals(self):
        global_bus.sensor_data_updated.connect(self._on_hv_data_updated)

    @pyqtSlot(str, dict)
    def _on_hv_data_updated(self, sensor_type, payload):
        if sensor_type != 'hv_status': return
        data = payload.get('data', {})
        
        for slot, slot_data in data.get('slots', {}).items():
            board_temp = slot_data.get('board_temp')
            if board_temp is not None and board_temp != -1.0 and slot in self.slot_groupboxes:
                original_desc = self.config.get('caen_hv', {}).get('crate_map', {}).get(str(slot), {}).get('description', '')
                new_title = f"Slot {slot}: {original_desc}  [{board_temp:.1f} °C]"
                # 타이틀 캐싱
                if self._last_titles.get(slot) != new_title:
                    self.slot_groupboxes[slot].setTitle(new_title)
                    self._last_titles[slot] = new_title
                
            for channel, params in slot_data.get('channels', {}).items():
                key = (slot, channel)
                if key in self.channel_widgets:
                    widget = self.channel_widgets[key]
                    power_status = params.get('Pw', False)
                    if widget.isVisible() != power_status: 
                        widget.setVisible(power_status)
                    if power_status: 
                        widget.update_status(params)