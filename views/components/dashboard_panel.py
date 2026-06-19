# views/components/dashboard_panel.py (전체 덮어쓰기)

from PyQt6.QtWidgets import QGroupBox, QHBoxLayout, QVBoxLayout, QGridLayout, QFrame, QLabel, QWidget
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSlot
from core.event_bus import global_bus

class DashboardPanel(QGroupBox):
    def __init__(self, config):
        super().__init__("🖥️ System Status Dashboard")
        self.config = config
        self.labels = {}
        self.safety_widgets = {}
        
        self.latest_radon_mu = 0.0
        self.latest_radon_sigma = 0.0
        self.latest_radon_state = "Initializing"
        self.latest_radon_countdown = -1

        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        self.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.setMaximumHeight(240)
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # ==========================================
        # [디자인 개편] 모던한 플랫 디자인 안전 카드
        # ==========================================
        safety_frame = QFrame()
        safety_frame.setObjectName("SafetyCard") # QSS 타겟팅을 위한 ObjectName 부여
        safety_layout = QVBoxLayout(safety_frame)
        safety_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_lbl = QLabel("🛡️ OVERALL SAFETY")
        title_lbl.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.safety_widgets['status_lbl'] = QLabel("✅ NORMAL")
        self.safety_widgets['status_lbl'].setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.safety_widgets['status_lbl'].setFont(QFont("Arial", 22, QFont.Weight.Black))
        
        self.safety_widgets['guide_lbl'] = QLabel("Monitoring Active.")
        self.safety_widgets['guide_lbl'].setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.safety_widgets['guide_lbl'].setFont(QFont("Arial", 11, QFont.Weight.Bold))

        self.safety_widgets['frame'] = safety_frame
        self.safety_widgets['_last_phase'] = "" # 렌더링 갱신 방지용 캐시

        safety_layout.addStretch(1)
        safety_layout.addWidget(title_lbl)
        safety_layout.addSpacing(10)
        safety_layout.addWidget(self.safety_widgets['status_lbl'])
        safety_layout.addSpacing(5)
        safety_layout.addWidget(self.safety_widgets['guide_lbl'])
        safety_layout.addStretch(1)

        # 초기 상태 (NORMAL) QSS 세팅
        safety_frame.setStyleSheet("""
            QFrame#SafetyCard {
                background-color: #27AE60; 
                border-radius: 10px;
            }
            QLabel {
                color: white; 
                border: none;
                background: transparent;
            }
        """)

        env_widget = QWidget()
        env_layout = QGridLayout(env_widget)
        env_layout.setContentsMargins(0, 0, 0, 0)
        env_layout.setSpacing(8)

        env_groups = [
            ("🌡️ LS Temp", ["L_LS_Temp", "R_LS_Temp"]),
            ("💧 LS Level", ["GdLS_level", "GCLS_level"]),
            ("🧲 Magnetometer", ["B_x", "B_y", "B_z", "B"]),
            ("☁️ TH/O2", ["TH_O2_Temp", "TH_O2_Humi", "TH_O2_Oxygen"]),
            ("📟 Arduino", ["Temp1", "Humi1", "Temp2", "Humi2", "Dist"]),
            ("☢️ Radon", ["Radon_Value"]),
            ("🔥 Flame Det.", ["Fire_Status"]),
            ("🧪 VOC Det.", ["VOC_Conc"]),
            ("🔋 UPS System", ["UPS_Status", "UPS_Charge", "UPS_TimeLeft"]),
            ("🎛️ HV System", ["HV_Board_Temps"]) 
        ]

        max_cols = 5
        row, col = 0, 0

        for title, labels in env_groups:
            group_frame = QFrame()
            group_frame.setFrameShape(QFrame.Shape.StyledPanel)
            group_frame.setStyleSheet("background-color: #f8f9fa; border-radius: 5px; border: 1px solid #e9ecef;")
            g_layout = QVBoxLayout(group_frame)
            g_layout.setSpacing(1)
            g_layout.setContentsMargins(4, 4, 4, 4)
            
            g_lbl = QLabel(title)
            g_lbl.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            g_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            g_layout.addWidget(g_lbl)
            
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Sunken)
            g_layout.addWidget(line)

            for name in labels:
                display_name = name.replace("TH_O2_", "").replace("_", " ")
                if name == "B": display_name = "|B|"
                elif name == "B_x": display_name = "Bx"
                elif name == "B_y": display_name = "By"
                elif name == "B_z": display_name = "Bz"
                elif name == "Fire_Status": display_name = "State"
                elif name == "VOC_Conc": display_name = "Level"
                elif name == "HV_Board_Temps": display_name = "Temps"

                lbl = QLabel(f"{display_name}: Wait...")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setProperty('_last_html', "") # 캐시 초기화
                self.labels[name] = lbl
                
                base_style = "font-size: 10pt;"
                if name == "B_x": lbl.setStyleSheet(base_style + "color: #d62728; font-weight: bold;")
                elif name == "B_y": lbl.setStyleSheet(base_style + "color: #2ca02c; font-weight: bold;")
                elif name == "B_z": lbl.setStyleSheet(base_style + "color: #1f77b4; font-weight: bold;")
                elif name == "B": lbl.setStyleSheet(base_style + "color: #000000; font-weight: bold;")
                else: lbl.setStyleSheet(base_style)
                
                g_layout.addWidget(lbl)
                
            g_layout.addStretch(1)
            env_layout.addWidget(group_frame, row, col)
            
            col += 1
            if col >= max_cols:
                col = 0
                row += 1

        main_layout.addWidget(safety_frame, 20)
        main_layout.addWidget(env_widget, 80)

    def _connect_signals(self):
        global_bus.sensor_data_updated.connect(self._on_sensor_data_updated)
        global_bus.safety_status_changed.connect(self._on_safety_status_changed)
        global_bus.radon_status_updated.connect(self._on_radon_status_updated)

    @pyqtSlot(str, int)
    def _on_radon_status_updated(self, state, countdown):
        self.latest_radon_state = state
        self.latest_radon_countdown = countdown
        self._update_radon_display()

    def _update_radon_display(self):
        line1 = "<b>Radon Value:</b>"
        line2 = f"{self.latest_radon_mu:.2f} &plusmn; {self.latest_radon_sigma:.2f}"
        line3 = f"<b>Status:</b> {self.latest_radon_state}"
        line4 = f"({self.latest_radon_countdown}s left)" if self.latest_radon_countdown >= 0 else ""
        combined_text = f"{line1}<br>{line2}<br>{line3}<br>{line4}"
        self._update_label('Radon_Value', combined_text)

    @pyqtSlot(str, str)
    def _on_safety_status_changed(self, phase, html_msg):
        # [핵심] 상태가 변했을 때만 UI를 갱신하여 렌더링 병목 방지
        if self.safety_widgets.get('_last_phase') == phase:
            return
            
        w_status = self.safety_widgets['status_lbl']
        w_guide = self.safety_widgets['guide_lbl']
        w_frame = self.safety_widgets['frame']

        if phase == "EMERGENCY":
            w_frame.setStyleSheet("""
                QFrame#SafetyCard { background-color: #C0392B; border-radius: 10px; }
                QLabel { color: white; border: none; background: transparent; }
            """)
            w_status.setText("🚨 EMERGENCY")
            w_guide.setText("CRITICAL DANGER.\nEVACUATE!")
        elif phase == "WARNING":
            w_frame.setStyleSheet("""
                QFrame#SafetyCard { background-color: #F1C40F; border-radius: 10px; }
                QLabel { color: #2C3E50; border: none; background: transparent; }
            """)
            w_status.setText("⚠️ WARNING")
            w_guide.setText("System Check\nRequired.")
        else:
            w_frame.setStyleSheet("""
                QFrame#SafetyCard { background-color: #27AE60; border-radius: 10px; }
                QLabel { color: white; border: none; background: transparent; }
            """)
            w_status.setText("✅ NORMAL")
            w_guide.setText("Monitoring Active.")
            
        self.safety_widgets['_last_phase'] = phase

    @pyqtSlot(str, dict)
    def _on_sensor_data_updated(self, sensor_type, payload):
        data = payload.get('data', {})
        if sensor_type == 'raw_data':
            if 'rtd' in data or 'volt' in data:
                rtd, volt = data.get('rtd', []), data.get('volt', [])
                if len(rtd) > 0: self._update_label("L_LS_Temp", f"L LS Temp: {rtd[0]:.2f} °C")
                if len(rtd) > 1: self._update_label("R_LS_Temp", f"R LS Temp: {rtd[1]:.2f} °C")
                if len(volt) > 0: self._update_label("GdLS_level", f"GdLS level: {(volt[0]*100):.1f} mm")
                if len(volt) > 1: self._update_label("GCLS_level", f"GCLS level: {(volt[1]*100):.1f} mm")
            if 'mag' in data:
                mag = data.get('mag', [])
                keys = ["B_x", "B_y", "B_z", "B"]
                display = ["Bx", "By", "Bz", "|B|"]
                for i, k in enumerate(keys):
                    if len(mag) > i: self._update_label(k, f"{display[i]}: {mag[i]:.2f} mG")
            if 'th_o2' in data:
                d = data['th_o2']
                if 'temp' in d: self._update_label("TH_O2_Temp", f"Temp: {d['temp']:.2f} °C")
                if 'humi' in d: self._update_label("TH_O2_Humi", f"Humi: {d['humi']:.2f} %")
                if 'o2' in d: self._update_label("TH_O2_Oxygen", f"Oxygen: {d['o2']:.2f} %")
            if 'arduino' in data:
                d = data['arduino']
                if 'temp0' in d and d['temp0'] is not None: self._update_label("Temp1", f"Temp1: {d['temp0']:.2f} °C")
                if 'humi0' in d and d['humi0'] is not None: self._update_label("Humi1", f"Humi1: {d['humi0']:.2f} %")
                if 'dist' in d and d['dist'] is not None: self._update_label("Dist", f"Dist: {d['dist']:.1f} cm")
        elif sensor_type == 'fire_status':
            self._update_label("Fire_Status", f"State: {data.get('msg', 'Wait...')}")
        elif sensor_type == 'voc_status':
            self._update_label("VOC_Conc", f"Level: {data.get('conc', 0.0):.3f} ppm")
        elif sensor_type == 'ups_status':
            status = data.get('STATUS', 'N/A')
            status_color = "green" if "ONLINE" in status else "orange" if "BATT" in status else "red"
            self._update_label("UPS_Status", f"Stat: <b style='color:{status_color};'>{status}</b>")
            self._update_label("UPS_Charge", f"Charge: <b style='color:#2ca02c;'>{data.get('BCHARGE', 0.0):.1f} %</b>")
            self._update_label("UPS_TimeLeft", f"Time Left: <b style='color:#ff7f0e;'>{data.get('TIMELEFT', 0.0):.1f} min</b>")
        
        elif sensor_type == 'hv_status':
            temp_parts = []
            for slot, slot_data in sorted(data.get('slots', {}).items()):
                t = slot_data.get('board_temp', -1.0)
                if t != -1.0:
                    if t >= 65.0: temp_color = "red"
                    elif t > 50.0: temp_color = "orange"
                    else: temp_color = "green"
                    temp_parts.append(f"S{slot}: <b style='color:{temp_color};'>{t:.1f}°C</b>")
            board_text = " | ".join(temp_parts) if temp_parts else "No Data"
            self._update_label('HV_Board_Temps', board_text)

        elif sensor_type == 'radon_avg':
            self.latest_radon_mu = data.get('mu', 0.0)
            self.latest_radon_sigma = data.get('sigma', 0.0)
            self._update_radon_display()

    def _update_label(self, key, html_text):
        # [핵심 최적화] 텍스트가 실제로 바뀌었을 때만 UI를 갱신하여 파싱 병목 방지
        if key in self.labels:
            lbl = self.labels[key]
            if lbl.property('_last_html') != html_text:
                lbl.setText(html_text)
                lbl.setProperty('_last_html', html_text)