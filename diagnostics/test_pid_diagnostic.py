# diagnostics/test_pid_diagnostic.py

import time
import glob
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException

# 현장 하드웨어 딥스위치 세팅
BAUDRATE = 9600
SLAVE_ID = 2
SCALE_FACTOR = 1000.0

def test_pid_diagnostics():
    print(f"[VOC/PID Detector] RAEGuard 2 PID 자동 탐색 및 진단 (Baud: {BAUDRATE}, Slave: {SLAVE_ID})")
    
    target_port = None
    ports = sorted(glob.glob('/dev/ttyUSB*'))
    
    # 1. 자동 탐색 (Auto-Hunt)
    for port in ports:
        print(f"🔍 {port} 포트 스캔 중... ", end="", flush=True)
        client = ModbusSerialClient(port=port, baudrate=BAUDRATE, timeout=0.5, parity='N', stopbits=1, bytesize=8)
        
        if client.connect():
            try:
                # [핵심 수정] 타임아웃 예외가 발생해도 스크립트가 죽지 않도록 예외 처리
                res = client.read_holding_registers(address=8, count=2, slave=SLAVE_ID)
                if not res.isError():
                    target_port = port
                    print("✅ 센서 응답 확인!")
                    client.close()
                    break
            except Exception:
                pass # 응답이 없으면 조용히 무시하고 다음 포트로 넘어감
            client.close()
        print("❌ 응답 없음")

    if not target_port:
        print("\n🚨 가스 감지기를 찾을 수 없습니다. (전원, 국번 세팅, 케이블을 확인하세요)")
        return

    print(f"\n🚀 [최종 연결 포트]: {target_port}")
    print("-" * 50)
    print(f"{'시간':^10} | {'VOC 농도 (ppm)':^15} | {'통신 상태':^15}")
    print("-" * 50)

    # 2. 실시간 데이터 폴링
    client = ModbusSerialClient(port=target_port, baudrate=BAUDRATE, timeout=1.0, parity='N', stopbits=1, bytesize=8)
    client.connect()
    try:
        while True:
            current_time = time.strftime("%H:%M:%S")
            try:
                res_conc = client.read_holding_registers(address=8, count=2, slave=SLAVE_ID)
                if res_conc.isError():
                    print(f"{current_time:^10} | {'ERR (ErrorObj)':^15} | {'수신 실패':^15}")
                else:
                    raw_conc = (res_conc.registers[0] << 16) + res_conc.registers[1]
                    concentration = raw_conc / SCALE_FACTOR
                    print(f"{current_time:^10} | {concentration:^15.3f} | {'정상 수신':^15}")
            except Exception as e:
                print(f"{current_time:^10} | {'ERR (Exception)':^15} | {str(e)[:15]:^15}")
            
            time.sleep(2.0)
    except KeyboardInterrupt:
        print("\n진단 종료.")
    finally:
        client.close()

if __name__ == "__main__":
    test_pid_diagnostics()