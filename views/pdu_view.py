from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                             QGridLayout, QLabel, QPushButton, QTextEdit, QMessageBox)
from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt
from PyQt5.QtGui import QFont
from datetime import datetime

class PDUView(QWidget):
    # 메인 윈도우(Worker)로 보낼 제어 시그널
    sig_control = pyqtSignal(int, bool) # (Port Number, State)
    sig_control_all = pyqtSignal(bool)  # (State)

    def __init__(self, config, data_manager, parent=None):
        super().__init__(parent)
        self.config = config
        self.dm = data_manager
        self.port_widgets = {}
        self.pdu_global_labels = {}
        
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # 1. Global Status & All Control
        layout.addWidget(self._create_global_status_group())
        
        # 2. Port Control Grid
        layout.addWidget(self._create_port_control_group())
        
        # 3. Log Area
        log_group = QGroupBox("PDU Control Log")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        
        layout.addWidget(log_group)
        layout.addStretch(1)

    def _create_global_status_group(self):
        group = QGroupBox("PDU Global Status")
        layout = QHBoxLayout()
        
        self.pdu_global_labels['conn'] = QLabel("DISCONNECTED")
        self.pdu_global_labels['conn'].setStyleSheet("font-weight: bold; color: red;")
        self.pdu_global_labels['volt'] = QLabel("0.0 V")
        self.pdu_global_labels['freq'] = QLabel("0.00 Hz")
        self.pdu_global_labels['power'] = QLabel("0 W")
        
        data_font = QFont()
        data_font.setPointSize(12)
        data_font.setBold(True)
        for key in ['volt', 'freq', 'power']:
            self.pdu_global_labels[key].setFont(data_font)
        
        layout.addWidget(QLabel("Connection:")); layout.addWidget(self.pdu_global_labels['conn'])
        layout.addStretch(1)
        layout.addWidget(QLabel("Voltage:")); layout.addWidget(self.pdu_global_labels['volt'])
        layout.addStretch(1)
        layout.addWidget(QLabel("Frequency:")); layout.addWidget(self.pdu_global_labels['freq'])
        layout.addStretch(1)
        layout.addWidget(QLabel("Total Load:")); layout.addWidget(self.pdu_global_labels['power'])
        
        self.btn_all_on = QPushButton("⚡ ALL ON")
        self.btn_all_on.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 5px;")
        self.btn_all_on.clicked.connect(lambda: self._confirm_all(True))
        
        self.btn_all_off = QPushButton("❌ ALL OFF")
        self.btn_all_off.setStyleSheet("background-color: #F44336; color: white; font-weight: bold; padding: 5px;")
        self.btn_all_off.clicked.connect(lambda: self._confirm_all(False))
        
        # 초기 상태 비활성화
        self.btn_all_on.setEnabled(False)
        self.btn_all_off.setEnabled(False)
        
        layout.addStretch(2)
        layout.addWidget(self.btn_all_on)
        layout.addWidget(self.btn_all_off)
        
        group.setLayout(layout)
        return group

    def _create_port_control_group(self):
        group = QGroupBox("PDU Output Ports")
        grid = QGridLayout()
        grid.setSpacing(8)
        
        headers = ["#", "Name", "State", "Power (W)", "Current (mA)", "Energy (Wh)", "Control"]
        for i, header in enumerate(headers):
            lbl = QLabel(header)
            lbl.setStyleSheet("font-weight: bold; text-decoration: underline;")
            grid.addWidget(lbl, 0, i, Qt.AlignCenter)
            
        port_map = self.config.get('netio_pdu', {}).get('port_map', {})
        
        for i in range(8):
            p_num = i + 1
            row = i + 1
            p_name = port_map.get(str(p_num), f"Port {p_num}")
            
            lbl_state = QLabel("N/A")
            lbl_state.setAlignment(Qt.AlignCenter)
            self._set_port_style(lbl_state, None)
            
            btn_on = QPushButton("ON")
            btn_off = QPushButton("OFF")
            
            btn_on.clicked.connect(lambda _, x=p_num: self._control_port(x, True))
            btn_off.clicked.connect(lambda _, x=p_num: self._control_port(x, False))
            
            btn_on.setEnabled(False)
            btn_off.setEnabled(False)
            
            ctrl_widget = QWidget()
            ctrl_layout = QHBoxLayout(ctrl_widget)
            ctrl_layout.setContentsMargins(0,0,0,0)
            ctrl_layout.addWidget(btn_on)
            ctrl_layout.addWidget(btn_off)
            
            self.port_widgets[p_num] = {
                'state_lbl': lbl_state,
                'power': QLabel("0"),
                'current': QLabel("0"),
                'energy': QLabel("0"),
                'btn_on': btn_on,
                'btn_off': btn_off
            }
            
            grid.addWidget(QLabel(str(p_num)), row, 0, Qt.AlignCenter)
            grid.addWidget(QLabel(p_name), row, 1)
            grid.addWidget(lbl_state, row, 2)
            grid.addWidget(self.port_widgets[p_num]['power'], row, 3, Qt.AlignRight)
            grid.addWidget(self.port_widgets[p_num]['current'], row, 4, Qt.AlignRight)
            grid.addWidget(self.port_widgets[p_num]['energy'], row, 5, Qt.AlignRight)
            grid.addWidget(ctrl_widget, row, 6)
            
        group.setLayout(grid)
        return group

    def _set_port_style(self, label, state):
        if state is True:
            label.setText("ON")
            label.setStyleSheet("background-color: #4CAF50; color: white; border-radius: 5px; font-weight: bold; padding: 3px;")
        elif state is False:
            label.setText("OFF")
            label.setStyleSheet("background-color: #9E9E9E; color: white; border-radius: 5px; font-weight: bold; padding: 3px;")
        else:
            label.setText("N/A")
            label.setStyleSheet("background-color: #FFC107; color: black; border-radius: 5px; font-weight: bold; padding: 3px;")

    def _control_port(self, p_num, state):
        if not self.dm.is_pdu_connected:
            self.append_log("WARNING", "Cannot control port when PDU is disconnected.")
            return
        self.sig_control.emit(p_num, state)
        # 버튼 잠시 비활성화
        if p_num in self.port_widgets:
            self.port_widgets[p_num]['btn_on'].setEnabled(False)
            self.port_widgets[p_num]['btn_off'].setEnabled(False)

    def _confirm_all(self, state):
        if not self.dm.is_pdu_connected:
            self.append_log("WARNING", "Cannot control ports when PDU is disconnected.")
            return
        action = "ON" if state else "OFF"
        reply = QMessageBox.warning(self, 'Confirm PDU ALL', 
                                    f"DANGER: Are you sure you want to turn ALL ports {action}?", 
                                    QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.sig_control_all.emit(state)
            self.btn_all_on.setEnabled(False)
            self.btn_all_off.setEnabled(False)
        else:
            self.append_log("INFO", f"ALL {action} command cancelled.")

    @pyqtSlot(dict)
    def update_ui(self, data):
        """데이터 갱신"""
        g = data.get('global', {})
        if 'volt' in g: self.pdu_global_labels['volt'].setText(f"{g.get('volt', 0):.1f} V")
        if 'freq' in g: self.pdu_global_labels['freq'].setText(f"{g.get('freq', 0):.2f} Hz")
        if 'power' in g: self.pdu_global_labels['power'].setText(f"{g.get('power', 0)} W")
        
        is_conn = self.dm.is_pdu_connected
        
        for p_num, info in data.get('outputs', {}).items():
            if p_num in self.port_widgets:
                w = self.port_widgets[p_num]
                state_bool = info.get('state_bool')
                
                self._set_port_style(w['state_lbl'], state_bool)
                w['power'].setText(str(info.get('power', 0)))
                w['current'].setText(str(info.get('current', 0)))
                w['energy'].setText(str(info.get('energy', 0)))
                
                if is_conn:
                    w['btn_on'].setEnabled(not state_bool)
                    w['btn_off'].setEnabled(bool(state_bool))
        
        if is_conn:
            self.btn_all_on.setEnabled(True)
            self.btn_all_off.setEnabled(True)

    @pyqtSlot(bool)
    def update_connection(self, connected):
        """[추가됨] 연결 상태에 따라 UI(버튼, 라벨) 업데이트"""
        if connected:
            self.pdu_global_labels['conn'].setText("CONNECTED")
            self.pdu_global_labels['conn'].setStyleSheet("font-weight: bold; color: green;")
            self.btn_all_on.setEnabled(True)
            self.btn_all_off.setEnabled(True)
        else:
            self.pdu_global_labels['conn'].setText("DISCONNECTED")
            self.pdu_global_labels['conn'].setStyleSheet("font-weight: bold; color: red;")
            
            self.btn_all_on.setEnabled(False)
            self.btn_all_off.setEnabled(False)
            
            for w in self.port_widgets.values():
                w['btn_on'].setEnabled(False)
                w['btn_off'].setEnabled(False)
                self._set_port_style(w['state_lbl'], None)

    @pyqtSlot(str, str)
    def append_log(self, level, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        c_map = {"INFO":"blue", "SUCCESS":"green", "WARNING":"orange", "ERROR":"red"}
        col = c_map.get(level, "black")
        self.log_text.append(f"<span style='color:{col};'>[{ts}] [{level}] {msg}</span>")
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())