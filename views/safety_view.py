from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, 
                             QFormLayout, QLabel, QTextEdit)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt
import pyqtgraph as pg

class SafetyView(QWidget):
    def __init__(self, config, data_manager, parent=None):
        super().__init__(parent)
        self.config = config
        self.dm = data_manager
        self.labels = {}
        self.curves = {}
        
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        
        # --- Left Column: Info & SOP (Ratio 4) ---
        left_layout = QVBoxLayout()
        
        # 1. Detailed Info Group
        info_group = QGroupBox("📋 Detailed Sensor Readings")
        info_layout = QFormLayout(info_group)
        
        self.labels['fire'] = QLabel("N/A")
        self.labels['voc_conc'] = QLabel("0.000 ppm")
        self.labels['voc_alarm'] = QLabel("Normal")
        self.labels['radon'] = QLabel("0.00 Bq/m³")
        
        font_val = QFont("Arial", 12, QFont.Bold)
        for l in self.labels.values():
            l.setFont(font_val)
            
        info_layout.addRow("🔥 Flame Level:", self.labels['fire'])
        info_layout.addRow("🧪 VOC Concentration:", self.labels['voc_conc'])
        info_layout.addRow("🔔 VOC Alarm Status:", self.labels['voc_alarm'])
        info_layout.addRow("☢️ Radon Level:", self.labels['radon'])
        
        # 2. SOP Guide Group
        sop_group = QGroupBox("📖 Standard Operating Procedure (SOP)")
        sop_layout = QVBoxLayout(sop_group)
        self.sop_text = QTextEdit()
        self.sop_text.setReadOnly(True)
        self.sop_text.setHtml("<h3>⏳ Initializing...</h3>")
        sop_layout.addWidget(self.sop_text)

        left_layout.addWidget(info_group, 4)
        left_layout.addWidget(sop_group, 6)
        
        # --- Right Column: Graphs (Ratio 6) ---
        graph_group = QGroupBox("📈 Safety Trends Analysis")
        graph_layout = QVBoxLayout(graph_group)
        
        # VOC Graph
        self.plot_voc = pg.PlotWidget(title="🧪 VOC Concentration (ppm)")
        self.plot_voc.setBackground('w')
        self.plot_voc.showGrid(x=True, y=True, alpha=0.3)
        self.plot_voc.setAxisItems({'bottom': pg.DateAxisItem(orientation='bottom')})
        self.curves['voc'] = self.plot_voc.plot(pen=pg.mkPen('b', width=2), name="VOC")
        
        # Flame Graph
        self.plot_flame = pg.PlotWidget(title="🔥 Flame Sensor Level (Analog)")
        self.plot_flame.setBackground('w')
        self.plot_flame.showGrid(x=True, y=True, alpha=0.3)
        self.plot_flame.setAxisItems({'bottom': pg.DateAxisItem(orientation='bottom')})
        self.curves['flame'] = self.plot_flame.plot(pen=pg.mkPen('r', width=2), name="Flame")
        
        graph_layout.addWidget(self.plot_voc)
        graph_layout.addWidget(self.plot_flame)

        # Add columns to main layout
        layout.addLayout(left_layout, 4)
        layout.addWidget(graph_group, 6)

    def update_ui(self):
        """메인 윈도우 타이머에 의해 주기적으로 호출됨"""
        # DataManager에서 데이터 읽기 (Read Lock)
        self.dm.lock.lockForRead()
        try:
            fire_data = self.dm.latest_fire_data
            voc_data = self.dm.latest_voc_data
            radon_mu = self.dm.latest_radon_mu
            
            # 그래프 데이터 참조 (Numpy View)
            voc_hist = self.dm.voc_data
            flame_hist = self.dm.flame_data
        finally:
            self.dm.lock.unlock()

        # 1. 텍스트 라벨 업데이트
        fire_msg = fire_data.get('msg', '-')
        fire_val = fire_data.get('status_code', 0)
        self.labels['fire'].setText(f"{fire_msg} (Lv: {fire_val})")
        
        voc_conc = voc_data.get('conc', 0.0)
        self.labels['voc_conc'].setText(f"{voc_conc:.3f} ppm")
        
        voc_alarm = voc_data.get('alarm', 0)
        self.labels['voc_alarm'].setText("ALARM" if voc_alarm > 0 else "Normal")
        
        self.labels['radon'].setText(f"{radon_mu:.2f} Bq/m³")

        # 2. SOP HTML 업데이트
        self._update_sop(fire_data, voc_data)
        
        # 3. 그래프 업데이트 (연결된 선으로 표시)
        # DataManager의 데이터는 [timestamp, value] 형태
        self.curves['voc'].setData(x=voc_hist[:,0], y=voc_hist[:,1], connect='finite')
        self.curves['flame'].setData(x=flame_hist[:,0], y=flame_hist[:,1], connect='finite')

    def _update_sop(self, fire_data, voc_data):
        # Config에서 임계값 가져오기
        voc_cfg = self.config.get('voc_detector', {})
        thresholds = voc_cfg.get('thresholds', {'warning_ppm': 10.0, 'critical_ppm': 50.0})
        
        limit_warn = thresholds.get('warning_ppm', 10.0)
        limit_crit = thresholds.get('critical_ppm', 50.0)
        
        is_fire = fire_data.get('is_fire', False)
        is_fault = fire_data.get('is_fault', False)
        voc_conc = voc_data.get('conc', 0.0)
        voc_alarm = voc_data.get('alarm', 0)

        # 상태 결정
        current_phase = "NORMAL"
        if is_fire or voc_conc >= limit_crit or voc_alarm > 0:
            current_phase = "EMERGENCY"
        elif is_fault or voc_conc >= limit_warn:
            current_phase = "WARNING"
            
        # HTML 생성
        self.sop_text.setHtml(self._generate_sop_html(current_phase))

    def _generate_sop_html(self, current_phase):
        style_dim = "opacity: 0.3; color: #999;"
        style_act_norm = "opacity: 1.0; color: green; font-weight: bold; font-size: 14px; border: 2px solid green; padding: 10px; background-color: #e8f5e9;"
        style_act_warn = "opacity: 1.0; color: #856404; font-weight: bold; font-size: 14px; border: 2px solid orange; padding: 10px; background-color: #fff3cd;"
        style_act_emer = "opacity: 1.0; color: white; font-weight: bold; font-size: 16px; border: 3px solid red; padding: 15px; background-color: #dc3545;"

        s_norm = style_act_norm if current_phase == "NORMAL" else style_dim
        s_warn = style_act_warn if current_phase == "WARNING" else style_dim
        s_emer = style_act_emer if current_phase == "EMERGENCY" else style_dim

        return f"""
        <h3>Current Operating Phase: {current_phase}</h3>
        
        <div style='{s_norm}'>
            ✅ <b>PHASE 1: NORMAL</b><br>
            - Regular Monitoring Active<br>
            - Check Sensor Status Periodically
        </div>
        <br>
        <div style='{s_warn}'>
            ⚠️ <b>PHASE 2: WARNING</b><br>
            - Potential Hazard Detected<br>
            - Verify Ventilation & Check Equipment<br>
            - Prepare for Evacuation
        </div>
        <br>
        <div style='{s_emer}'>
            🚨 <b>PHASE 3: EMERGENCY</b><br>
            - CRITICAL DANGER (Fire/Toxic Gas)<br>
            - <b>EVACUATE IMMEDIATELY</b><br>
            - Trigger Fire Alarm & Call 119
        </div>
        <br>
        <hr>
        <div style='font-size: 14px; color: #333;'>
            <b>📞 Emergency Contacts (비상 연락망)</b><br>
            - <b>Fire Dept (소방서):</b> 119<br>
            - <b>Lab Manager (실험 책임자):</b> 010-XXXX-XXXX (Dr. Choi)<br>
            - <b>KEPCO (한전 비상):</b> 123<br>
            - <b>Safety Officer (안전 관리자):</b> 010-YYYY-YYYY
        </div>
        """