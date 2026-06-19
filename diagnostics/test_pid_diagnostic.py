import time
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException

PORT = '/dev/ttyUSB2'
BAUDRATE = 9600
SLAVE_ID = 50
SCALE_FACTOR = 1000.0

def test_pid_diagnostics():
    print(f"[{PORT}] RAEGuard 2 PID 정밀 진단 시작 (Baud: {BAUDRATE}, Slave ID: {SLAVE_ID})")
    
    client = ModbusSerialClient(
        port=PORT, baudrate=BAUDRATE, timeout=1.0, 
        parity='N', stopbits=1, bytesize=8
    )

    if not client.connect():
        print("[오류] 포트 열기 실패.")
        return

    print("-" * 60)
    print(f"{'시간':^10} | {'농도 (ppm)':^15} | {'H/W 알람(Reg 34)':^20}")
    print("-" * 60)

    try:
        while True:
            current_time = time.strftime("%H:%M:%S")
            conc_str = "ERR"
            alarm_str = "ERR"

            # 1. 농도 레지스터 읽기 (Address 8, Count 2)
            try:
                res_conc = client.read_holding_registers(address=8, count=2, slave=SLAVE_ID)
                if not res_conc.isError():
                    raw_conc = (res_conc.registers[0] << 16) + res_conc.registers[1]
                    concentration = raw_conc / SCALE_FACTOR
                    conc_str = f"{concentration:.3f}"
            except ModbusException:
                pass

            # 2. 하드웨어 알람 레지스터 읽기 (Address 34, Count 1)
            # 이 요청이 실패하면 해당 펌웨어는 레지스터 34를 지원하지 않는 것이다.
            try:
                res_alarm = client.read_holding_registers(address=34, count=1, slave=SLAVE_ID)
                if not res_alarm.isError():
                    alarm_val = res_alarm.registers[0]
                    alarm_str = f"Status: {alarm_val}"
                else:
                    alarm_str = "Not Supported"
            except ModbusException:
                alarm_str = "Exception"

            print(f"{current_time:^10} | {conc_str:^15} | {alarm_str:^20}")
            time.sleep(2.0)

    except KeyboardInterrupt:
        print("\n진단 종료.")
    finally:
        client.close()

if __name__ == "__main__":
    test_pid_diagnostics()
