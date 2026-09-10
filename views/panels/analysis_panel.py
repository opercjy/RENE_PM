# views/panels/analysis_panel.py (전체 덮어쓰기)

import time
import pandas as pd
import numpy as np
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, 
                             QComboBox, QSpinBox, QCheckBox, QLabel, QPushButton, 
                             QDateEdit, QMessageBox, QFileDialog)
from PyQt6.QtCore import Qt, QDate
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from workers.analysis_worker import AnalysisWorker
from core.event_bus import global_bus

class AnalysisPanel(QWidget):
    def __init__(self, config, db_pool):
        super().__init__()
        self.config = config
        self.db_pool = db_pool
        self.last_analysis_df = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        control_panel = QFrame()
        control_panel.setFrameShape(QFrame.Shape.StyledPanel)
        control_layout = QHBoxLayout(control_panel)
        control_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.analysis_mode_combo = QComboBox()
        self.analysis_mode_combo.addItems(["Time Series", "Correlation"])
        
        self.timeseries_widget = QWidget()
        ts_layout = QHBoxLayout(self.timeseries_widget)
        ts_layout.setContentsMargins(0,0,0,0)
        
        self.analysis_combo = QComboBox()
        # [핵심 수정] FIRE_DATA 및 VOC_DATA SQL 쿼리 라우팅 추가 완료
        self.analysis_map = {
            "LS Temperature (C)": "SELECT `datetime`, `RTD_1`, `RTD_2` FROM LS_DATA", 
            "LS Level (mm)": "SELECT `datetime`, `DIST_1`, `DIST_2` FROM LS_DATA",
            "Magnetometer (mG)": "SELECT `datetime`, `Bx`, `By`, `Bz`, `B_mag` FROM MAGNETOMETER_DATA", 
            "Radon (Bq/m3)": "SELECT `datetime`, `mu` FROM RADON_DATA",
            "TH/O2 Sensor": "SELECT `datetime`, `temperature`, `humidity`, `oxygen` FROM TH_O2_DATA", 
            "Arduino Sensor": "SELECT `datetime`, `analog_1`, `analog_2`, `analog_3`, `analog_4`, `analog_5` FROM ARDUINO_DATA",
            "UPS Status": "SELECT `datetime`, `linev`, `bcharge`, `timeleft` FROM UPS_DATA", 
            "Flame Sensor (Lv)": "SELECT `datetime`, `status_code` AS `Flame_Level`, `temperature` AS `Temp_C` FROM FIRE_DATA",
            "VOC Concentration (ppm)": "SELECT `datetime`, `concentration` AS `VOC_ppm` FROM VOC_DATA",
            "HV Voltage (VMon)": "HV_QUERY", 
            "HV Current (IMon)": "HV_QUERY", 
            "HV Board Temperature (C)": "HV_TEMP_QUERY",
            "PDU Power (W)": "PDU_QUERY", 
            "PDU Current (mA)": "PDU_QUERY", 
            "PDU Energy (Wh)": "PDU_QUERY"
        }
        self.analysis_combo.addItems(self.analysis_map.keys())
        
        self.hv_specific_controls = QWidget()
        hv_spec_layout = QHBoxLayout(self.hv_specific_controls)
        hv_spec_layout.setContentsMargins(0,0,0,0)
        self.hv_slot_combo = QComboBox()
        if self.config.get('caen_hv', {}).get("enabled") and self.config.get('caen_hv', {}).get('crate_map'):
            self.hv_slot_combo.addItems(self.config['caen_hv']['crate_map'].keys())
        self.hv_ch_start = QSpinBox()
        self.hv_ch_start.setRange(0, 99)
        self.hv_ch_end = QSpinBox()
        self.hv_ch_end.setRange(0, 99)
        self.analysis_single_channel_checkbox = QCheckBox("Single")
        self.analysis_single_channel_checkbox.setChecked(True)
        
        hv_spec_layout.addWidget(QLabel("Slot:")); hv_spec_layout.addWidget(self.hv_slot_combo)
        hv_spec_layout.addWidget(QLabel("Ch Start:")); hv_spec_layout.addWidget(self.hv_ch_start)
        hv_spec_layout.addWidget(QLabel("Ch End:")); hv_spec_layout.addWidget(self.hv_ch_end)
        hv_spec_layout.addWidget(self.analysis_single_channel_checkbox)
        self.hv_specific_controls.hide()

        self.board_temp_controls = QWidget()
        board_temp_layout = QHBoxLayout(self.board_temp_controls)
        board_temp_layout.setContentsMargins(0,0,0,0)
        board_temp_layout.addWidget(QLabel("Slots:"))
        self.slot_checkboxes = {}
        if self.config.get('caen_hv', {}).get("enabled") and self.config.get('caen_hv', {}).get('crate_map'):
            for slot_str in self.config['caen_hv']['crate_map'].keys():
                checkbox = QCheckBox(f"Slot {slot_str}")
                self.slot_checkboxes[int(slot_str)] = checkbox
                board_temp_layout.addWidget(checkbox)
        self.board_temp_controls.hide()

        self.pdu_specific_controls = QWidget()
        pdu_spec_layout = QHBoxLayout(self.pdu_specific_controls)
        pdu_spec_layout.setContentsMargins(0,0,0,0)
        pdu_spec_layout.addWidget(QLabel("Ports:"))
        self.pdu_port_checkboxes = {}
        if self.config.get('netio_pdu', {}).get("enabled"):
            for i in range(1, 9): 
                checkbox = QCheckBox(f"P{i}")
                self.pdu_port_checkboxes[i] = checkbox
                pdu_spec_layout.addWidget(checkbox)
        self.pdu_specific_controls.hide()
        
        self.analysis_start_date = QDateEdit(QDate.currentDate().addDays(-7))
        self.analysis_end_date = QDateEdit(QDate.currentDate())
        self.analysis_start_date.setCalendarPopup(True)
        self.analysis_end_date.setCalendarPopup(True)
        
        ts_layout.addWidget(QLabel("Data:")); ts_layout.addWidget(self.analysis_combo)
        ts_layout.addWidget(self.hv_specific_controls)
        ts_layout.addWidget(self.board_temp_controls)
        ts_layout.addWidget(self.pdu_specific_controls)
        ts_layout.addWidget(QLabel("Start:")); ts_layout.addWidget(self.analysis_start_date)
        ts_layout.addWidget(QLabel("End:")); ts_layout.addWidget(self.analysis_end_date)
        
        self.correlation_widget = QWidget()
        corr_layout = QHBoxLayout(self.correlation_widget)
        corr_layout.setContentsMargins(0,0,0,0)
        self.corr_slot_combo = QComboBox()
        if self.config.get('caen_hv', {}).get("enabled") and self.config.get('caen_hv', {}).get('crate_map'): 
            self.corr_slot_combo.addItems(self.config['caen_hv']['crate_map'].keys())
        self.corr_param_combo = QComboBox()
        self.corr_param_combo.addItems(["VMon", "IMon"])
        self.corr_target_label = QLabel("Target: Slot 1 VMon vs LS Temp")
        self.corr_ch_start = QSpinBox()
        self.corr_ch_start.setRange(0, 99)
        self.corr_ch_end = QSpinBox()
        self.corr_ch_end.setRange(0, 99)
        self.corr_single_channel_checkbox = QCheckBox("Single")
        self.corr_single_channel_checkbox.setChecked(True)
        self.corr_start_date_edit = QDateEdit(QDate.currentDate().addDays(-7))
        self.corr_end_date_edit = QDateEdit(QDate.currentDate())
        self.corr_start_date_edit.setCalendarPopup(True)
        self.corr_end_date_edit.setCalendarPopup(True)
        
        corr_layout.addWidget(QLabel("Slot:")); corr_layout.addWidget(self.corr_slot_combo)
        corr_layout.addWidget(QLabel("Ch Start:")); corr_layout.addWidget(self.corr_ch_start)
        corr_layout.addWidget(QLabel("Ch End:")); corr_layout.addWidget(self.corr_ch_end)
        corr_layout.addWidget(self.corr_single_channel_checkbox)
        corr_layout.addWidget(QLabel("Param:")); corr_layout.addWidget(self.corr_param_combo)
        corr_layout.addWidget(self.corr_target_label)
        corr_layout.addWidget(QLabel("Start:")); corr_layout.addWidget(self.corr_start_date_edit)
        corr_layout.addWidget(QLabel("End:")); corr_layout.addWidget(self.corr_end_date_edit)

        self.correlation_widget.hide()
        
        self.plot_button = QPushButton("Plot Data")
        self.export_button = QPushButton("Export to CSV")
        
        control_layout.addWidget(QLabel("Mode:")); control_layout.addWidget(self.analysis_mode_combo)
        control_layout.addWidget(self.timeseries_widget); control_layout.addWidget(self.correlation_widget)
        control_layout.addStretch(1)
        control_layout.addWidget(self.plot_button); control_layout.addWidget(self.export_button)
        
        self.analysis_mode_combo.currentTextChanged.connect(self._on_analysis_mode_changed)
        self.analysis_combo.currentTextChanged.connect(self._on_analysis_type_changed)
        self.analysis_single_channel_checkbox.stateChanged.connect(self._toggle_single)
        self.hv_ch_start.valueChanged.connect(lambda val: self.hv_ch_end.setValue(val) if self.analysis_single_channel_checkbox.isChecked() else None)
        
        self.corr_slot_combo.currentTextChanged.connect(self._update_correlation_display)
        self.corr_single_channel_checkbox.stateChanged.connect(self._toggle_single_correlation)
        self.corr_ch_start.valueChanged.connect(lambda val: self.corr_ch_end.setValue(val) if self.corr_single_channel_checkbox.isChecked() else None)
        
        self.plot_button.clicked.connect(self._run_analysis)
        self.export_button.clicked.connect(self._export_analysis_data)
        
        self.analysis_canvas = FigureCanvas(Figure(figsize=(15, 6)))
        layout.addWidget(control_panel)
        layout.addWidget(self.analysis_canvas)

    def _on_analysis_mode_changed(self, mode):
        if mode == "Time Series": 
            self.timeseries_widget.show()
            self.correlation_widget.hide()
        elif mode == "Correlation": 
            self.timeseries_widget.hide()
            self.correlation_widget.show()

    def _on_analysis_type_changed(self, text):
        is_hv = "HV Voltage (VMon)" in text or "HV Current (IMon)" in text
        is_hv_temp = "HV Board Temperature" in text
        is_pdu = "PDU Power" in text or "PDU Current" in text or "PDU Energy" in text
        self.hv_specific_controls.setVisible(is_hv)
        self.board_temp_controls.setVisible(is_hv_temp)
        self.pdu_specific_controls.setVisible(is_pdu)

    def _toggle_single(self, state):
        is_single = (state == Qt.CheckState.Checked.value)
        self.hv_ch_end.setEnabled(not is_single)
        if is_single: self.hv_ch_end.setValue(self.hv_ch_start.value())

    def _toggle_single_correlation(self, state):
        is_single = (state == Qt.CheckState.Checked.value)
        self.corr_ch_end.setEnabled(not is_single)
        if is_single: self.corr_ch_end.setValue(self.corr_ch_start.value())

    def _update_correlation_display(self, slot_str):
        if not slot_str: return
        try: slot = int(slot_str)
        except ValueError: return
        target_temp = "LS Temp" if slot == 1 else "TH/O2 Temp"
        param = self.corr_param_combo.currentText()
        self.corr_target_label.setText(f"Target: Slot {slot} {param} vs {target_temp}")

    def _run_analysis(self):
        if not self.db_pool: 
            QMessageBox.critical(self, "Error", "DB pool not available.")
            return
        self.plot_button.setEnabled(False)
        self.plot_button.setText("Loading...")
        
        mode = self.analysis_mode_combo.currentText()
        queries, params = [], []

        if mode == "Time Series":
            query = self.analysis_map.get(self.analysis_combo.currentText())
            start_date = self.analysis_start_date.date().toString("yyyy-MM-dd 00:00:00")
            end_date = self.analysis_end_date.date().toString("yyyy-MM-dd 23:59:59")
            
            if query == "HV_QUERY":
                try:
                    slot = int(self.hv_slot_combo.currentText())
                    final_query = "SELECT `datetime`, `channel`, `vmon`, `imon` FROM HV_DATA WHERE `slot` = ? AND `channel` BETWEEN ? AND ? AND `datetime` BETWEEN ? AND ?"
                    queries.append(final_query)
                    params.append([slot, self.hv_ch_start.value(), self.hv_ch_end.value(), start_date, end_date])
                except ValueError: pass
            elif query == "HV_TEMP_QUERY":
                selected_slots = [slot for slot, checkbox in self.slot_checkboxes.items() if checkbox.isChecked()]
                if not selected_slots:
                    QMessageBox.warning(self, "Warning", "Please select at least one slot to plot.")
                    self._on_analysis_finished()
                    return
                placeholders = ', '.join(['?'] * len(selected_slots))
                final_query = f"SELECT DISTINCT `datetime`, `slot`, `board_temp` FROM HV_DATA WHERE `slot` IN ({placeholders}) AND `datetime` BETWEEN ? AND ?"
                queries.append(final_query)
                params.append(selected_slots + [start_date, end_date])
            elif query == "PDU_QUERY":
                selected_ports = [port for port, checkbox in self.pdu_port_checkboxes.items() if checkbox.isChecked()]
                if not selected_ports:
                    QMessageBox.warning(self, "Warning", "Please select at least one PDU port to plot.")
                    self._on_analysis_finished()
                    return
                placeholders = ', '.join(['?'] * len(selected_ports))
                final_query = f"SELECT `datetime`, `port_idx`, `power_w`, `current_ma`, `energy_wh` FROM PDU_DATA WHERE `port_idx` IN ({placeholders}) AND `datetime` BETWEEN ? AND ?"
                queries.append(final_query)
                params.append(selected_ports + [start_date, end_date])
            elif query: 
                queries.append(f"{query} WHERE `datetime` BETWEEN ? AND ?")
                params.append([start_date, end_date])

        elif mode == "Correlation":
            try: slot = int(self.corr_slot_combo.currentText())
            except ValueError: 
                self._on_analysis_finished()
                return
            ch_start = self.corr_ch_start.value()
            ch_end = self.corr_ch_end.value()
            start_date = self.corr_start_date_edit.date().toString("yyyy-MM-dd 00:00:00")
            end_date = self.corr_end_date_edit.date().toString("yyyy-MM-dd 23:59:59")
            
            queries.append("SELECT `datetime`, `channel`, `vmon`, `imon` FROM HV_DATA WHERE `slot` = ? AND `channel` BETWEEN ? AND ? AND `datetime` BETWEEN ? AND ?")
            params.append([slot, ch_start, ch_end, start_date, end_date])
            
            if slot == 1:
                queries.append("SELECT `datetime`, (`RTD_1` + `RTD_2`) / 2 as temp FROM LS_DATA WHERE `datetime` BETWEEN ? AND ? AND `RTD_1` IS NOT NULL AND `RTD_2` IS NOT NULL")
            else:
                queries.append("SELECT `datetime`, `temperature` as temp FROM TH_O2_DATA WHERE `datetime` BETWEEN ? AND ? AND `temperature` IS NOT NULL")
            params.append([start_date, end_date])
            
        if queries:
            self.analysis_thread = AnalysisWorker(self.db_pool, self.config.get('database', {}), queries, params)
            self.analysis_thread.analysis_complete.connect(self._plot_analysis_data)
            self.analysis_thread.error_occurred.connect(lambda e: global_bus.system_log_message.emit("ERROR", e))
            self.analysis_thread.finished.connect(self._on_analysis_finished)
            self.analysis_thread.start()
        else:
            self._on_analysis_finished()

    def _plot_analysis_data(self, dfs):
        if not dfs or any(df.empty for df in dfs):
            QMessageBox.warning(self, "Warning", "No data found for the selected period.")
            return
        
        self.last_analysis_df = dfs[0]
        self.analysis_canvas.figure.clear()
        mode = self.analysis_mode_combo.currentText()
        fig = self.analysis_canvas.figure
        
        if mode == "Time Series":
            analysis_type = self.analysis_combo.currentText()
            fig.suptitle(f"Time Series Analysis of {analysis_type}", fontsize=16)
            df = dfs[0]
            df['datetime'] = pd.to_datetime(df['datetime'])
            ax = fig.add_subplot(111)
            
            if "HV Voltage (VMon)" in analysis_type:
                df_pivot = df.pivot(index='datetime', columns='channel', values='vmon')
                df_pivot.plot(ax=ax, marker='.', linestyle='-', markersize=2)
                ax.set_ylabel("Voltage (VMon)")
            elif "HV Current (IMon)" in analysis_type:
                df_pivot = df.pivot(index='datetime', columns='channel', values='imon')
                df_pivot.plot(ax=ax, marker='.', linestyle='-', markersize=2)
                ax.set_ylabel("Current (IMon, uA)")
            elif "HV Board Temperature" in analysis_type:
                df.set_index('datetime', inplace=True)
                for slot in df['slot'].unique(): 
                    slot_df = df[df['slot'] == slot]
                    ax.plot(slot_df.index, slot_df['board_temp'], marker='.', linestyle='-', markersize=2, label=f'Slot {slot}')
                ax.set_ylabel("Temperature (C)")
            elif "PDU" in analysis_type:
                if "Power (W)" in analysis_type: value_col = 'power_w'; y_label = "Power (W)"
                elif "Current (mA)" in analysis_type: value_col = 'current_ma'; y_label = "Current (mA)"
                elif "Energy (Wh)" in analysis_type: value_col = 'energy_wh'; y_label = "Energy (Wh)"
                else: return 
                ax.set_ylabel(y_label)
                df_pivot = df.pivot_table(index='datetime', columns='port_idx', values=value_col, aggfunc='mean')
                port_map = self.config.get('netio_pdu', {}).get('port_map', {})
                rename_dict = {k: port_map.get(str(k), f"Port {k}") for k in df_pivot.columns}
                df_pivot.rename(columns=rename_dict, inplace=True)
                self.last_analysis_df = df_pivot.reset_index()
                df_pivot.plot(ax=ax, marker='.', linestyle='-', markersize=2)
            else:
                df.set_index('datetime', inplace=True)
                y_label = analysis_type[analysis_type.find("(")+1:analysis_type.find(")")] if "(" in analysis_type else ""
                ax.set_ylabel(y_label)
                for col in df.columns:
                    if col != 'status': 
                        ax.plot(df.index, df[col], marker='o', linestyle='-', markersize=2, label=col)
            ax.legend()
            ax.grid(True)
            
        elif mode == "Correlation":
            df_hv = dfs[0]
            df_temp = dfs[1]
            df_hv['datetime'] = pd.to_datetime(df_hv['datetime'])
            df_temp['datetime'] = pd.to_datetime(df_temp['datetime'])
            merged_df = pd.merge_asof(df_hv.sort_values('datetime'), df_temp.sort_values('datetime'), on='datetime', direction='nearest', tolerance=pd.Timedelta('10min'))
            merged_df.dropna(inplace=True)
            self.last_analysis_df = merged_df
            
            param = self.corr_param_combo.currentText().lower()
            slot = self.corr_slot_combo.currentText()
            temp_name = "LS Temp" if int(slot) == 1 else "TH/O2 Temp"
            
            fig.suptitle(f"Correlation of Slot {slot} {param.upper()} vs {temp_name}", fontsize=16)
            ax = fig.add_subplot(111)
            for channel in merged_df['channel'].unique(): 
                channel_df = merged_df[merged_df['channel'] == channel]
                ax.scatter(channel_df['temp'], channel_df[param], alpha=0.5, label=f'Ch {channel}')
            ax.set_xlabel(f"{temp_name} (C)")
            ax.set_ylabel(f"{param.upper()} ({'V' if 'v' in param else 'uA'})")
            ax.grid(True)
            ax.legend(title='Channel')
            
            if len(merged_df) > 1:
                m, b = np.polyfit(merged_df['temp'], merged_df[param], 1)
                ax.plot(merged_df['temp'], m * merged_df['temp'] + b, color='red', linewidth=2, linestyle='--', label='Overall Trend')
                corr = merged_df['temp'].corr(merged_df[param])
                ax.text(0.05, 0.95, f'Overall Trend:\ny = {m:.3f}x + {b:.2f}\nr = {corr:.3f}', transform=ax.transAxes, fontsize=10, verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
                
        fig.autofmt_xdate()
        fig.tight_layout(rect=[0, 0.03, 1, 0.95])
        self.analysis_canvas.draw()

    def _export_analysis_data(self):
        if self.last_analysis_df is None or self.last_analysis_df.empty: return
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV File", f"export_{time.strftime('%Y%m%d_%H%M%S')}.csv", "CSV Files (*.csv)")
        if path: self.last_analysis_df.to_csv(path, index=False)

    def _on_analysis_finished(self):
        self.plot_button.setEnabled(True)
        self.plot_button.setText("Plot Data")