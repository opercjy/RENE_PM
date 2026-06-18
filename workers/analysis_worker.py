# workers/analysis_worker.py

from PyQt6.QtCore import QThread, pyqtSignal
import pandas as pd
import mariadb

class AnalysisWorker(QThread):
    analysis_complete = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

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
            for query, param in zip(self.queries, self.params):
                df = pd.read_sql(query, conn, params=param)
                results.append(df)
            
            self.analysis_complete.emit(results)
            
        except Exception as e:
            self.error_occurred.emit(f"Data analysis error: {e}")
        
        finally:
            if conn:
                conn.close()