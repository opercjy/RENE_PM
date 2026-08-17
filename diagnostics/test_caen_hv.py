# diagnostics/test_caen_hv.py

import sys
import time

try:
    from caen_libs import caenhvwrapper as hv
except ImportError:
    print("❌ 오류: caen_libs 모듈을 찾을 수 없습니다. C++ 래퍼 컴파일 상태를 확인하십시오.")
    sys.exit(1)

IP_ADDRESS = "192.168.0.39"
USERNAME = "admin"
PASSWORD = "admin"

def test_hv_connection():
    print(f"🔌 CAEN HV Mainframe ({IP_ADDRESS}) 정밀 진단 시작...")
    try:
        device = hv.Device.open(hv.SystemType.SY4527, hv.LinkType.TCPIP, IP_ADDRESS, USERNAME, PASSWORD)
        print("✅ 통신 연결 성공! 보드 파라미터를 조회합니다.\n")
        
        # Slot 1, 4, 8 보드 온도 조회 테스트
        for slot in [1, 4, 8]:
            temp_values = device.get_bd_param([slot], 'Temp')
            board_temp = float(temp_values[0]) if temp_values else -1.0
            print(f"  ▶ Slot {slot} Board Temp: {board_temp:.1f} °C")

        # Slot 1, Ch 0의 VMon, IMon 조회
        vmon = device.get_ch_param(1, [0], 'VMon')[0]
        imon = device.get_ch_param(1, [0], 'IMon')[0]
        print(f"  ▶ Slot 1 Ch 0 -> VMon: {float(vmon):.1f} V, IMon: {float(imon):.2f} uA")

        device.close()
        print("\n✅ 진단 완료 및 포트 정상 해제.")
    except Exception as e:
        print(f"\n❌ 진단 실패. 네트워크 및 장비 전원, 계정 정보를 확인하십시오: {e}")

if __name__ == "__main__":
    test_hv_connection()