# diagnostics/test_pdu.py

from pymodbus.client import ModbusTcpClient

IP_ADDRESS = '192.168.0.2'
PORT = 502
SLAVE_ID = 1

def test_pdu():
    print(f"⚡ NETIO PowerPDU ({IP_ADDRESS}:{PORT}) 정밀 진단 시작...")
    client = ModbusTcpClient(IP_ADDRESS, port=PORT, timeout=3)
    
    if not client.connect():
        print("❌ TCP 연결 실패. PDU 네트워크 라우팅 및 M2M API 활성화 여부를 확인하십시오.")
        return
        
    try:
        # 글로벌 전압/주파수
        res_gv = client.read_input_registers(address=0, count=2, slave=SLAVE_ID)
        res_gp = client.read_input_registers(address=200, count=1, slave=SLAVE_ID)
        
        if res_gv.isError() or res_gp.isError():
            print("❌ Modbus TCP 읽기 에러. 장비 국번이나 권한을 확인하십시오.")
        else:
            freq = res_gv.registers[0] / 100.0
            volt = res_gv.registers[1] / 10.0
            power = res_gp.registers[0]
            print(f"\n✅ 글로벌 상태 - 전압: {volt}V, 주파수: {freq}Hz, 총 부하: {power}W\n")
            
        # 포트 1번 상태 읽기
        res_coil = client.read_coils(address=101, count=1, slave=SLAVE_ID)
        res_port_pwr = client.read_input_registers(address=201, count=1, slave=SLAVE_ID)
        
        if not res_coil.isError() and not res_port_pwr.isError():
            state = "ON" if res_coil.bits[0] else "OFF"
            p_watt = res_port_pwr.registers[0]
            print(f"✅ 포트 1 상태 - 전원: {state}, 소비 전력: {p_watt}W")

    except Exception as e:
        print(f"❌ 진단 실패: {e}")
    finally:
        client.close()
        print("\n✅ 진단 완료.")

if __name__ == "__main__":
    test_pdu()