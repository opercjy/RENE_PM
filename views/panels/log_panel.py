# views/panels/log_panel.py

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QLabel
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtCore import pyqtSlot
from core.event_bus import global_bus

class LogPanel(QWidget):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self._init_ui()
        global_bus.system_log_message.connect(self._update_log_viewer)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        self.log_viewer_text = QTextEdit()
        self.log_viewer_text.setReadOnly(True)
        self.log_viewer_text.setFont(QFont("Consolas", 10))
        layout.addWidget(QLabel("System Event Log (Real-time)"))
        layout.addWidget(self.log_viewer_text)

    @pyqtSlot(str, str)
    def _update_log_viewer(self, level, message):
        max_lines = self.config.get('gui', {}).get('max_log_lines', 2000)
        if self.log_viewer_text.document().blockCount() > max_lines:
            cursor = self.log_viewer_text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()
        
        color_map = {"INFO": "blue", "SUCCESS": "green", "WARNING": "orange", "ERROR": "red", "CRITICAL": "darkred"}
        color = color_map.get(level, "black")
        self.log_viewer_text.append(f"<span style='color:{color};'>[{level}] {message.strip()}</span>")