# diagnostics/test_all_sensors_scanner.py

import time
import struct
import serial
import serial.tools.list_ports
from pymodbus.client import ModbusSerialClient

def get_hw_serial(port_device):
    """USB-to-Serial 변환 칩셋의 하드웨어 고유 시리얼 넘버를 반환합니다."""
    ports = serial.tools.list_ports.comports()
    for p in ports:
        if p.device == port_device:
            return p.serial_number if p.serial_number else "NO_SERIAL"
    return "UNKNOWN"

def test_radon_ascii(port):
    """라돈 센서의 ASCII 프로토콜을 테스트합니다."""
    try:
        with serial.Serial(port, 19200, timeout=1.0, write_timeout=1.0) as ser:
            ser.write(b'VALUE?\r\n')
            time.sleep(0.3)
            res = ser.readline().decode('ascii', 'ignore').strip()
            if "VALUE" in res:
                return True
    except Exception:
        pass
    return False

def scan_all_sensors():
    print("시스템에 연결된 모든 센서의 논리 포트 및 하드웨어 시리얼 매핑을 시작합니다...\n")
    
    available_ports = sorted([p.device for p in serial.tools.list_ports.comports() if 'ttyUSB' in p.device])
    if not available_ports:
        print("시스템에 인식된 ttyUSB 포트가 없습니다.")
        return

    # (센서명, Baudrate, Parity, Slave ID, Address, Count)
    modbus_candidates = [
        ("FS24X 불꽃 감지기", 9600, 'E', 45, 2, 2),
        ("VOC 가스 감지기", 9600, 'N', 50, 8, 2),
        ("TH/O2 온습도/산소 센서", 4800, 'N', 1, 0, 3)
    ]

    found_mapping = {}

    for port in available_ports:
        hw_serial = get_hw_serial(port)
        print(f"▶ 포트 검사 중: {port} (H/W Serial: {hw_serial})")
        
        # 1. 라돈 센서 검사 (ASCII)
        if test_radon_ascii(port):
            print(f"  [발견] 라돈 센서 (ASCII, 19200bps)")
            found_mapping["Radon"] = {"port": port, "serial": hw_serial}
            continue
            
        # 2. Modbus 센서 검사
        device_found = False
        for name, baud, parity, slave, addr, count in modbus_candidates:
            client = ModbusSerialClient(port=port, baudrate=baud, timeout=0.3, parity=parity, stopbits=1, bytesize=8)
            if client.connect():
                try:
                    res = client.read_holding_registers(address=addr, count=count, slave=slave)
                    if not res.isError():
                        print(f"  [발견] {name} (Modbus, {baud}bps, Slave {slave})")
                        found_mapping[name] = {"port": port, "serial": hw_serial}
                        device_found = True
                        break
                except Exception:
                    pass
                finally:
                    client.close()
            
        if not device_found:
            print("  응답하는 센서가 없습니다.")

    print("\n" + "="*70)
    print("[최종 하드웨어 매핑 결과 (Udev Rules 작성용)]")
    print(f"{'센서 종류':<25} | {'현재 포트':<12} | {'통신칩 고유 시리얼 넘버(iSerial)'}")
    print("-" * 70)
    for name, info in found_mapping.items():
        print(f"{name:<25} | {info['port']:<12} | {info['serial']}")
    print("="*70)

if __name__ == "__main__":
    scan_all_sensors()