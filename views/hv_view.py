from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QFormLayout, 
                             QComboBox, QSpinBox, QDoubleSpinBox, QPushButton, QLabel, QTextEdit, QCheckBox)
from PyQt5.QtCore import pyqtSignal, Qt

class HVControlView(QWidget):
    send_command = pyqtSignal(dict)
    request_setpoints = pyqtSignal(int, int)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._init_ui()

    def _init_ui(self):
        # 전체 레이아웃 (이제 그리드가 없으니 매우 심플해짐)
        layout = QHBoxLayout(self) 
        
        # 1. Control Settings
        ctrl_group = QGroupBox("Control Panel")
        form = QFormLayout(ctrl_group)
        
        self.slot = QComboBox()
        if self.config.get('caen_hv', {}).get('crate_map'):
             self.slot.addItems(self.config['caen_hv']['crate_map'].keys())
        
        ch_layout = QHBoxLayout()
        self.ch_s = QSpinBox(); self.ch_s.setRange(0, 99)
        self.ch_e = QSpinBox(); self.ch_e.setRange(0, 99)
        self.chk = QCheckBox("Single"); self.chk.setChecked(True)
        self.chk.stateChanged.connect(lambda s: self.ch_e.setEnabled(not s))
        ch_layout.addWidget(self.ch_s); ch_layout.addWidget(QLabel("~")); ch_layout.addWidget(self.ch_e); ch_layout.addWidget(self.chk)
        
        self.v0 = QDoubleSpinBox(); self.v0.setRange(0, 3000); self.v0.setSuffix(" V")
        self.i0 = QDoubleSpinBox(); self.i0.setRange(0, 1000); self.i0.setSuffix(" uA")
        
        form.addRow("Slot:", self.slot)
        form.addRow("Channel:", ch_layout)
        form.addRow("Set V0:", self.v0)
        form.addRow("Set I0:", self.i0)
        
        btn_apply = QPushButton("Apply Settings"); btn_apply.clicked.connect(self._on_apply)
        form.addRow(btn_apply)
        
        pwr_layout = QHBoxLayout()
        btn_on = QPushButton("ON"); btn_on.setStyleSheet("background:#2ecc71"); btn_on.clicked.connect(lambda: self._on_pwr(True))
        btn_off = QPushButton("OFF"); btn_off.setStyleSheet("background:#e74c3c; color:white"); btn_off.clicked.connect(lambda: self._on_pwr(False))
        pwr_layout.addWidget(btn_on); pwr_layout.addWidget(btn_off)
        form.addRow("Power:", pwr_layout)

        # 2. Log
        log_group = QGroupBox("Command Log")
        log_lay = QVBoxLayout(log_group)
        self.log = QTextEdit(); self.log.setReadOnly(True)
        log_lay.addWidget(self.log)
        
        layout.addWidget(ctrl_group, 4)
        layout.addWidget(log_group, 6)

    def append_log(self, msg): self.log.append(msg)
    def update_setpoints(self, d): self.v0.setValue(d.get('V0Set',0)); self.i0.setValue(d.get('I0Set',0))
    
    def _on_apply(self): self._send('set_params', {'V0Set': self.v0.value(), 'I0Set': self.i0.value()})
    def _on_pwr(self, s): self._send('set_power', {'value': s})
    
    def _send(self, t, p):
        try:
            s = int(self.slot.currentText())
            c1 = self.ch_s.value()
            c2 = self.ch_e.value() if not self.chk.isChecked() else c1
            cmd = {'type':t, 'slot':s, 'channels':list(range(c1, c2+1))}
            if t=='set_params': cmd['params']=p
            else: cmd.update(p)
            self.send_command.emit(cmd)
        except: pass