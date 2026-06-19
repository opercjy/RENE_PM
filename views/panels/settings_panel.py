# views/panels/settings_panel.py (전체 덮어쓰기)

import json
import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QGridLayout, 
                             QCheckBox, QPushButton, QMessageBox, QTextEdit, QLabel, QSplitter)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from core.event_bus import global_bus

class SettingsPanel(QWidget):
    def __init__(self, config, config_file_path="config_v3.json"):
        super().__init__()
        self.config = config
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.abspath(os.path.join(script_dir, "..", ".."))
        self.config_file_path = os.path.join(root_dir, config_file_path)
        if not os.path.exists(self.config_file_path):
            self.config_file_path = os.path.join(root_dir, "config_v2.json")
            
        self.checkboxes = {}
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # [상단] 하드웨어 모듈 토글 그룹 (핫스왑)
        hw_widget = QWidget()
        hw_layout = QVBoxLayout(hw_widget)
        hw_layout.setContentsMargins(0,0,0,0)
        
        hw_group = QGroupBox("🔌 Quick Hot-Swap (Runtime Module Control)")
        grid_layout = QGridLayout(hw_group)
        
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
            is_enabled = self.config.get(key, {}).get('enabled', False)
            chk.setChecked(is_enabled)
            
            # 체크박스 변경시 하단 JSON 텍스트 에디터 동기화
            chk.stateChanged.connect(self._sync_checkbox_to_json)
            self.checkboxes[key] = chk
            grid_layout.addWidget(chk, row, col)
            col += 1
            if col > 2:
                col = 0
                row += 1

        hw_layout.addWidget(hw_group)
        splitter.addWidget(hw_widget)
        
        # [하단] JSON 고급 편집기
        json_widget = QWidget()
        json_layout = QVBoxLayout(json_widget)
        json_layout.setContentsMargins(0,0,0,0)
        
        json_group = QGroupBox("⚙️ Advanced Configuration Editor (JSON)")
        j_layout = QVBoxLayout(json_group)
        
        self.json_editor = QTextEdit()
        self.json_editor.setFont(QFont("Consolas", 11))
        self.json_editor.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        
        # 현재 config를 예쁜 들여쓰기 형태의 문자열로 변환하여 삽입
        self.json_editor.setPlainText(json.dumps(self.config, indent=4, ensure_ascii=False))
        
        info_lbl = QLabel("⚠️ 경고: JSON 형식이 틀리면 시스템이 오작동할 수 있습니다. (IP, 포트, 임계값 등 직접 수정 가능)")
        info_lbl.setStyleSheet("color: #E67E22; font-weight: bold;")
        j_layout.addWidget(info_lbl)
        j_layout.addWidget(self.json_editor)
        
        json_layout.addWidget(json_group)
        splitter.addWidget(json_widget)
        
        splitter.setSizes([200, 600])
        main_layout.addWidget(splitter)
        
        # 버튼 영역
        btn_layout = QHBoxLayout()
        
        btn_format = QPushButton("🧹 Format & Check JSON")
        btn_format.setStyleSheet("background-color: #95A5A6; color: white; font-weight: bold; padding: 10px;")
        btn_format.clicked.connect(self._format_json)
        
        btn_apply = QPushButton("💾 Validate, Save & Apply")
        btn_apply.setStyleSheet("background-color: #27AE60; color: white; font-weight: bold; padding: 10px; font-size: 13pt;")
        btn_apply.clicked.connect(self._save_and_apply)
        
        btn_layout.addWidget(btn_format, 1)
        btn_layout.addWidget(btn_apply, 3)
        
        main_layout.addLayout(btn_layout)

    def _sync_checkbox_to_json(self):
        try:
            current_json = json.loads(self.json_editor.toPlainText())
            for key, chk in self.checkboxes.items():
                if key not in current_json:
                    current_json[key] = {}
                current_json[key]['enabled'] = chk.isChecked()
            
            # 사용자 타이핑을 방해하지 않도록 커서 위치 복원 처리 등은 생략 (단순 동기화)
            self.json_editor.setPlainText(json.dumps(current_json, indent=4, ensure_ascii=False))
        except json.JSONDecodeError:
            pass # 타이핑 도중 문법이 깨진 상태면 동기화 무시

    def _format_json(self):
        """에디터 내용 문법 검사 및 포맷팅"""
        raw_json = self.json_editor.toPlainText()
        try:
            parsed = json.loads(raw_json)
            self.json_editor.setPlainText(json.dumps(parsed, indent=4, ensure_ascii=False))
            global_bus.system_log_message.emit("INFO", "JSON 포맷 검증 성공.")
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "JSON Format Error", f"JSON 구문 오류가 있습니다.\n{e}")

    def _save_and_apply(self):
        raw_json = self.json_editor.toPlainText()
        
        # 1. 텍스트 에디터의 JSON 유효성(문법) 검사
        try:
            new_config = json.loads(raw_json)
        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "JSON Parse Error", f"JSON 파싱 실패. 문법 오류를 확인하세요.\n{e}")
            return
        
        reply = QMessageBox.question(
            self, 'Confirm Settings Update', 
            "설정을 저장하고 시스템에 반영하시겠습니까?\n체크 해제된 모듈은 즉시 워커 스레드가 반환되며, 고급 설정값(임계치 등)이 갱신됩니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 2. 핫스왑 토글 수행 (새 설정 기준)
            for key, chk in self.checkboxes.items():
                is_enabled_in_json = new_config.get(key, {}).get('enabled', False)
                
                # 에디터에서 직접 enabled를 바꾼 경우 상단의 체크박스 UI도 동기화
                if chk.isChecked() != is_enabled_in_json:
                    chk.blockSignals(True)
                    chk.setChecked(is_enabled_in_json)
                    chk.blockSignals(False)

                old_state = self.config.get(key, {}).get('enabled', False)
                if is_enabled_in_json != old_state:
                    if key != 'database':
                        global_bus.cmd_toggle_worker.emit(key, is_enabled_in_json)

            # 3. 메인 메모리 변수 갱신
            self.config.clear()
            self.config.update(new_config)
            
            # 4. 물리적 JSON 파일 Write
            try:
                with open(self.config_file_path, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=4, ensure_ascii=False)
                    
                global_bus.system_log_message.emit("SUCCESS", f"고급 설정이 {os.path.basename(self.config_file_path)}에 성공적으로 저장되었습니다.")
                QMessageBox.information(self, "Applied", "설정이 성공적으로 덮어씌워졌으며 시스템에 반영되었습니다.")
            except Exception as e:
                global_bus.system_log_message.emit("ERROR", f"Config Save Failed: {e}")
                QMessageBox.critical(self, "Error", f"설정 파일을 저장하는 중 오류가 발생했습니다.\n{e}")