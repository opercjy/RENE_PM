# diagnostics/test_arduino.py

import serial
import time

PORT = '/dev/ttyACM0'
BAUDRATE = 9600

def test_arduino():
    print(f"📟 아두이노 센서 ({PORT}) 정밀 진단 시작...")
    try:
        ser = serial.Serial(PORT, BAUDRATE, timeout=2.0)
        print("✅ 포트 개방 성공. 스트리밍 데이터 대기 중...\n")
        
        for _ in range(5):
            line = ser.readline().decode('utf-8', 'ignore').strip()
            if line:
                print(f"RAW Data: {line}")
                data = {}
                for pair in line.split(','):
                    if ':' in pair:
                        key, val_str = pair.split(':', 1)
                        if val_str.strip().upper() != 'NONE':
                            data[key.strip()] = float(val_str.strip())
                print(f"Parsed Dict: {data}\n")
            else:
                print("No Data Received.")
            time.sleep(1.0)
            
        ser.close()
        print("✅ 진단 완료.")
    except Exception as e:
        print(f"\n❌ 진단 실패. 아두이노 연결 상태를 확인하십시오: {e}")

if __name__ == "__main__":
    test_arduino()