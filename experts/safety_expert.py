# experts/safety_expert.py (전체 덮어쓰기)

import os
import json
import logging
from PyQt6.QtCore import QObject, QTimer
from core.event_bus import global_bus

class SafetyExpert(QObject):
    """
    [안전 판단 룰 엔진 (Rule Engine)]
    """
    def __init__(self, config):
        super().__init__()
        self.config = config
        
        self.emergency_shutdown_triggered = False
        self.current_phase = "" # [최적화] 초기 1회 강제 렌더링을 위해 빈 문자열로 초기화
        
        self.fire_state = {'is_fire': False, 'is_fault': False, 'msg': 'Wait...'}
        self.voc_state = {'conc': 0.0, 'alarm': 0}

        voc_cfg = self.config.get('voc_detector', {})
        thresholds = voc_cfg.get('thresholds', {'warning_ppm': 10.0, 'critical_ppm': 50.0})
        self.voc_limit_warn = thresholds.get('warning_ppm', 10.0)
        self.voc_limit_crit = thresholds.get('critical_ppm', 50.0)

        self.sop_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sop.json")
        self.sop_data = self._load_sop_data()

        global_bus.sensor_data_updated.connect(self._evaluate_safety_conditions)
        QTimer.singleShot(500, self._determine_safety_phase)

    def _load_sop_data(self):
        default_sop = {
            "PHASE_1": {"title": "✅ PHASE 1: NORMAL", "items": ["Regular Monitoring Active", "Check Sensor Status Periodically"]},
            "PHASE_2": {"title": "⚠️ PHASE 2: WARNING", "items": ["Potential Hazard Detected", "Verify Ventilation & Check Equipment", "Prepare for Evacuation"]},
            "PHASE_3": {"title": "🚨 PHASE 3: EMERGENCY", "items": ["CRITICAL DANGER (Fire/Toxic Gas)", "EVACUATE IMMEDIATELY", "Trigger Fire Alarm & Call 119"]},
            "CONTACTS": [
                "📞 Fire Dept (소방서): 119",
                "📞 RENE Executive Manager (실험 책임자): 010-XXXX-XXXX (Dr. XXX)",
                "📞 KEPCO (한전 비상): 123"
            ]
        }
        if not os.path.exists(self.sop_file_path):
            try:
                with open(self.sop_file_path, 'w', encoding='utf-8') as f:
                    json.dump(default_sop, f, indent=4, ensure_ascii=False)
            except Exception as e:
                logging.error(f"Failed to create sop.json: {e}")
            return default_sop
        else:
            try:
                with open(self.sop_file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"Failed to read sop.json: {e}")
                return default_sop

    def _evaluate_safety_conditions(self, sensor_type, payload):
        data = payload.get('data', {})

        if sensor_type == 'ups_status':
            status = data.get('STATUS', 'N/A')
            timeleft = data.get('TIMELEFT', 0.0)
            shutdown_threshold_min = 15.0 

            if "BATT" in status and timeleft < shutdown_threshold_min and not self.emergency_shutdown_triggered:
                self.emergency_shutdown_triggered = True
                self._trigger_emergency_hv_shutdown()
                global_bus.system_log_message.emit("CRITICAL", "UPS 배터리 부족: 전체 HV 채널 비상 셧다운 개시.")
            
            elif "ONLINE" in status and self.emergency_shutdown_triggered:
                self.emergency_shutdown_triggered = False
                global_bus.system_log_message.emit("INFO", "AC 전원 복구: 비상 셧다운 플래그 초기화.")

        elif sensor_type == 'fire_status':
            self.fire_state = data
            self._determine_safety_phase()
            
        elif sensor_type == 'voc_status':
            self.voc_state = data
            self._determine_safety_phase()

    def _determine_safety_phase(self):
        is_fire = self.fire_state.get('is_fire', False)
        is_fault = self.fire_state.get('is_fault', False)
        
        voc_conc = self.voc_state.get('conc', 0.0)
        voc_alarm = self.voc_state.get('alarm', 0)
        
        voc_high = voc_conc >= self.voc_limit_crit or voc_alarm > 0
        voc_low = voc_conc >= self.voc_limit_warn

        new_phase = "NORMAL"
        if is_fire or voc_high: new_phase = "EMERGENCY"
        elif is_fault or voc_low: new_phase = "WARNING"

        # [핵심 최적화: Event Loop 방어]
        # 상태 천이(State Transition)가 발생했을 때만 무거운 HTML을 파싱하고 시그널을 방출합니다.
        # 이를 통해 1초 주기 시계 멈춤(Freezing) 현상을 완벽히 차단합니다.
        if self.current_phase != new_phase:
            self.current_phase = new_phase
            html_msg = self._generate_sop_html(new_phase)
            global_bus.safety_status_changed.emit(new_phase, html_msg)

    def _trigger_emergency_hv_shutdown(self):
        crate_map = self.config.get('caen_hv', {}).get('crate_map', {})
        for slot_str, board_info in crate_map.items():
            slot = int(slot_str)
            channels = list(range(board_info.get('channels', 0)))
            command = {'type': 'set_power', 'slot': slot, 'channels': channels, 'value': False}
            global_bus.cmd_hv_control.emit(command)

    def _generate_sop_html(self, current_phase):
        style_dim = "opacity: 0.3; color: #999;"
        style_act_norm = "opacity: 1.0; color: #155724; font-weight: bold; font-size: 11pt; border-left: 5px solid #28a745; padding: 8px; background-color: #e8f5e9;"
        style_act_warn = "opacity: 1.0; color: #856404; font-weight: bold; font-size: 11pt; border-left: 5px solid #ffc107; padding: 8px; background-color: #fff3cd;"
        style_act_emer = "opacity: 1.0; color: #721c24; font-weight: bold; font-size: 12pt; border-left: 5px solid #dc3545; padding: 10px; background-color: #f8d7da;"

        s_norm = style_act_norm if current_phase == "NORMAL" else style_dim
        s_warn = style_act_warn if current_phase == "WARNING" else style_dim
        s_emer = style_act_emer if current_phase == "EMERGENCY" else style_dim

        p1_items = "<br>".join([f"- {item}" for item in self.sop_data["PHASE_1"]["items"]])
        p2_items = "<br>".join([f"- {item}" for item in self.sop_data["PHASE_2"]["items"]])
        p3_items = "<br>".join([f"- {item}" for item in self.sop_data["PHASE_3"]["items"]])
        contacts = "<br>".join([f"&nbsp;&nbsp;{item}" for item in self.sop_data["CONTACTS"]])

        return f"""
        <h3 style="font-family: Arial; margin-bottom: 5px; color: #333;">Current Operating Phase</h3>
        
        <div style='{s_norm} margin-bottom: 8px; font-family: Arial;'>
            {self.sop_data["PHASE_1"]["title"]}<br>
            <span style="font-weight: normal; font-size: 10pt; color: #444;">{p1_items}</span>
        </div>
        
        <div style='{s_warn} margin-bottom: 8px; font-family: Arial;'>
            {self.sop_data["PHASE_2"]["title"]}<br>
            <span style="font-weight: normal; font-size: 10pt; color: #444;">{p2_items}</span>
        </div>
        
        <div style='{s_emer} margin-bottom: 8px; font-family: Arial;'>
            {self.sop_data["PHASE_3"]["title"]}<br>
            <span style="font-weight: normal; font-size: 11pt; color: #444;">{p3_items}</span>
        </div>
        
        <hr style="border: 0; border-top: 1px solid #ccc; margin: 15px 0;">
        <div style='font-size: 11pt; color: #222; font-family: Arial; background-color: #f8f9fa; padding: 10px; border-radius: 5px; border: 1px solid #ddd;'>
            <b>🚨 Emergency Contacts (비상 연락망)</b><br><br>
            {contacts}
        </div>
        """