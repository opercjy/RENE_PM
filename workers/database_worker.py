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
    TABLE_SCHEMAS = [
        """CREATE TABLE IF NOT EXISTS LS_DATA (
            `datetime` DATETIME NOT NULL PRIMARY KEY, `RTD_1` FLOAT NULL, `RTD_2` FLOAT NULL,
            `DIST_1` FLOAT NULL, `DIST_2` FLOAT NULL
        );""",
        """CREATE TABLE IF NOT EXISTS RADON_DATA (
            `datetime` DATETIME NOT NULL PRIMARY KEY, `mu` FLOAT NULL, `sigma` FLOAT NULL
        );""",
        """CREATE TABLE IF NOT EXISTS MAGNETOMETER_DATA (
            `datetime` DATETIME NOT NULL PRIMARY KEY, `Bx` FLOAT NULL, `By` FLOAT NULL,
            `Bz` FLOAT NULL, `B_mag` FLOAT NULL
        );""",
        """CREATE TABLE IF NOT EXISTS TH_O2_DATA (
            `datetime` DATETIME NOT NULL PRIMARY KEY, `temperature` FLOAT NULL,
            `humidity` FLOAT NULL, `oxygen` FLOAT NULL
        );""",
        """CREATE TABLE IF NOT EXISTS ARDUINO_DATA (
            `datetime` DATETIME NOT NULL PRIMARY KEY, `analog_1` FLOAT NULL, `analog_2` FLOAT NULL,
            `analog_3` FLOAT NULL, `analog_4` FLOAT NULL, `analog_5` FLOAT NULL,
            `digital_status` INT NULL, `message` VARCHAR(255) NULL
        );""",
        """CREATE TABLE IF NOT EXISTS HV_DATA (
            `datetime` DATETIME, `slot` INT, `channel` INT, `power` BOOLEAN, `vmon` FLOAT, `imon` FLOAT,
            `v0set` FLOAT, `i0set` FLOAT, `status` INT, PRIMARY KEY (`datetime`, `slot`, `channel`)
        );"""
    ]

    def __init__(self, db_config, data_queue: queue.Queue):
        super().__init__()
        self.db_config = db_config
        self.data_queue = data_queue
        self._is_running = True
        self.conn = None
        self.batch_timer = QTimer(self)
        self.batch_timer.timeout.connect(self.process_batch)

    def _connect_and_setup(self):
        try:
            if self.conn:
                self.conn.ping()
                return True
        except (mariadb.Error, AttributeError):
            self.conn = None
        
        try:
            params = {
                'user': self.db_config['user'], 'password': self.db_config['password'],
                'database': self.db_config['database']
            }
            if self.db_config.get('unix_socket'):
                params['unix_socket'] = self.db_config['unix_socket']
            else:
                params['host'] = self.db_config.get('host', '127.0.0.1')
                params['port'] = self.db_config.get('port', 3306)
            
            self.conn = mariadb.connect(**params)
            self.cursor = self.conn.cursor()
            logging.info("Database connection established.")
            for schema in self.TABLE_SCHEMAS:
                self.cursor.execute(schema)
            self.conn.commit()
            logging.info("Database tables are ready.")
            return True
        except mariadb.Error as e:
            self.error_occurred.emit(f"DB Connection/Setup Error: {e}")
            self.conn = None
            return False

    @pyqtSlot()
    def run(self):
        if not self.db_config.get('enabled'): return
        if not self._connect_and_setup():
            QTimer.singleShot(10000, self.run)
            return
        self.batch_timer.start(60 * 1000)
        logging.info("Database worker started.")

    @pyqtSlot()
    def process_batch(self):
        if not self._is_running: return
        try:
            if self.conn: self.conn.ping()
            else: 
                if not self._connect_and_setup(): return
        except mariadb.Error:
            if not self._connect_and_setup(): return

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
        
        try:
            for type_key, data_list in batch.items():
                if data_list:
                    self.cursor.executemany(self.SQL_INSERT[type_key], data_list)
            self.conn.commit()
            logging.info(f"Successfully inserted batch of {batch_size} items.")
        except mariadb.Error as e:
            logging.error(f"DB insert error: {e}. Rolling back...")
            self.conn.rollback()

    @pyqtSlot()
    def stop(self):
        self._is_running = False
        self.batch_timer.stop()
        logging.info("Processing remaining items before stopping DB worker.")
        self.process_batch()
        if self.conn:
            self.conn.close()
            logging.info("DB connection closed.")