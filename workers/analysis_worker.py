# workers/analysis_worker.py

from PyQt5.QtCore import QThread, pyqtSignal
import pandas as pd
import mariadb

class AnalysisWorker(QThread):
    """
    데이터베이스에서 데이터를 조회하고 분석하는 작업을 비동기적으로 처리하는 워커 스레드입니다.
    """
    analysis_complete = pyqtSignal(pd.DataFrame)
    error_occurred = pyqtSignal(str)

    def __init__(self, db_config, query, params):
        super().__init__()
        self.db_config = db_config
        self.query = query
        self.params = params

    def run(self):
        try:
            # 데이터베이스 연결 설정
            db_params = {
                'user': self.db_config['user'], 'password': self.db_config['password'],
                'database': self.db_config['database']
            }
            if self.db_config.get('unix_socket'):
                db_params['unix_socket'] = self.db_config['unix_socket']
            else:
                db_params['host'] = self.db_config.get('host', '127.0.0.1')
                db_params['port'] = self.db_config.get('port', 3306)
            
            conn = mariadb.connect(**db_params)
            
            # 파라미터 바인딩을 사용한 쿼리 실행
            df = pd.read_sql(self.query, conn, params=self.params)
            
            conn.close()
            
            # 분석 완료 시그널 발생
            self.analysis_complete.emit(df)
            
        except Exception as e:
            # 오류 발생 시 시그널 발생
            self.error_occurred.emit(f"Data analysis error: {e}")