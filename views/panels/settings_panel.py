# views/panels/settings_panel.py

import json
import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGroupBox, QGridLayout, 
                             QCheckBox, QPushButton, QMessageBox, QLabel)
from PyQt6.QtCore import Qt
from core.event_bus import global_bus

class SettingsPanel(QWidget):
    def __init__(self, config, config_file_path="config_v2.json"):
        super().__init__()
        self.config = config
        self.config_file_path = config_file_path
        self.checkboxes = {}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # 하드웨어 워커 토글 그룹
        hw_group = QGroupBox("Hardware Module Configuration (Hot-Swap)")
        hw_layout = QGridLayout(hw_group)
        
        # 관리 대상 워커 목록
        workers = {
            'caen_hv': 'CAEN HV Mainframe',
            'netio_pdu': 'NETIO PowerPDU',
            'daq': 'NI-cDAQ (Temperature/Level)',
            'th_o2': 'TH/O2 Sensor (Modbus)',
            'radon': 'Radon Sensor (Serial)',
            'magnetometer': 'Magnetometer (PyVISA)',
            'arduino': 'Arduino Sub-sensors',
            'fire_detector': 'FS24X Plus (Fire)',
            'voc_detector': 'RAEGuard2 (VOC)',
            'ups': 'APC UPS Monitor',
            'database': 'MariaDB Logging'
        }
        
        row, col = 0, 0
        for key, display_name in workers.items():
            chk = QCheckBox(display_name)
            # 현재 메모리(CONFIG)의 상태를 읽어와 초기값 설정
            is_enabled = self.config.get(key, {}).get('enabled', False)
            chk.setChecked(is_enabled)
            self.checkboxes[key] = chk
            
            hw_layout.addWidget(chk, row, col)
            col += 1
            if col > 2:
                col = 0
                row += 1

        # 저장 및 적용 버튼
        btn_layout = QGridLayout()
        btn_apply = QPushButton("Save to JSON & Apply Dynamically")
        btn_apply.setStyleSheet("background-color: #27AE60; color: white; font-weight: bold; padding: 10px;")
        btn_apply.clicked.connect(self._save_and_apply)
        
        layout.addWidget(hw_group)
        layout.addWidget(btn_apply)
        layout.addStretch(1)

    def _save_and_apply(self):
        reply = QMessageBox.question(
            self, 'Confirm', 
            "설정을 JSON 파일에 덮어쓰고 시스템에 즉시 반영하시겠습니까?\n체크 해제된 하드웨어는 즉시 통신이 차단됩니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 1. 체크박스 상태를 읽어와 메모리의 config 갱신 및 EventBus로 핫스왑 명령 하달
            for key, chk in self.checkboxes.items():
                new_state = chk.isChecked()
                old_state = self.config.get(key, {}).get('enabled', False)
                
                # 상태가 변경된 경우에만 처리
                if new_state != old_state:
                    if key not in self.config:
                        self.config[key] = {}
                    self.config[key]['enabled'] = new_state
                    
                    # DB 워커는 재시작 로직이 복잡하므로 런타임 핫스왑 대상에서 제외 또는 별도 처리
                    if key != 'database':
                        global_bus.cmd_toggle_worker.emit(key, new_state)

            # 2. 변경된 딕셔너리를 물리적 JSON 파일에 Write
            try:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                # 루트 디렉터리로 경로 보정
                root_dir = os.path.abspath(os.path.join(script_dir, "..", ".."))
                target_path = os.path.join(root_dir, self.config_file_path)
                
                with open(target_path, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=4, ensure_ascii=False)
                    
                global_bus.system_log_message.emit("SUCCESS", f"설정이 {self.config_file_path}에 성공적으로 저장되었습니다.")
                QMessageBox.information(self, "Applied", "설정이 저장되고 스레드 재배치가 완료되었습니다.")
                
            except Exception as e:
                global_bus.system_log_message.emit("ERROR", f"JSON 저장 실패: {e}")
                QMessageBox.critical(self, "Error", f"파일 저장 중 오류가 발생했습니다.\n{e}")