# experts/worker_manager.py (전체 덮어쓰기)

import logging
import time
from PyQt6.QtCore import QObject, QThread, Qt, QMetaObject
from PyQt6 import sip
from core.event_bus import global_bus

from workers.daq_worker import DaqWorker
from workers.radon_worker import RadonWorker
from workers.magnetometer_worker import MagnetometerWorker
from workers.th_o2_worker import ThO2Worker
from workers.arduino_worker import ArduinoWorker
from workers.hv_worker import HVWorker
from workers.ups_worker import UPSWorker
from workers.pdu_worker import PDUWorker
from workers.fire_worker import FireWorker
from workers.pid_worker import PidWorker

class WorkerManager(QObject):
    def __init__(self, config, db_queue):
        super().__init__()
        self.config = config
        self.db_queue = db_queue
        self.threads = {}
        self.hv_db_push_counter = 0
        
        # [핵심] UI를 멈추게 만들던 모든 Direct Call(forward 함수) 삭제 완료
        global_bus.cmd_toggle_worker.connect(self.toggle_worker)

    def toggle_worker(self, name, enable):
        if enable:
            if name not in self.threads:
                global_bus.system_log_message.emit("INFO", f"[{name}] 워커 스레드 동적 할당 및 가동 시작.")
                self.start_worker(name)
        else:
            if name in self.threads:
                global_bus.system_log_message.emit("WARNING", f"[{name}] 워커 스레드 종료 및 리소스 반환 중...")
                thread, worker = self.threads[name]
                stop_method = 'stop' if hasattr(worker, 'stop') else 'stop_worker'
                
                if name in ['daq', 'magnetometer']:
                    worker._is_running = False
                    if hasattr(worker, stop_method):
                        getattr(worker, stop_method)()
                else:
                    if hasattr(worker, stop_method):
                        QMetaObject.invokeMethod(worker, stop_method, Qt.ConnectionType.QueuedConnection)
                
                thread.quit()
                if not thread.wait(3000):
                    thread.terminate()
                
                del self.threads[name]
                global_bus.system_log_message.emit("INFO", f"[{name}] 워커 스레드 폐기 완료.")
                global_bus.device_connection_changed.emit(name, False)

    def start_worker(self, name):
        if name in self.threads: return
        worker_map = {
            'daq': (DaqWorker, True), 'radon': (RadonWorker, False), 'magnetometer': (MagnetometerWorker, True),
            'th_o2': (ThO2Worker, False), 'arduino': (ArduinoWorker, False), 'caen_hv': (HVWorker, False), 
            'ups': (UPSWorker, False), 'netio_pdu': (PDUWorker, False), 'fire_detector': (FireWorker, False), 
            'voc_detector': (PidWorker, False)
        }
        if name not in worker_map: return
        WClass, use_run = worker_map[name]
        thread = QThread()
        if name in ['caen_hv', 'netio_pdu']: worker = WClass(self.config.get(name, {}))
        else: worker = WClass(self.config.get(name, {}), self.db_queue)

        self._connect_worker_to_bus(name, worker)
        worker.moveToThread(thread)
        if hasattr(worker, 'finished'):
            worker.finished.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)

        thread.started.connect(worker.run if use_run else worker.start_worker)
        thread.start()
        self.threads[name] = (thread, worker)

    def _handle_hv_data_ready(self, d):
        ts = self._now()
        global_bus.sensor_data_updated.emit('hv_status', {'ts': ts, 'data': d})
        
        self.hv_db_push_counter += 1
        if self.hv_db_push_counter >= 60:
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
            for slot, slot_data in d.get('slots', {}).items():
                board_temp = slot_data.get('board_temp', -1.0)
                for ch, params in slot_data.get('channels', {}).items():
                    db_tuple = (
                        timestamp, slot, ch, params.get('Pw', False), 
                        params.get('VMon', 0.0), params.get('IMon', 0.0), 
                        params.get('V0Set', 0.0), params.get('I0Set', 0.0), 
                        params.get('Status', 0), board_temp
                    )
                    self.db_queue.put({'type': 'HV', 'data': db_tuple})
            self.hv_db_push_counter = 0

    def _connect_worker_to_bus(self, name, worker):
        if hasattr(worker, 'error_occurred'):
            worker.error_occurred.connect(lambda msg: global_bus.system_log_message.emit("ERROR", f"[{name}] {msg}"))

        if name == 'caen_hv':
            worker.data_ready.connect(self._handle_hv_data_ready)
            worker.connection_status.connect(lambda s: global_bus.device_connection_changed.emit('caen_hv', s))
            worker.control_command_status.connect(lambda msg: global_bus.system_log_message.emit("INFO", msg))
            worker.setpoints_ready.connect(global_bus.hv_setpoints_ready.emit)
            
            # [핵심] 시그널과 워커 슬롯을 1:1로 직접 연결하여 완벽한 비동기 큐잉 달성
            global_bus.request_hv_setpoints.connect(worker.fetch_setpoints)
            global_bus.cmd_hv_control.connect(worker.execute_control_command)
            
        elif name == 'daq':
            worker.avg_data_ready.connect(lambda ts, d: global_bus.sensor_data_updated.emit('daq_avg', {'ts': ts, 'data': d}))
            worker.raw_data_ready.connect(lambda d: global_bus.sensor_data_updated.emit('raw_data', {'ts': self._now(), 'data': d}))
        elif name == 'radon':
            worker.data_ready.connect(lambda ts, mu, sig: global_bus.sensor_data_updated.emit('radon_avg', {'ts': ts, 'data': {'mu': mu, 'sigma': sig}}))
            worker.radon_status_update.connect(global_bus.radon_status_updated.emit)
        elif name == 'magnetometer':
            worker.avg_data_ready.connect(lambda ts, d: global_bus.sensor_data_updated.emit('mag_avg', {'ts': ts, 'data': d}))
            worker.raw_data_ready.connect(lambda d: global_bus.sensor_data_updated.emit('raw_data', {'ts': self._now(), 'data': d}))
        elif name == 'th_o2':
            worker.avg_data_ready.connect(lambda ts, t, h, o2: global_bus.sensor_data_updated.emit('th_o2_avg', {'ts': ts, 'data': {'temp': t, 'humi': h, 'o2': o2}}))
            worker.raw_data_ready.connect(lambda d: global_bus.sensor_data_updated.emit('raw_data', {'ts': self._now(), 'data': d}))
        elif name == 'arduino':
            worker.avg_data_ready.connect(lambda ts, d: global_bus.sensor_data_updated.emit('arduino_avg', {'ts': ts, 'data': d}))
            worker.raw_data_ready.connect(lambda d: global_bus.sensor_data_updated.emit('raw_data', {'ts': self._now(), 'data': d}))
        elif name == 'ups':
            worker.data_ready.connect(lambda d: global_bus.sensor_data_updated.emit('ups_status', {'ts': self._now(), 'data': d}))
        elif name == 'fire_detector':
            worker.data_ready.connect(lambda d: global_bus.sensor_data_updated.emit('fire_status', {'ts': self._now(), 'data': d.get('fire_detector', {})}))
        elif name == 'voc_detector':
            worker.data_ready.connect(lambda d: global_bus.sensor_data_updated.emit('voc_status', {'ts': self._now(), 'data': d.get('voc_detector', {})}))
        elif name == 'netio_pdu':
            worker.sig_status_updated.connect(lambda d: global_bus.sensor_data_updated.emit('pdu_status', {'ts': self._now(), 'data': d}))
            worker.sig_connection_changed.connect(lambda s: global_bus.device_connection_changed.emit('netio_pdu', s))
            worker.sig_log_message.connect(global_bus.system_log_message.emit)
            if hasattr(worker, 'sig_queue_data'):
                worker.sig_queue_data.connect(lambda d: self.db_queue.put(d))
            # [핵심] PDU 역시 비동기 다이렉트 연결
            global_bus.cmd_pdu_control_single.connect(worker.control_single_port)
            global_bus.cmd_pdu_control_all.connect(worker.control_all_ports)

    def _now(self): return time.time()

    def stop_all(self):
        for name, (thread, worker) in list(self.threads.items()):
            if thread.isRunning() and not sip.isdeleted(worker):
                stop_method = 'stop' if hasattr(worker, 'stop') else 'stop_worker'
                if name in ['daq', 'magnetometer']:
                    worker._is_running = False
                    if hasattr(worker, stop_method): getattr(worker, stop_method)()
                else:
                    if hasattr(worker, stop_method):
                        QMetaObject.invokeMethod(worker, stop_method, Qt.ConnectionType.QueuedConnection)
                thread.quit()

        for name, (thread, worker) in list(self.threads.items()):
            if thread.isRunning():
                if not thread.wait(3000):
                    global_bus.system_log_message.emit("WARNING", f"Thread '{name}' hung. Forcing termination.")
                    thread.terminate()
                    thread.wait(1000)
        self.threads.clear()