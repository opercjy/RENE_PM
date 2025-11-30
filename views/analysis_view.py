from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, QComboBox, 
                             QLabel, QSpinBox, QCheckBox, QDateEdit, QPushButton, QMessageBox)
from PyQt5.QtCore import Qt, QDate, pyqtSlot
import pandas as pd
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from workers.analysis_worker import AnalysisWorker

class AnalysisView(QWidget):
    def __init__(self, config, data_manager, parent=None):
        super().__init__(parent)
        self.config = config
        self.dm = data_manager
        self.last_analysis_df = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # Control Panel
        control_panel = QFrame(); control_panel.setFrameShape(QFrame.StyledPanel)
        control_layout = QHBoxLayout(control_panel); control_layout.setAlignment(Qt.AlignLeft)
        
        self.combo_mode = QComboBox(); self.combo_mode.addItems(["Time Series", "Correlation"])
        self.combo_mode.currentTextChanged.connect(self._on_mode_changed)
        
        # Time Series Widgets
        self.widget_ts = QWidget(); layout_ts = QHBoxLayout(self.widget_ts); layout_ts.setContentsMargins(0,0,0,0)
        self.combo_data = QComboBox()
        self.map_queries = {
            "LS Temperature": "SELECT `datetime`, `RTD_1`, `RTD_2` FROM LS_DATA", 
            "LS Level": "SELECT `datetime`, `DIST_1`, `DIST_2` FROM LS_DATA",
            "Magnetometer": "SELECT `datetime`, `Bx`, `By`, `Bz`, `B_mag` FROM MAGNETOMETER_DATA", 
            "Radon": "SELECT `datetime`, `mu` FROM RADON_DATA",
            "TH/O2": "SELECT `datetime`, `temperature`, `humidity`, `oxygen` FROM TH_O2_DATA", 
            "Arduino": "SELECT `datetime`, `analog_1`, `analog_2`, `analog_3`, `analog_4`, `analog_5` FROM ARDUINO_DATA",
            "UPS": "SELECT `datetime`, `linev`, `bcharge`, `timeleft` FROM UPS_DATA", 
            "HV Voltage": "HV_QUERY", "HV Current": "HV_QUERY", "HV Temp": "HV_TEMP_QUERY",
            "PDU Power": "PDU_QUERY", "PDU Current": "PDU_QUERY", "PDU Energy": "PDU_QUERY"
        }
        self.combo_data.addItems(self.map_queries.keys())
        self.combo_data.currentTextChanged.connect(self._on_data_changed)
        
        # Date Pickers
        self.date_start = QDateEdit(QDate.currentDate().addDays(-7)); self.date_start.setCalendarPopup(True)
        self.date_end = QDateEdit(QDate.currentDate()); self.date_end.setCalendarPopup(True)
        
        layout_ts.addWidget(QLabel("Data:")); layout_ts.addWidget(self.combo_data)
        layout_ts.addWidget(QLabel("Start:")); layout_ts.addWidget(self.date_start)
        layout_ts.addWidget(QLabel("End:")); layout_ts.addWidget(self.date_end)
        
        # Correlation Widgets (Simple setup)
        self.widget_corr = QWidget(); layout_corr = QHBoxLayout(self.widget_corr); layout_corr.setContentsMargins(0,0,0,0)
        self.widget_corr.hide()
        
        # Buttons
        self.btn_plot = QPushButton("Plot"); self.btn_plot.clicked.connect(self._run_analysis)
        self.btn_export = QPushButton("Export CSV"); self.btn_export.clicked.connect(self._export_csv)
        
        control_layout.addWidget(QLabel("Mode:")); control_layout.addWidget(self.combo_mode)
        control_layout.addWidget(self.widget_ts); control_layout.addWidget(self.widget_corr)
        control_layout.addStretch(1)
        control_layout.addWidget(self.btn_plot); control_layout.addWidget(self.btn_export)
        
        # Canvas
        self.canvas = FigureCanvas(Figure(figsize=(10, 6)))
        
        layout.addWidget(control_panel)
        layout.addWidget(self.canvas)

    def _on_mode_changed(self, mode):
        self.widget_ts.setVisible(mode == "Time Series")
        self.widget_corr.setVisible(mode == "Correlation")

    def _on_data_changed(self, text):
        # HV/PDU 관련 추가 옵션 UI 표시 로직은 간소화를 위해 생략하거나 필요시 추가
        pass

    def _run_analysis(self):
        if not self.dm.db_pool: return
        self.btn_plot.setEnabled(False); self.btn_plot.setText("Loading...")
        
        # 쿼리 생성 (간소화된 예시)
        target = self.combo_data.currentText()
        query_template = self.map_queries.get(target, "")
        
        s_date = self.date_start.date().toString("yyyy-MM-dd 00:00:00")
        e_date = self.date_end.date().toString("yyyy-MM-dd 23:59:59")
        
        queries, params = [], []
        
        # 단순 쿼리 처리
        if "WHERE" not in query_template and "HV_QUERY" not in query_template:
            queries.append(f"{query_template} WHERE `datetime` BETWEEN ? AND ?")
            params.append([s_date, e_date])
        
        # Worker 실행
        self.worker = AnalysisWorker(self.dm.db_pool, self.config['database'], queries, params)
        self.worker.analysis_complete.connect(self._on_data_ready)
        self.worker.finished.connect(lambda: [self.btn_plot.setEnabled(True), self.btn_plot.setText("Plot")])
        self.worker.start()

    def _on_data_ready(self, dfs):
        if not dfs or dfs[0].empty: return
        self.last_analysis_df = dfs[0]
        df = dfs[0]
        df['datetime'] = pd.to_datetime(df['datetime'])
        df.set_index('datetime', inplace=True)
        
        self.canvas.figure.clear()
        ax = self.canvas.figure.add_subplot(111)
        df.plot(ax=ax)
        ax.grid(True)
        self.canvas.draw()

    def _export_csv(self):
        if self.last_analysis_df is not None:
            self.last_analysis_df.to_csv("exported_data.csv")
            QMessageBox.information(self, "Export", "Saved to exported_data.csv")