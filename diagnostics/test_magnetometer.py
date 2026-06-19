# diagnostics/test_magnetometer.py

import pyvisa
import time
import math

RESOURCE_NAME = "USB0::0x1BFA::0x0498::0003055::INSTR"

def test_magnetometer():
    print(f"🧲 자기장 센서 (Magnetometer) 정밀 진단 시작...")
    rm = pyvisa.ResourceManager('@py')
    try:
        inst = rm.open_resource(RESOURCE_NAME, timeout=3000)
        inst.read_termination = '\n'
        inst.write_termination = '\n'
        
        inst.write('*RST')
        time.sleep(1.5)
        idn = inst.query('*IDN?').strip()
        print(f"✅ 장비 인식 성공: {idn}\n")
        print("-" * 50)
        print(f"{'Bx (mG)':^10} | {'By (mG)':^10} | {'Bz (mG)':^10} | {'|B| (mG)':^10}")
        print("-" * 50)
        
        for _ in range(5):
            res_x = inst.query(':MEASure:SCALar:FLUX:X?')
            res_y = inst.query(':MEASure:SCALar:FLUX:Y?')
            res_z = inst.query(':MEASure:SCALar:FLUX:Z?')
            
            bx = float(res_x.strip().split(' ')[0]) * 10_000_000
            by = float(res_y.strip().split(' ')[0]) * 10_000_000
            bz = float(res_z.strip().split(' ')[0]) * 10_000_000
            b_mag = math.sqrt(bx**2 + by**2 + bz**2)
            
            print(f"{bx:^10.2f} | {by:^10.2f} | {bz:^10.2f} | {b_mag:^10.2f}")
            time.sleep(1.0)
            
        inst.close()
        print("\n✅ 진단 완료.")
    except Exception as e:
        print(f"\n❌ 진단 실패. USB 연결(lsusb) 및 Resource Name 권한을 확인하십시오: {e}")

if __name__ == "__main__":
    test_magnetometer()