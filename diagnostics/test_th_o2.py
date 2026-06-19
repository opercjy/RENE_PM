# diagnostics/test_th_o2.py

from pymodbus.client import ModbusSerialClient
import time

PORT = '/dev/ttyUSB1'
BAUDRATE = 4800
SLAVE_ID = 1

def test_th_o2():
    print(f"☁️ TH/O2 센서 ({PORT}) 정밀 진단 시작 (Baud: {BAUDRATE}, Slave: {SLAVE_ID})...")
    client = ModbusSerialClient(port=PORT, baudrate=BAUDRATE, parity='N', stopbits=1, bytesize=8, timeout=1.0)
    
    if not client.connect():
        print("❌ 오류: 포트 열기 실패. 다른 프로세스가 포트를 점유하고 있는지 확인하십시오.")
        return

    print("✅ 연결 성공! 레지스터 폴링 시작 (Ctrl+C 종료)\n")
    print(f"{'시간':^10} | {'온도 (°C)':^10} | {'습도 (%)':^10} | {'산소 (%)':^10}")
    print("-" * 50)
    
    try:
        for _ in range(5):
            res = client.read_holding_registers(address=0, count=3, slave=SLAVE_ID)
            current_time = time.strftime("%H:%M:%S")
            
            if res.isError():
                print(f"{current_time:^10} | ⚠️ 응답 오류 (Modbus Timeout)")
            else:
                humi = res.registers[0] / 10.0
                t_raw = res.registers[1]
                temp = ((t_raw - 65536) / 10.0) if t_raw > 32767 else (t_raw / 10.0)
                o2 = res.registers[2] / 10.0
                
                print(f"{current_time:^10} | {temp:^10.2f} | {humi:^10.2f} | {o2:^10.2f}")
            time.sleep(2.0)
    except KeyboardInterrupt:
        pass
    finally:
        client.close()
        print("\n✅ 진단 완료.")

if __name__ == "__main__":
    test_th_o2()