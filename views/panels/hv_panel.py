# views/panels/hv_panel.py (전체 덮어쓰기)

from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, 
                             QFormLayout, QComboBox, QSpinBox, QDoubleSpinBox, 
                             QPushButton, QCheckBox, QTextEdit, QLabel, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSlot, QTimer
from core.event_bus import global_bus
from datetime import datetime

class HVPanel(QWidget):
    def __init__(self, crate_map_keys):
        super().__init__()
        self.crate_map_keys = crate_map_keys
        self._init_ui()
        self._connect_signals()
        
        # 초기 구동 시 첫 번째 슬롯/채널의 설정값을 가져오기 위해 1.5초 후 1회 자동 호출
        QTimer.singleShot(1500, self._request_current_setpoints)

    def _init_ui(self):
        layout = QHBoxLayout(self)
        
        control_group = QGroupBox("🎛️ HV Channel Control")
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
        
        # [핵심] 장비에서 현재 설정값을 명시적으로 읽어오는 버튼
        self.btn_read = QPushButton("🔄 Read Current Setpoints")
        self.btn_read.setStyleSheet("background-color: #F39C12; color: white; font-weight: bold; padding: 5px;")
        self.btn_read.clicked.connect(self._request_current_setpoints)

        self.spin_v0 = QDoubleSpinBox()
        self.spin_v0.setRange(0, 3000)
        self.spin_v0.setSuffix(" V")
        self.spin_v0.setDecimals(1)
        
        self.spin_i0 = QDoubleSpinBox()
        self.spin_i0.setRange(0, 1000)
        self.spin_i0.setSuffix(" uA")
        self.spin_i0.setDecimals(2)
        
        btn_apply = QPushButton("💾 Apply Settings")
        btn_apply.setStyleSheet("background-color: #3498DB; color: white; font-weight: bold;")
        btn_apply.clicked.connect(self._emit_params_cmd)
        
        btn_on = QPushButton("⚡ Power ON")
        btn_on.setStyleSheet("background-color: #27AE60; color: white; font-weight: bold;")
        btn_on.clicked.connect(lambda: self._emit_power_cmd(True))
        
        btn_off = QPushButton("🛑 Power OFF")
        btn_off.setStyleSheet("background-color: #C0392B; color: white; font-weight: bold;")
        btn_off.clicked.connect(lambda: self._emit_power_cmd(False))
        
        control_layout.addRow("Slot:", self.combo_slot)
        control_layout.addRow("Channels:", ch_layout)
        control_layout.addRow("", self.btn_read) 
        control_layout.addRow("Set Voltage (V0Set):", self.spin_v0)
        control_layout.addRow("Set Current (I0Set):", self.spin_i0)
        control_layout.addRow("", btn_apply)
        control_layout.addRow(btn_on, btn_off)
        
        log_group = QGroupBox("📝 Control Status Log")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        
        layout.addWidget(control_group, 1)
        layout.addWidget(log_group, 2)
        
        # 내부 UI 이벤트 연동
        self.chk_single.stateChanged.connect(self._on_single_check_changed)
        self.spin_ch_start.valueChanged.connect(self._on_ch_start_changed)
        # 슬롯 콤보박스가 바뀔 때도 값을 다시 긁어오게 변경
        self.combo_slot.currentTextChanged.connect(lambda _: self._request_current_setpoints())

    def _connect_signals(self):
        global_bus.hv_setpoints_ready.connect(self._on_setpoints_ready)
        # 패널 내부 로그 출력을 위한 연결
        global_bus.system_log_message.connect(self._append_log)

    def showEvent(self, event):
        """[UX 개선] 사용자가 이 탭을 클릭하여 열 때 즉시 CAEN 서버에 현재 값을 읽어옵니다."""
        super().showEvent(event)
        self._request_current_setpoints()

    @pyqtSlot(str, str)
    def _append_log(self, level, msg):
        if "HV" in msg or "CAEN" in msg or "Slot" in msg or "Setpoint" in msg:
            color = "green" if level == "SUCCESS" else "red" if level == "ERROR" else "blue"
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_text.append(f"<span style='color:{color};'>[{ts}] [{level}] {msg}</span>")

    def _on_single_check_changed(self, state):
        is_single = (state == Qt.CheckState.Checked.value)
        self.spin_ch_end.setEnabled(not is_single)
        if is_single:
            self.spin_ch_end.setValue(self.spin_ch_start.value())

    def _on_ch_start_changed(self, val):
        if self.chk_single.isChecked():
            self.spin_ch_end.setValue(val)
        # 서버 부하 방지를 위해 채널 SpinBox 조작 시 발생하는 자동 조회(Auto-Fetch) 로직 삭제. 
        # 사용자가 "Read Current Setpoints" 버튼을 수동 조작하도록 유도.

    def _request_current_setpoints(self):
        try:
            slot = int(self.combo_slot.currentText())
            channel = self.spin_ch_start.value()
            global_bus.request_hv_setpoints.emit(slot, channel)
            self.log_text.append(f"<i>Requesting server setpoints for Slot {slot} Ch {channel}...</i>")
        except ValueError:
            pass

    @pyqtSlot(dict)
    def _on_setpoints_ready(self, data):
        """서버에서 응답이 오면 스핀박스 값을 0.0이 아닌 실제 세팅값으로 바꿉니다."""
        # UI 업데이트 시 valueChanged 이벤트가 무한루프 타는 것 방지
        self.spin_v0.blockSignals(True)
        self.spin_i0.blockSignals(True)
        
        self.spin_v0.setValue(data.get('V0Set', 0.0))
        self.spin_i0.setValue(data.get('I0Set', 0.0))
        
        self.spin_v0.blockSignals(False)
        self.spin_i0.blockSignals(False)
        
        global_bus.system_log_message.emit("SUCCESS", f"HV Setpoints loaded: V0Set={data.get('V0Set', 0.0)}V, I0Set={data.get('I0Set', 0.0)}uA")

    def _emit_params_cmd(self):
        try:
            slot = int(self.combo_slot.currentText())
            ch_start = self.spin_ch_start.value()
            ch_end = self.spin_ch_end.value()
        except ValueError: 
            return
        
        v0 = self.spin_v0.value()
        i0 = self.spin_i0.value()
        
        reply = QMessageBox.question(
            self, '⚠️ Warning', 
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
        except ValueError: 
            return
        
        # 1차 경고
        reply1 = QMessageBox.warning(
            self, '1차 경고: 전원 제어', 
            f"Slot {slot}, Channels {ch_start}-{ch_end}의 전원을 {'ON' if state else 'OFF'} 하시겠습니까?", 
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
            QMessageBox.StandardButton.No
        )
        
        if reply1 == QMessageBox.StandardButton.Yes:
            # 2차 펫핑거(Fat Finger) 방지 인터락 (Double Interlock)
            reply2 = QMessageBox.critical(
                self, '2차 경고: 최종 확인', 
                "⚠️ 조작 실수 방지 ⚠️\n\n정말로 고전압 출력을 제어하시겠습니까?", 
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                QMessageBox.StandardButton.No
            )
            
            if reply2 == QMessageBox.StandardButton.Yes:
                channels = list(range(ch_start, ch_end + 1))
                cmd = {
                    'type': 'set_power', 'slot': slot, 
                    'channels': channels, 'value': state
                }
                global_bus.cmd_hv_control.emit(cmd)