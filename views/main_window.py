# views/main_window.py (전체 덮어쓰기)

from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QTabWidget, QLabel, QStatusBar)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

from views.panels.safety_panel import SafetyPanel
from views.panels.pdu_panel import PDUPanel
from views.panels.hv_panel import HVPanel
from views.panels.env_panel import EnvPanel
from views.panels.log_panel import LogPanel
from views.panels.notes_panel import NotesPanel
from views.panels.analysis_panel import AnalysisPanel
from views.panels.guide_panel import GuidePanel
from views.panels.hv_graph_panel import HVGraphPanel
from views.panels.settings_panel import SettingsPanel

from views.components.dashboard_panel import DashboardPanel
from views.components.hv_grid_panel import HVGridPanel

class MainWindow(QMainWindow):
    def __init__(self, config, state_store, db_pool):
        super().__init__()
        self.config = config
        self.state_store = state_store
        self.db_pool = db_pool
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("RENE-PM v3.0 Decentralized")
        self.setGeometry(50, 50, 1920, 1080)
        
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        
        title_label = QLabel("RENE-PM Integrated Monitoring System v3.0")
        title_label.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)
        
        top_panel = QWidget()
        top_layout = QHBoxLayout(top_panel)
        
        self.tab_widget = QTabWidget()
        
        # [수정] SafetyPanel에 state_store 의존성 주입
        self.safety_panel = SafetyPanel(self.state_store)
        self.tab_widget.addTab(self.safety_panel, "🛡️ Safety")
        
        if self.config.get('caen_hv', {}).get("enabled"):
            crate_map = self.config['caen_hv'].get('crate_map', {})
            self.hv_panel = HVPanel(list(crate_map.keys()))
            self.tab_widget.addTab(self.hv_panel, "🎛️ HV Control")
            
        self.env_panel = EnvPanel(self.state_store)
        self.tab_widget.addTab(self.env_panel, "🌡️ Env Graphs")
        
        self.analysis_panel = AnalysisPanel(self.config, self.db_pool)
        self.tab_widget.addTab(self.analysis_panel, "🔍 Data History")
        
        if self.config.get('caen_hv', {}).get("enabled"):
            for slot_str, board in self.config['caen_hv'].get('crate_map', {}).items():
                self.tab_widget.addTab(HVGraphPanel(int(slot_str), board.get('channels', 0), self.state_store), f"📈 HV S{slot_str}")
        
        self.guide_panel = GuidePanel(self.config)
        self.tab_widget.addTab(self.guide_panel, "🗺️ Guide")
        
        self.notes_panel = NotesPanel()
        self.tab_widget.addTab(self.notes_panel, "📝 Notes")

        self.log_panel = LogPanel(self.config)
        self.tab_widget.addTab(self.log_panel, "📜 Logs")
        
        if self.config.get('netio_pdu', {}).get("enabled"):
            self.pdu_panel = PDUPanel()
            self.tab_widget.addTab(self.pdu_panel, "⚡ PDU Control")
            
        self.settings_panel = SettingsPanel(self.config)
        self.tab_widget.addTab(self.settings_panel, "⚙️ Settings")
            
        top_layout.addWidget(self.tab_widget, 7) 
        
        if self.config.get('caen_hv', {}).get("enabled"):
            self.hv_grid_panel = HVGridPanel(self.config)
            top_layout.addWidget(self.hv_grid_panel, 3) 
        else:
            top_layout.addWidget(QLabel("CAEN HV System Disabled"), 3)
            
        main_layout.addWidget(top_panel, 8) 
        
        self.dashboard_panel = DashboardPanel(self.config)
        main_layout.addWidget(self.dashboard_panel, 2)
        
        shifter_text = self.config.get("shifter_name", "Unknown Shifter")
        self.shifter_label = QLabel(f" Shifter: {shifter_text} ")
        self.status_bar.addPermanentWidget(self.shifter_label)