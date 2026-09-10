# views/panels/pdu_panel.py

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                             QGridLayout, QLabel, QPushButton, QTextEdit, QMessageBox)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSlot
from core.event_bus import global_bus
from datetime import datetime

class PDUPanel(QWidget):
    def __init__(self, config=None):
        super().__init__()
        self.config = config or {}
        
        # [수정] JSON의 계층 구조에 맞게 'netio_pdu' 내부의 'port_map'을 추출합니다.
        netio_config = self.config.get("netio_pdu", {})
        self.port_map = netio_config.get("port_map", {}) 
        
        self.is_connected = False
        self.port_widgets = {}
        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        layout.addWidget(self._create_global_status_group())
        layout.addWidget(self._create_port_control_group())
        
        log_group = QGroupBox("PDU Control Log")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        log_layout.addWidget(self.log_text)
        
        layout.addWidget(log_group)
        layout.addStretch(1)

    def _create_global_status_group(self):
        group = QGroupBox("PDU Global Status")
        layout = QHBoxLayout(group)
        
        self.lbl_conn = QLabel("DISCONNECTED")
        self.lbl_conn.setStyleSheet("font-weight: bold; color: red;")
        self.lbl_volt = QLabel("0.0 V")
        self.lbl_freq = QLabel("0.00 Hz")
        self.lbl_power = QLabel("0 W")
        
        data_font = QFont("Arial", 12, QFont.Weight.Bold)
        for lbl in [self.lbl_volt, self.lbl_freq, self.lbl_power]:
            lbl.setFont(data_font)
            
        layout.addWidget(QLabel("Connection:")); layout.addWidget(self.lbl_conn); layout.addStretch(1)
        layout.addWidget(QLabel("Voltage:")); layout.addWidget(self.lbl_volt); layout.addStretch(1)
        layout.addWidget(QLabel("Frequency:")); layout.addWidget(self.lbl_freq); layout.addStretch(1)
        layout.addWidget(QLabel("Total Load:")); layout.addWidget(self.lbl_power)
        
        self.btn_all_on = QPushButton("⚡ ALL ON")
        self.btn_all_on.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 5px;")
        self.btn_all_on.clicked.connect(lambda: self._confirm_all_control(True))
        
        self.btn_all_off = QPushButton("❌ ALL OFF")
        self.btn_all_off.setStyleSheet("background-color: #F44336; color: white; font-weight: bold; padding: 5px;")
        self.btn_all_off.clicked.connect(lambda: self._confirm_all_control(False))
        
        self.btn_all_on.setEnabled(False)
        self.btn_all_off.setEnabled(False)
        
        layout.addStretch(2)
        layout.addWidget(self.btn_all_on)
        layout.addWidget(self.btn_all_off)
        return group

    def _create_port_control_group(self):
        group = QGroupBox("PDU Output Ports")
        grid = QGridLayout(group)
        grid.setSpacing(8)
        
        # 헤더에 "Name"을 추가합니다.
        headers = ["#", "Name", "State", "Power (W)", "Current (mA)", "Energy (Wh)", "Control"]
        for i, header in enumerate(headers):
            lbl = QLabel(header)
            lbl.setStyleSheet("font-weight: bold; text-decoration: underline;")
            grid.addWidget(lbl, 0, i, alignment=Qt.AlignmentFlag.AlignCenter)
            
        for i in range(1, 9):
            # JSON의 키는 문자열이므로 str(i)를 사용하여 이름을 가져옵니다.
            # 매핑된 이름이 없으면 기본값으로 "Port X"를 사용합니다.
            port_name_str = self.port_map.get(str(i), f"Port {i}")
            lbl_name = QLabel(port_name_str)
            lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)

            lbl_state = QLabel("N/A")
            lbl_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._set_state_style(lbl_state, None)
            
            btn_on = QPushButton("ON")
            btn_off = QPushButton("OFF")
            btn_on.clicked.connect(lambda checked, p=i: self._request_port_control(p, True))
            btn_off.clicked.connect(lambda checked, p=i: self._request_port_control(p, False))
            btn_on.setEnabled(False)
            btn_off.setEnabled(False)
            
            ctrl_widget = QWidget()
            ctrl_layout = QHBoxLayout(ctrl_widget)
            ctrl_layout.setContentsMargins(0, 0, 0, 0)
            ctrl_layout.addWidget(btn_on)
            ctrl_layout.addWidget(btn_off)
            
            self.port_widgets[i] = {
                'name': lbl_name, 'state': lbl_state, 'power': QLabel("0"), 
                'current': QLabel("0"), 'energy': QLabel("0"),
                'btn_on': btn_on, 'btn_off': btn_off
            }
            
            grid.addWidget(QLabel(str(i)), i, 0, alignment=Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(lbl_name, i, 1, alignment=Qt.AlignmentFlag.AlignCenter) # 이름 열 추가
            grid.addWidget(lbl_state, i, 2)
            grid.addWidget(self.port_widgets[i]['power'], i, 3, alignment=Qt.AlignmentFlag.AlignRight)
            grid.addWidget(self.port_widgets[i]['current'], i, 4, alignment=Qt.AlignmentFlag.AlignRight)
            grid.addWidget(self.port_widgets[i]['energy'], i, 5, alignment=Qt.AlignmentFlag.AlignRight)
            grid.addWidget(ctrl_widget, i, 6)
            
        return group

    def _set_state_style(self, label, state):
        if state is True:
            label.setText("ON")
            label.setStyleSheet("background-color: #4CAF50; color: white; border-radius: 5px; font-weight: bold; padding: 3px;")
        elif state is False:
            label.setText("OFF")
            label.setStyleSheet("background-color: #9E9E9E; color: white; border-radius: 5px; font-weight: bold; padding: 3px;")
        else:
            label.setText("N/A")
            label.setStyleSheet("background-color: #FFC107; color: black; border-radius: 5px; font-weight: bold; padding: 3px;")

    def _connect_signals(self):
        global_bus.sensor_data_updated.connect(self._on_sensor_data_updated)
        global_bus.device_connection_changed.connect(self._on_connection_changed)
        global_bus.system_log_message.connect(self._append_log)

    @pyqtSlot(str, dict)
    def _on_sensor_data_updated(self, sensor_type, payload):
        if sensor_type != 'pdu_status': return
        data = payload.get('data', {})
        g = data.get('global', {})
        
        self.lbl_volt.setText(f"{g.get('volt', 0):.1f} V")
        self.lbl_freq.setText(f"{g.get('freq', 0):.2f} Hz")
        self.lbl_power.setText(f"{g.get('power', 0)} W")
        
        for p_num, values in data.get('outputs', {}).items():
            if p_num in self.port_widgets:
                w = self.port_widgets[p_num]
                state_bool = values.get('state_bool')
                self._set_state_style(w['state'], state_bool)
                w['power'].setText(str(values.get('power', 0)))
                w['current'].setText(str(values.get('current', 0)))
                w['energy'].setText(str(values.get('energy', 0)))
                
                if self.is_connected:
                    w['btn_on'].setEnabled(not state_bool)
                    w['btn_off'].setEnabled(state_bool)

    @pyqtSlot(str, bool)
    def _on_connection_changed(self, device, state):
        if device != 'netio_pdu': return
        self.is_connected = state
        if state:
            self.lbl_conn.setText("CONNECTED")
            self.lbl_conn.setStyleSheet("font-weight: bold; color: green;")
            self.btn_all_on.setEnabled(True)
            self.btn_all_off.setEnabled(True)
        else:
            self.lbl_conn.setText("DISCONNECTED")
            self.lbl_conn.setStyleSheet("font-weight: bold; color: red;")
            self.btn_all_on.setEnabled(False)
            self.btn_all_off.setEnabled(False)
            for w in self.port_widgets.values():
                w['btn_on'].setEnabled(False)
                w['btn_off'].setEnabled(False)
                self._set_state_style(w['state'], None)

    @pyqtSlot(str, str)
    def _append_log(self, level, message):
        """전문가 또는 워커에서 발생한 제어 로그를 수신"""
        ts = datetime.now().strftime("%H:%M:%S")
        color_map = {"INFO": "blue", "SUCCESS": "green", "WARNING": "orange", "ERROR": "red", "CRITICAL": "darkred"}
        color = color_map.get(level, "black")
        self.log_text.append(f"<span style='color:{color};'>[{ts}] [{level}] {message}</span>")

    # --- 사용자 입력(이벤트)을 지식망으로 발행 ---
    def _request_port_control(self, port_num, state):
        global_bus.cmd_pdu_control_single.emit(port_num, state)
        # 피드백이 오기 전까지 버튼 비활성화 처리 (UX)
        self.port_widgets[port_num]['btn_on'].setEnabled(False)
        self.port_widgets[port_num]['btn_off'].setEnabled(False)

    def _confirm_all_control(self, state):
        action = "ON" if state else "OFF"
        reply = QMessageBox.warning(
            self, '⚠️ Confirm PDU ALL Control', 
            f"DANGER: Are you sure you want to turn ALL PDU ports {action}?", 
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            global_bus.cmd_pdu_control_all.emit(state)
            self.btn_all_on.setEnabled(False)
            self.btn_all_off.setEnabled(False)