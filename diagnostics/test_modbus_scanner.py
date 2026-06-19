# diagnostics/test_modbus_scanner.py

import time
import glob
import struct
from pymodbus.client import ModbusSerialClient

def ultimate_modbus_scan():
    print("🔍 [Ultimate Modbus Scanner] 센서 정밀 전수 조사 시작...")
    print("PC에 연결된 모든 USB 포트와 통신 파라미터 조합을 스캔합니다.\n")
    
    ports = sorted(glob.glob('/dev/ttyUSB*'))
    if not ports:
        print("🚨 시스템에 인식된 /dev/ttyUSB 포트가 없습니다. USB 허브 전원을 확인하세요.")
        return

    # 탐색할 후보군: (센서명, Baudrate, Parity, Slave ID, Address, Count)
    candidates = [
        ("VOC 가스 감지기 (v3 세팅)", 9600, 'N', 50, 8, 2),
        ("VOC 가스 감지기 (v2 세팅)", 9600, 'N', 2, 8, 2),
        ("FS24X 불꽃 감지기 (v3 세팅)", 9600, 'E', 45, 2, 2),
        ("FS24X 불꽃 감지기 (v2 세팅)", 19200, 'N', 1, 2, 2)
    ]

    found_devices = {}

    for port in ports:
        print(f"▶ 포트 검사 중: {port}")
        for name, baud, parity, slave, addr, count in candidates:
            # 타임아웃을 0.3초로 짧게 주어 스캔 속도 극대화
            client = ModbusSerialClient(port=port, baudrate=baud, timeout=0.3, parity=parity, stopbits=1, bytesize=8)
            
            if client.connect():
                try:
                    res = client.read_holding_registers(address=addr, count=count, slave=slave)
                    if not res.isError():
                        print(f"  ✅ [발견!] {name}")
                        print(f"      - 연결 파라미터: Port={port}, Baud={baud}, Parity={parity}, Slave ID={slave}")
                        
                        # 센서별 간단한 데이터 디코딩 시연
                        if "VOC" in name:
                            raw_conc = (res.registers[0] << 16) + res.registers[1]
                            print(f"      - 현재 판독값: {raw_conc / 1000.0:.3f} ppm")
                        elif "불꽃" in name:
                            raw_bytes = struct.pack('>HH', res.registers[0], res.registers[1])
                            alarm_level = struct.unpack('>f', raw_bytes)[0]
                            print(f"      - 현재 판독값: 알람 레벨 {alarm_level:.1f}")
                            
                        found_devices[name] = port
                        break # 이 포트에서 장비를 찾았으므로 다음 포트로 이동
                except Exception:
                    pass # 응답 없으면 조용히 무시 (타임아웃)
                finally:
                    client.close()

    print("\n" + "="*60)
    print("🎯 [최종 탐색 결과 요약]")
    if not found_devices:
        print("❌ 아무 센서도 찾지 못했습니다.")
        print("   1. 하드웨어 전원 및 결선 상태를 확인하십시오.")
        print("   2. 장비 내부의 딥스위치(국번, 통신속도)가 전혀 다른 값일 수 있습니다.")
    else:
        for dev, p in found_devices.items():
            print(f" ✔️ {dev} ---> {p}")
    print("="*60)

if __name__ == "__main__":
    ultimate_modbus_scan()