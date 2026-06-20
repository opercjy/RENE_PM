# main.py (전체 덮어쓰기)

import sys
import json
import logging
import queue
import mariadb
import os

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QThread, QTimer, QMetaObject, Qt

from core.state_store import StateStore
from core.event_bus import global_bus
from experts.safety_expert import SafetyExpert
from experts.worker_manager import WorkerManager
from views.main_window import MainWindow
from workers.database_worker import DatabaseWorker

CONFIG = {}

def load_config(config_file="config_v3.json"):
    global CONFIG
    script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
    config_path = os.path.join(script_dir, config_file)
    if not os.path.exists(config_path):
        config_path = os.path.join(script_dir, "config_v2.json")
        if not os.path.exists(config_path):
            print(f"Error: Config file not found: {config_path}")
            sys.exit(1)
            
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            CONFIG = json.load(f)
        return CONFIG
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from {config_path}: {e}")
        sys.exit(1)

class LogToEventBusHandler(logging.Handler):
    def emit(self, record):
        msg = self.format(record)
        global_bus.system_log_message.emit(record.levelname, msg)

def init_logging():
    log_level = CONFIG.get('logging_level', 'INFO').upper()
    log_filename = "rene_pm_v3.log"
    file_handler = logging.FileHandler(log_filename, 'w')
    stream_handler = logging.StreamHandler()
    
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format='%(asctime)s - %(levelname)s - [%(threadName)s] - %(message)s',
        handlers=[file_handler, stream_handler],
        force=True
    )
    
    eb_handler = LogToEventBusHandler()
    eb_handler.setFormatter(logging.Formatter('%(message)s'))
    logging.getLogger().addHandler(eb_handler)
    
    logging.info("="*60)
    logging.info("RENE-PM v3.0 (Event-Driven Architecture) Starting")
    logging.info("="*60)

def create_db_pool(db_config):
    try:
        pool_config = {
            'user': db_config['user'], 'password': db_config['password'],
            'pool_name': db_config.get('pool_name', 'rene_pm_v3_pool'), 
            'pool_size': db_config.get('pool_size', 5)
        }
        if db_config.get('unix_socket'):
            pool_config['unix_socket'] = db_config['unix_socket']
        else:
            pool_config['host'] = db_config.get('host', '127.0.0.1')
            pool_config['port'] = db_config.get('port', 3306)
        
        pool = mariadb.ConnectionPool(**pool_config)
        logging.info("Database connection pool created successfully.")
        return pool
    except mariadb.Error as e:
        logging.error(f"Failed to create DB connection pool: {e}"); return None

if __name__ == '__main__':
    load_config()
    init_logging()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    
    app.setStyleSheet("""
        QWidget { font-size: 12pt; font-family: 'Arial'; }
        QGroupBox { font-weight: bold; font-size: 13pt; }
        QTabBar::tab { min-width: 80px; padding: 6px 12px; margin: 2px; font-size: 11pt; }
    """)

    db_queue = queue.Queue()
    db_pool = create_db_pool(CONFIG.get('database', {}))

    state_store = StateStore(CONFIG)
    safety_expert = SafetyExpert(CONFIG)
    worker_manager = WorkerManager(CONFIG, db_queue)

    db_thread = None
    db_worker = None
    if CONFIG.get('database', {}).get('enabled') and db_pool:
        db_thread = QThread()
        db_worker = DatabaseWorker(db_pool, CONFIG['database'], db_queue)
        db_worker.moveToThread(db_thread)
        db_thread.started.connect(db_worker.run)
        db_thread.start()

    main_window = MainWindow(CONFIG, state_store, db_pool)
    main_window.show()

    main_window.ui_timer = QTimer(main_window)
    main_window.ui_timer.timeout.connect(lambda: global_bus.ui_update_requested.emit())
    main_window.ui_timer.start(5000)

    workers_to_start = [
        'caen_hv', 'netio_pdu', 'fire_detector', 'voc_detector', 
        'ups', 'daq', 'radon', 'th_o2', 'magnetometer', 'arduino'
    ]
    for w_name in workers_to_start:
        if CONFIG.get(w_name, {}).get("enabled", False):
            worker_manager.start_worker(w_name)

    def on_about_to_quit():
        logging.info("Application shutting down...")
        worker_manager.stop_all()
        # [핵심] DB 워커 역시 강제 종료가 아닌 우아한 깃발 내리기로 유도
        if db_worker and db_thread:
            db_worker._is_running = False
            db_thread.quit()
            db_thread.wait(3000)

    app.aboutToQuit.connect(on_about_to_quit)
    sys.exit(app.exec())