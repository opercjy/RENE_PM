# workers/analysis_worker.py

from PyQt5.QtCore import QThread, pyqtSignal
import pandas as pd
import mariadb

class AnalysisWorker(QThread):
    analysis_complete = pyqtSignal(pd.DataFrame)
    error_occurred = pyqtSignal(str)

    # === 변경점 1: __init__에서 db_config도 함께 받도록 수정 ===
    def __init__(self, db_pool, db_config, query, params):
        super().__init__()
        self.db_pool = db_pool
        self.db_config = db_config # 데이터베이스 이름을 알기 위해 config 저장
        self.query = query
        self.params = params

    def run(self):
        conn = None
        try:
            conn = self.db_pool.get_connection()
            # === 변경점 2: 연결 사용 전, 데이터베이스 지정 ===
            conn.database = self.db_config['database']
            
            df = pd.read_sql(self.query, conn, params=self.params)
            
            self.analysis_complete.emit(df)
            
        except Exception as e:
            self.error_occurred.emit(f"Data analysis error: {e}")
        
        finally:
            if conn:
                conn.close()