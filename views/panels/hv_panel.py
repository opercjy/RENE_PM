# views/panels/hv_panel.py

from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, 
                             QFormLayout, QComboBox, QSpinBox, QDoubleSpinBox, 
                             QPushButton, QCheckBox, QTextEdit, QLabel, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSlot
from core.event_bus import global_bus
from datetime import datetime

class HVPanel(QWidget):
    def __init__(self, crate_map_keys):
        super().__init__()
        self.crate_map_keys = crate_map_keys
        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        
        control_group = QGroupBox("HV Channel Control")
        control_layout = QFormLayout(control_group)
        
        self.combo_slot = QComboBox()
        self.combo_slot.addItems(self.crate_map_keys)
        
        ch_layout = QHBoxLayout()
        self.spin_ch_start = QSpinBox()
        self.spin_ch_start.setRange(0, 99)
        self.spin_ch_end = QSpinBox()
        self.spin_ch_end.setRange(0, 99)
        self.chk_single = QCheckBox("Single")
        self.chk_single.setChecked(True)
        
        ch_layout.addWidget(QLabel("Start:")); ch_layout.addWidget(self.spin_ch_start)
        ch_layout.addWidget(QLabel("End:")); ch_layout.addWidget(self.spin_ch_end)
        ch_layout.addWidget(self.chk_single)
        
        self.spin_v0 = QDoubleSpinBox()
        self.spin_v0.setRange(0, 3000)
        self.spin_v0.setSuffix(" V")
        
        self.spin_i0 = QDoubleSpinBox()
        self.spin_i0.setRange(0, 1000)
        self.spin_i0.setSuffix(" uA")
        
        btn_apply = QPushButton("Apply Settings")
        btn_apply.setStyleSheet("background-color: #3498DB; color: white;")
        btn_apply.clicked.connect(self._emit_params_cmd)
        
        btn_on = QPushButton("Power ON")
        btn_on.setStyleSheet("background-color: #27AE60; color: white;")
        btn_on.clicked.connect(lambda: self._emit_power_cmd(True))
        
        btn_off = QPushButton("Power OFF")
        btn_off.setStyleSheet("background-color: #C0392B; color: white;")
        btn_off.clicked.connect(lambda: self._emit_power_cmd(False))
        
        control_layout.addRow("Slot:", self.combo_slot)
        control_layout.addRow("Channels:", ch_layout)
        control_layout.addRow("Set Voltage (V0Set):", self.spin_v0)
        control_layout.addRow("Set Current (I0Set):", self.spin_i0)
        control_layout.addRow(btn_apply)
        control_layout.addRow(btn_on, btn_off)
        
        log_group = QGroupBox("Control Status")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        
        layout.addWidget(control_group, 1)
        layout.addWidget(log_group, 2)
        
        # 내부 UI 이벤트
        self.chk_single.stateChanged.connect(self._on_single_check_changed)
        self.spin_ch_start.valueChanged.connect(self._on_ch_start_changed)

    def _connect_signals(self):
        global_bus.hv_setpoints_ready.connect(self._on_setpoints_ready)

    def _on_single_check_changed(self, state):
        is_single = (state == Qt.CheckState.Checked.value)
        self.spin_ch_end.setEnabled(not is_single)
        if is_single:
            self.spin_ch_end.setValue(self.spin_ch_start.value())

    def _on_ch_start_changed(self, val):
        if self.chk_single.isChecked():
            self.spin_ch_end.setValue(val)
        # 슬롯/채널 변경 시 현재 셋포인트를 지식망에 요청
        try:
            slot = int(self.combo_slot.currentText())
            global_bus.request_hv_setpoints.emit(slot, val)
        except ValueError:
            pass

    @pyqtSlot(dict)
    def _on_setpoints_ready(self, data):
        self.spin_v0.setValue(data.get('V0Set', 0))
        self.spin_i0.setValue(data.get('I0Set', 0))

    def _emit_params_cmd(self):
        try:
            slot = int(self.combo_slot.currentText())
            ch_start = self.spin_ch_start.value()
            ch_end = self.spin_ch_end.value()
        except ValueError: return
        
        v0 = self.spin_v0.value()
        i0 = self.spin_i0.value()
        
        reply = QMessageBox.question(
            self, 'Confirm Action', 
            f"Apply V0Set={v0}V, I0Set={i0}uA to Slot {slot}, Channels {ch_start}-{ch_end}?", 
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            channels = list(range(ch_start, ch_end + 1))
            cmd = {
                'type': 'set_params', 'slot': slot, 
                'channels': channels, 'params': {'V0Set': v0, 'I0Set': i0}
            }
            global_bus.cmd_hv_control.emit(cmd)

    def _emit_power_cmd(self, state):
        try:
            slot = int(self.combo_slot.currentText())
            ch_start = self.spin_ch_start.value()
            ch_end = self.spin_ch_end.value()
        except ValueError: return
        
        reply = QMessageBox.question(
            self, 'Confirm Action', 
            f"Turn Power {'ON' if state else 'OFF'} for Slot {slot}, Channels {ch_start}-{ch_end}?", 
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            channels = list(range(ch_start, ch_end + 1))
            cmd = {
                'type': 'set_power', 'slot': slot, 
                'channels': channels, 'value': state
            }
            global_bus.cmd_hv_control.emit(cmd)