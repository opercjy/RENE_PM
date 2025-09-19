# workers/analysis_worker.py 파일을 아래 코드로 전체 교체하세요.

from PyQt5.QtCore import QThread, pyqtSignal
import pandas as pd
import mariadb

class AnalysisWorker(QThread):
    # === 변경점 1: 여러 데이터프레임을 리스트 형태로 반환하도록 시그널 수정 ===
    analysis_complete = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    # === 변경점 2: 여러 쿼리와 파라미터를 리스트로 받도록 __init__ 수정 ===
    def __init__(self, db_pool, db_config, queries: list, params: list):
        super().__init__()
        self.db_pool = db_pool
        self.db_config = db_config
        self.queries = queries
        self.params = params

    def run(self):
        conn = None
        try:
            conn = self.db_pool.get_connection()
            conn.database = self.db_config['database']
            
            results = []
            # === 변경점 3: 받은 모든 쿼리에 대해 반복 실행 ===
            for query, param in zip(self.queries, self.params):
                df = pd.read_sql(query, conn, params=param)
                results.append(df)
            
            self.analysis_complete.emit(results)
            
        except Exception as e:
            self.error_occurred.emit(f"Data analysis error: {e}")
        
        finally:
            if conn:
                conn.close()