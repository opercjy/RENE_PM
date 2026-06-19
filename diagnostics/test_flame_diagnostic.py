# diagnostics/test_flame_diagnostic.py

import time
import struct
import glob
from pymodbus.client import ModbusSerialClient

# 현장 하드웨어 딥스위치 세팅
BAUDRATE = 19200
SLAVE_ID = 1
PARITY = 'N'

def test_flame():
    print(f"[Flame Detector] FS24X Plus 자동 탐색 및 진단 (Baud: {BAUDRATE}, Slave: {SLAVE_ID}, Parity: {PARITY})")
    
    target_port = None
    ports = sorted(glob.glob('/dev/ttyUSB*'))
    
    # 1. 자동 탐색 (Auto-Hunt)
    for port in ports:
        print(f"🔍 {port} 포트 스캔 중... ", end="", flush=True)
        client = ModbusSerialClient(port=port, baudrate=BAUDRATE, timeout=0.5, parity=PARITY, stopbits=1, bytesize=8)
        
        if client.connect():
            try:
                # [핵심 수정] 타임아웃 예외 무시
                res = client.read_holding_registers(address=2, count=2, slave=SLAVE_ID)
                if not res.isError():
                    target_port = port
                    print("✅ 센서 응답 확인!")
                    client.close()
                    break
            except Exception:
                pass
            client.close()
        print("❌ 응답 없음")

    if not target_port:
        print("\n🚨 불꽃 감지기를 찾을 수 없습니다. (전원, 국번 세팅, 케이블을 확인하세요)")
        return

    print(f"\n🚀 [최종 연결 포트]: {target_port}")
    print("-" * 65)
    print(f"{'시간':^10} | {'상태 (State)':^15} | {'온도 (°C)':^10} | {'알람 레벨':^10} | {'고장 코드':^10}")
    print("-" * 65)

    # 2. 실시간 데이터 폴링
    client = ModbusSerialClient(port=target_port, baudrate=BAUDRATE, timeout=1.0, parity=PARITY, stopbits=1, bytesize=8)
    client.connect()
    try:
        while True:
            current_time = time.strftime("%H:%M:%S")
            try:
                res_alarm = client.read_holding_registers(address=2, count=2, slave=SLAVE_ID)
                res_fault = client.read_holding_registers(address=4, count=1, slave=SLAVE_ID)
                res_state = client.read_holding_registers(address=6, count=1, slave=SLAVE_ID)
                
                if res_alarm.isError() or res_state.isError():
                    print(f"{current_time:^10} | Modbus 응답 에러 (Timeout)")
                else:
                    raw_bytes = struct.pack('>HH', res_alarm.registers[0], res_alarm.registers[1])
                    alarm_level = struct.unpack('>f', raw_bytes)[0]
                    fault_code = res_fault.registers[0] if not res_fault.isError() else 0
                    
                    state_val = res_state.registers[0]
                    if state_val in [1, 6]: state_str = "NORMAL"
                    elif state_val in [2, 3]: state_str = "INHIBITED"
                    elif state_val in [5, 7]: state_str = "WARNING"
                    elif state_val in [1, 4, 8]: state_str = "FAULT"
                    elif state_val in [16, 17, 3] or alarm_level >= 1.0: state_str = "FIRE ALARM!"
                    else: state_str = f"UNKNOWN({state_val})"

                    res_temp = client.read_holding_registers(address=14, count=1, slave=SLAVE_ID)
                    if not res_temp.isError():
                        temp_raw = res_temp.registers[0]
                        if temp_raw > 32767: temp_raw -= 65536
                        temperature = temp_raw / 10.0
                    else:
                        temperature = 0.0

                    print(f"{current_time:^10} | {state_str:^15} | {temperature:^10.1f} | {alarm_level:^10.1f} | {fault_code:^10}")
            except Exception as e:
                print(f"{current_time:^10} | 예외 발생: {str(e)[:20]}")
                
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n진단 종료.")
    finally:
        client.close()

if __name__ == "__main__":
    test_flame()