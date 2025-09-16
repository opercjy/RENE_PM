# workers/database_worker.py

import logging
import queue
import mariadb
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer

class DatabaseWorker(QObject):
    status_update = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    SQL_INSERT = {
        'DAQ': "INSERT IGNORE INTO LS_DATA (`datetime`, `RTD_1`, `RTD_2`, `DIST_1`, `DIST_2`) VALUES (?, ?, ?, ?, ?)",
        'RADON': "INSERT IGNORE INTO RADON_DATA (`datetime`, `mu`, `sigma`) VALUES (?, ?, ?)",
        'MAG': "INSERT IGNORE INTO MAGNETOMETER_DATA (`datetime`, `Bx`, `By`, `Bz`, `B_mag`) VALUES (?, ?, ?, ?, ?)",
        'TH_O2': "INSERT IGNORE INTO TH_O2_DATA (`datetime`, `temperature`, `humidity`, `oxygen`) VALUES (?, ?, ?, ?)",
        'ARDUINO': "INSERT IGNORE INTO ARDUINO_DATA (`datetime`, `analog_1`, `analog_2`, `analog_3`, `analog_4`, `analog_5`, `digital_status`, `message`) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        'HV': """
            INSERT IGNORE INTO HV_DATA (datetime, slot, channel, power, vmon, imon, v0set, i0set, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
    }
    # === 변경점: 모든 테이블에 datetime 인덱스 생성 구문 추가 ===
    TABLE_SCHEMAS = [
        """CREATE TABLE IF NOT EXISTS LS_DATA (
            `datetime` DATETIME NOT NULL PRIMARY KEY, `RTD_1` FLOAT NULL, `RTD_2` FLOAT NULL,
            `DIST_1` FLOAT NULL, `DIST_2` FLOAT NULL
        );""", "CREATE INDEX IF NOT EXISTS idx_ls_datetime ON LS_DATA (datetime);",
        """CREATE TABLE IF NOT EXISTS RADON_DATA (
            `datetime` DATETIME NOT NULL PRIMARY KEY, `mu` FLOAT NULL, `sigma` FLOAT NULL
        );""", "CREATE INDEX IF NOT EXISTS idx_radon_datetime ON RADON_DATA (datetime);",
        """CREATE TABLE IF NOT EXISTS MAGNETOMETER_DATA (
            `datetime` DATETIME NOT NULL PRIMARY KEY, `Bx` FLOAT NULL, `By` FLOAT NULL,
            `Bz` FLOAT NULL, `B_mag` FLOAT NULL
        );""", "CREATE INDEX IF NOT EXISTS idx_mag_datetime ON MAGNETOMETER_DATA (datetime);",
        """CREATE TABLE IF NOT EXISTS TH_O2_DATA (
            `datetime` DATETIME NOT NULL PRIMARY KEY, `temperature` FLOAT NULL,
            `humidity` FLOAT NULL, `oxygen` FLOAT NULL
        );""", "CREATE INDEX IF NOT EXISTS idx_tho2_datetime ON TH_O2_DATA (datetime);",
        """CREATE TABLE IF NOT EXISTS ARDUINO_DATA (
            `datetime` DATETIME NOT NULL PRIMARY KEY, `analog_1` FLOAT NULL, `analog_2` FLOAT NULL,
            `analog_3` FLOAT NULL, `analog_4` FLOAT NULL, `analog_5` FLOAT NULL,
            `digital_status` INT NULL, `message` VARCHAR(255) NULL
        );""", "CREATE INDEX IF NOT EXISTS idx_arduino_datetime ON ARDUINO_DATA (datetime);",
        """CREATE TABLE IF NOT EXISTS HV_DATA (
            `datetime` DATETIME, `slot` INT, `channel` INT, `power` BOOLEAN, `vmon` FLOAT, `imon` FLOAT,
            `v0set` FLOAT, `i0set` FLOAT, `status` INT, PRIMARY KEY (`datetime`, `slot`, `channel`)
        );""", "CREATE INDEX IF NOT EXISTS idx_hv_datetime ON HV_DATA (datetime);"
    ]

    def __init__(self, db_pool, db_config, data_queue: queue.Queue):
        super().__init__()
        self.db_pool = db_pool
        self.db_config = db_config
        self.data_queue = data_queue
        self._is_running = True
        self.batch_timer = QTimer(self)
        self.batch_timer.timeout.connect(self.process_batch)

    def _setup_tables(self):
        conn = None
        try:
            conn = self.db_pool.get_connection()
            conn.database = self.db_config['database']
            cursor = conn.cursor()
            for schema in self.TABLE_SCHEMAS:
                cursor.execute(schema)
            conn.commit()
            logging.info("Database tables and indexes are ready.")
            return True
        except mariadb.Error as e:
            self.error_occurred.emit(f"DB Table/Index Setup Error: {e}")
            return False
        finally:
            if conn: conn.close()

    @pyqtSlot()
    def run(self):
        if not self.db_pool: return
        if not self._setup_tables():
            QTimer.singleShot(10000, self.run)
            return
        self.batch_timer.start(60 * 1000)
        logging.info("Database worker started, using shared connection pool.")

    @pyqtSlot()
    def process_batch(self):
        if not self._is_running: return
        batch_size = self.data_queue.qsize()
        if batch_size == 0: return
        batch = {k: [] for k in self.SQL_INSERT.keys()}
        for _ in range(batch_size):
            try:
                item = self.data_queue.get_nowait()
                if item and item.get('type') in batch:
                    batch[item['type']].append(item['data'])
                self.data_queue.task_done()
            except queue.Empty: break
        
        conn = None
        try:
            conn = self.db_pool.get_connection()
            conn.database = self.db_config['database']
            cursor = conn.cursor()
            for type_key, data_list in batch.items():
                if data_list:
                    cursor.executemany(self.SQL_INSERT[type_key], data_list)
            conn.commit()
            logging.info(f"Successfully inserted batch of {batch_size} items.")
        except mariadb.Error as e:
            logging.error(f"DB insert error: {e}. Rolling back...")
            if conn: conn.rollback()
        finally:
            if conn: conn.close()

    @pyqtSlot()
    def stop(self):
        self._is_running = False
        self.batch_timer.stop()
        logging.info("Processing remaining items before stopping DB worker.")
        self.process_batch()
        logging.info("DB worker stopped.")