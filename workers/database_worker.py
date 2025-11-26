# workers/database_worker.py

import logging
import queue
import mariadb
import threading
import time
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
            INSERT IGNORE INTO HV_DATA (datetime, slot, channel, power, vmon, imon, v0set, i0set, status, board_temp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        'UPS': "INSERT IGNORE INTO UPS_DATA (`datetime`, `status`, `linev`, `bcharge`, `timeleft`) VALUES (?, ?, ?, ?, ?)",
        
        # [v2.1 신규 추가] PDU 데이터 INSERT 쿼리
        'PDU': "INSERT INTO PDU_DATA (datetime, port_idx, state, power_w, current_ma, energy_wh) VALUES (?, ?, ?, ?, ?, ?)"
    }
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
            `v0set` FLOAT, `i0set` FLOAT, `status` INT, `board_temp` FLOAT, 
            PRIMARY KEY (`datetime`, `slot`, `channel`)
        );""", "CREATE INDEX IF NOT EXISTS idx_hv_datetime ON HV_DATA (datetime);",
        """CREATE TABLE IF NOT EXISTS UPS_DATA (
            `datetime` DATETIME NOT NULL PRIMARY KEY, `status` VARCHAR(20), `linev` FLOAT,
            `bcharge` FLOAT, `timeleft` FLOAT
        );""", "CREATE INDEX IF NOT EXISTS idx_ups_datetime ON UPS_DATA (datetime);",

        # [v2.1 신규 추가] PDU 데이터 테이블 스키마 (DATETIME(3) 및 Auto Increment PK 사용)
        """CREATE TABLE IF NOT EXISTS PDU_DATA (
            id INT AUTO_INCREMENT PRIMARY KEY,
            datetime DATETIME(3) NOT NULL,
            port_idx INT NOT NULL,
            state BOOLEAN NOT NULL,
            power_w FLOAT,
            current_ma INT,
            energy_wh FLOAT
        );""", 
        "CREATE INDEX IF NOT EXISTS idx_pdu_time ON PDU_DATA (datetime);",
        "CREATE INDEX IF NOT EXISTS idx_pdu_port ON PDU_DATA (port_idx);"
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
            
            # 1. 기본 테이블 스키마 생성
            for schema in self.TABLE_SCHEMAS:
                try:
                    cursor.execute(schema)
                except mariadb.Error as e:
                    # 스키마 실행 중 발생할 수 있는 경미한 오류(예: 인덱스 생성 경고) 로그
                    logging.warning(f"Issue executing schema statement: {schema[:100]}... Error: {e}")
            conn.commit()
            
            # 2. 'board_temp' 컬럼 존재 여부 확인 (마이그레이션 로직)
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = ? AND TABLE_NAME = 'HV_DATA' AND COLUMN_NAME = 'board_temp'
            """, (self.db_config['database'],))
            
            if cursor.fetchone()[0] == 0:
                logging.warning("Column 'board_temp' not found in HV_DATA. Altering table...")
                cursor.execute("ALTER TABLE HV_DATA ADD COLUMN board_temp FLOAT")
                conn.commit()
                logging.info("Successfully added 'board_temp' column to HV_DATA table.")

            logging.info("Database tables and indexes are ready (including PDU_DATA).")
            return True
        except mariadb.Error as e:
            self.error_occurred.emit(f"DB Table/Index Setup Error: {e}")
            logging.error(f"DB Table/Index Setup Error: {e}")
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
        # [v2.1 수정] 배치 처리 로직 개선 (List[Tuple] 및 Tuple 모두 처리)
        if not self._is_running: return
        batch_size = self.data_queue.qsize()
        if batch_size == 0: return

        batch = {k: [] for k in self.SQL_INSERT.keys()}
        processed_record_count = 0 # 실제 처리된 레코드 수 카운트

        for _ in range(batch_size):
            try:
                item = self.data_queue.get_nowait()
                
                if item:
                    data_type = item.get('type')
                    data_payload = item.get('data')

                    if data_type in batch:
                        # 데이터 형식을 확인하여 처리
                        if isinstance(data_payload, list):
                            # 페이로드가 리스트인 경우 (예: PDU, HV), extend 사용
                            batch[data_type].extend(data_payload)
                            processed_record_count += len(data_payload)
                        elif data_payload: 
                            # 페이로드가 단일 레코드(Tuple 등)인 경우 (예: DAQ, Radon), append 사용
                            # 기존 코드는 이 방식만 사용했음.
                            batch[data_type].append(data_payload)
                            processed_record_count += 1
                        else:
                             logging.debug(f"Received empty payload for type {data_type}")
                
                self.data_queue.task_done()
            except queue.Empty: break
        
        if processed_record_count == 0: return
        
        conn = None
        try:
            conn = self.db_pool.get_connection()
            conn.database = self.db_config['database']
            cursor = conn.cursor()
            for type_key, data_list in batch.items():
                if data_list:
                    cursor.executemany(self.SQL_INSERT[type_key], data_list)
            conn.commit()
            # 실제 처리된 레코드 수로 로그 메시지 수정
            logging.info(f"Successfully inserted batch of {processed_record_count} records.")
            
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