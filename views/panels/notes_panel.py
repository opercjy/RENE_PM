# views/panels/notes_panel.py

import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QTextEdit

class NotesPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        notes_group = QGroupBox("Notes")
        notes_layout = QVBoxLayout(notes_group)
        self.notes_edit = QTextEdit()
        notes_layout.addWidget(self.notes_edit)
        layout.addWidget(notes_group)
        
        notes_path = "notes.md"
        if os.path.exists(notes_path):
            with open(notes_path, "r", encoding="utf-8") as f:
                self.notes_edit.setMarkdown(f.read())
        else:
            self.notes_edit.setText("Project root folder에 notes.md 파일을 생성하세요.")