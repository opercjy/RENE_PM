# diagnostics/test_radon.py

import serial
import time

PORT = '/dev/ttyUSB0'
BAUDRATE = 19200

def test_radon():
    print(f"☢️ 라돈(Radon) 센서 ({PORT}) 정밀 진단 시작...")
    try:
        # GIL 프리징 방어를 위한 timeout 설정
        ser = serial.Serial(PORT, BAUDRATE, timeout=2.0, write_timeout=2.0)
        print("✅ 포트 개방 성공. 데이터 요청(VALUE?) 전송 중...\n")
        
        for i in range(3):
            ser.write(b'VALUE?\r\n')
            time.sleep(0.5)
            response = ser.readline().decode('ascii', 'ignore').strip()
            
            if response and "VALUE" in response:
                mu = float(response.split(':')[1].split(' ')[1])
                sigma = float(response.split(':')[2].split(' ')[1])
                print(f"[{i+1}/3] 수신: {response} -> 파싱 완료: Mu={mu:.2f}, Sigma={sigma:.2f}")
            else:
                print(f"[{i+1}/3] 응답 대기 중 또는 유효하지 않은 응답: '{response}' (초기 10분 안정화 기간일 수 있음)")
            time.sleep(2.0)
            
        ser.close()
        print("\n✅ 진단 완료.")
    except Exception as e:
        print(f"\n❌ 진단 실패. USB 연결 및 /dev/ttyUSB0의 dialout 권한을 확인하십시오: {e}")

if __name__ == "__main__":
    test_radon()