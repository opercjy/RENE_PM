from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QGridLayout, QLabel, QFrame)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt
import numpy as np

class DashboardView(QWidget):
    def __init__(self, config, data_manager):
        super().__init__()
        self.config = config
        self.dm = data_manager
        
        # [중요] 로컬 저장소 초기화 (main_win 의존성 제거)
        self.labels = {} 
        self.safety_widgets = {}
        
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        indicator_group_box = QGroupBox("🖥️ System Status Dashboard")
        indicator_group_box.setFont(QFont("Arial", 11, QFont.Bold))
        indicator_group_box.setMaximumHeight(240) 
        
        main_layout = QHBoxLayout(indicator_group_box)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        # =========================================================
        # [Left] Safety Status (20%)
        # =========================================================
        safety_frame = QFrame()
        safety_frame.setFrameShape(QFrame.StyledPanel)
        safety_frame.setStyleSheet("background-color: #d4edda; border: 3px solid #28a745; border-radius: 10px;")
        
        s_layout = QVBoxLayout(safety_frame)
        s_layout.setAlignment(Qt.AlignCenter)
        
        # [수정] self.safety_widgets에 직접 저장 (self.main_win 사용 안 함)
        self.safety_widgets['status'] = QLabel("✅ SYSTEM\nNORMAL")
        self.safety_widgets['status'].setAlignment(Qt.AlignCenter)
        self.safety_widgets['status'].setFont(QFont("Arial", 16, QFont.Bold))
        self.safety_widgets['status'].setStyleSheet("color: #155724; border: none; background: transparent;")
        
        self.safety_widgets['guide'] = QLabel("Monitoring\nActive")
        self.safety_widgets['guide'].setAlignment(Qt.AlignCenter)
        self.safety_widgets['guide'].setFont(QFont("Arial", 10))
        self.safety_widgets['guide'].setStyleSheet("border: none; background: transparent; color: #155724;")
        
        self.safety_widgets['frame'] = safety_frame

        s_layout.addWidget(QLabel("🛡️ SAFETY"))
        s_layout.addStretch(1)
        s_layout.addWidget(self.safety_widgets['status'])
        s_layout.addWidget(self.safety_widgets['guide'])
        s_layout.addStretch(1)
        
        # =========================================================
        # [Right] Sensors Panel (80%)
        # =========================================================
        env_widget = QWidget()
        env_layout = QGridLayout(env_widget)
        env_layout.setContentsMargins(0, 0, 0, 0)
        env_layout.setSpacing(8)

        env_groups = [
            ("🌡️ LS Temp", ["L_LS_Temp", "R_LS_Temp"]),
            ("💧 LS Level", ["GdLS_level", "GCLS_level"]),
            ("🧲 Magnetometer", ["B_x", "B_y", "B_z", "B"]),
            ("☁️ TH/O2 Sensor", ["TH_O2_Temp", "TH_O2_Humi", "TH_O2_Oxygen"]),
            ("📟 Arduino Env", ["Temp1", "Humi1", "Temp2", "Humi2", "Dist"]),
            ("☢️ Radon Sensor", ["Radon_Value"]),
            ("🔥 Flame Detector", ["Fire_Status"]),
            ("🧪 VOC Detector", ["VOC_Conc"]),
            ("🔋 UPS System", ["UPS_Status", "UPS_Charge", "UPS_TimeLeft"]),
            ("🎛️ HV Board Temp", ["HV_Board_Temps"]) 
        ]
        
        max_cols = 5; row, col = 0, 0
        
        for title, keys in env_groups:
            g_frame = QFrame()
            g_frame.setFrameShape(QFrame.StyledPanel)
            g_frame.setStyleSheet("background-color: #f8f9fa; border-radius: 5px; border: 1px solid #e9ecef;")
            g_layout = QVBoxLayout(g_frame)
            g_layout.setSpacing(1); g_layout.setContentsMargins(4, 4, 4, 4)
            
            title_lbl = QLabel(title)
            title_lbl.setFont(QFont("Arial", 9, QFont.Bold))
            title_lbl.setAlignment(Qt.AlignCenter)
            g_layout.addWidget(title_lbl)
            
            line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken)
            g_layout.addWidget(line)

            for key in keys:
                disp_name = key.replace("TH_O2_", "").replace("_", " ")
                if key == "B": disp_name = "|B|"
                if key == "Fire_Status": disp_name = "State"
                if key == "VOC_Conc": disp_name = "Level"
                if key == "HV_Board_Temps": disp_name = "Temps"
                
                lbl = QLabel(f"{disp_name}: Wait...")
                lbl.setFont(QFont("Arial", 9))
                lbl.setAlignment(Qt.AlignCenter)
                
                # [수정] 로컬 labels에 저장
                self.labels[key] = lbl 
                
                # 스타일 적용
                base_style = "font-size: 10pt;"
                if key == "B_x": lbl.setStyleSheet(base_style + "color: #d62728; font-weight: bold;")
                elif key == "B_y": lbl.setStyleSheet(base_style + "color: #2ca02c; font-weight: bold;")
                elif key == "B_z": lbl.setStyleSheet(base_style + "color: #1f77b4; font-weight: bold;")
                elif key == "B":   lbl.setStyleSheet(base_style + "color: #000000; font-weight: bold;")
                else: lbl.setStyleSheet(base_style)
                
                g_layout.addWidget(lbl)
            
            g_layout.addStretch(1)
            env_layout.addWidget(g_frame, row, col)
            
            col += 1
            if col >= max_cols: col = 0; row += 1

        main_layout.addWidget(safety_frame, 15)
        main_layout.addWidget(env_widget, 85)
        layout.addWidget(indicator_group_box)

    def update_ui(self):
        """DataManager에서 최신 데이터를 가져와 UI 갱신"""
        self.dm.lock.lockForRead()
        try:
            readings = self.dm.latest_readings
            
            # 1. DAQ
            daq = readings.get('daq', {})
            rtd = daq.get('rtd', []); dist = daq.get('dist', [])
            if rtd: 
                self._set_text('L_LS_Temp', f"{rtd[0]:.2f} °C")
                if len(rtd)>1: self._set_text('R_LS_Temp', f"{rtd[1]:.2f} °C")
            if dist:
                self._set_text('GdLS_level', f"{dist[0]:.1f} mm")
                if len(dist)>1: self._set_text('GCLS_level', f"{dist[1]:.1f} mm")

            # 2. Mag
            mag = readings.get('mag', [])
            if mag and len(mag)>=4:
                self._set_text('B_x', f"{mag[0]:.2f} mG"); self._set_text('B_y', f"{mag[1]:.2f} mG")
                self._set_text('B_z', f"{mag[2]:.2f} mG"); self._set_text('B', f"{mag[3]:.2f} mG")

            # 3. TH/O2
            th = readings.get('th_o2', {})
            if th:
                self._set_text('TH_O2_Temp', f"{th.get('temp',0):.1f} °C")
                self._set_text('TH_O2_Humi', f"{th.get('humi',0):.1f} %")
                self._set_text('TH_O2_Oxygen', f"{th.get('o2',0):.1f} %")

            # 4. Arduino
            ard = readings.get('arduino', {})
            if ard:
                self._set_text('Temp1', f"{ard.get('temp0',0):.1f} °C"); self._set_text('Humi1', f"{ard.get('humi0',0):.1f} %")
                self._set_text('Temp2', f"{ard.get('temp1',0):.1f} °C"); self._set_text('Humi2', f"{ard.get('humi1',0):.1f} %")
                self._set_text('Dist', f"{ard.get('dist',0):.1f} cm")

            # 5. Radon
            self._set_text('Radon_Value', f"{self.dm.latest_radon_mu:.2f} Bq/m³")

            # 6. UPS
            ups = self.dm.latest_ups_status
            if ups:
                stat = ups.get('STATUS', 'N/A')
                col = "green" if "ONLINE" in stat else "orange"
                if 'UPS_Status' in self.labels:
                    self.labels['UPS_Status'].setText(f"Stat: <b style='color:{col}'>{stat}</b>")
                self._set_text('UPS_Charge', f"{ups.get('BCHARGE',0):.1f}%")
                self._set_text('UPS_TimeLeft', f"{ups.get('TIMELEFT',0):.1f}m")

            # 7. HV Temps
            boards = self.dm.latest_board_temps
            if 'HV_Board_Temps' in self.labels:
                parts = []
                for s, t in sorted(boards.items()):
                    if t != -1:
                        c = "red" if t>65 else "orange" if t>50 else "green"
                        parts.append(f"S{s}: <b style='color:{c}'>{t:.1f}°C</b>")
                self.labels['HV_Board_Temps'].setText(" | ".join(parts) if parts else "No Data")

            # 8. Fire & VOC
            fire_msg = self.dm.latest_fire_data.get('msg', 'Wait...')
            self._set_text('Fire_Status', f"{fire_msg}")
            voc_level = self.dm.latest_voc_data.get('conc', 0.0)
            self._set_text('VOC_Conc', f"{voc_level:.3f} ppm")

            # 9. Safety Light
            self._update_safety_light()

        finally:
            self.dm.lock.unlock()

    def _set_text(self, key, text):
        if key in self.labels:
            disp_name = key.replace("TH_O2_", "").replace("_", " ")
            if key == "B": disp_name = "|B|"
            if key == "Fire_Status": disp_name = "State"
            if key == "VOC_Conc": disp_name = "Level"
            if key == "HV_Board_Temps": disp_name = "Temps"
            
            self.labels[key].setText(f"{disp_name}: {text}")

    def _update_safety_light(self):
        fire = self.dm.latest_fire_data; voc = self.dm.latest_voc_data
        is_crit = fire.get('is_fire') or voc.get('conc', 0) > 50
        is_warn = fire.get('is_fault') or voc.get('conc', 0) > 10
        
        w_stat = self.safety_widgets['status']
        w_guide = self.safety_widgets['guide']
        w_frame = self.safety_widgets['frame']
        
        if is_crit:
            w_stat.setText("🚨 EMERGENCY"); w_stat.setStyleSheet("color: white; background: red; border:none;")
            w_guide.setText("EVACUATE!"); w_frame.setStyleSheet("background: #ffcccc; border: 3px solid red;")
        elif is_warn:
            w_stat.setText("⚠️ WARNING"); w_stat.setStyleSheet("color: black; background: yellow; border:none;")
            w_guide.setText("Check System"); w_frame.setStyleSheet("background: #fff3cd; border: 3px solid orange;")
        else:
            w_stat.setText("✅ SYSTEM\nNORMAL"); w_stat.setStyleSheet("color: #155724; background: transparent; border:none;")
            w_guide.setText("Monitoring\nActive"); w_frame.setStyleSheet("background: #d4edda; border: 2px solid #28a745;")