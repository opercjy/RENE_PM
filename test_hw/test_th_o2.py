import serial
import time
import sys

# 설정: 실제 포트 번호로 변경하세요 (예: /dev/ttyUSB0)
PORT = "/dev/ttyUSB0" 
BAUDRATE = 4800

def test_sensor():
    print(f"Trying to open {PORT} at {BAUDRATE}...")
    try:
        ser = serial.Serial(PORT, BAUDRATE, timeout=1)
        print("Connected. Waiting for data...")
        
        while True:
            if ser.in_waiting > 0:
                # 데이터 읽기 (Modbus RTU는 바이너리 데이터일 수 있음)
                data = ser.read(ser.in_waiting)
                
                # Hex 형태로 출력하여 데이터 패킷 확인
                hex_data = " ".join([f"{b:02X}" for b in data])
                print(f"[RECV] {hex_data}")
                
                # 만약 ASCII 데이터라면 디코딩 시도
                try:
                    print(f"[ASCII] {data.decode('utf-8').strip()}")
                except:
                    pass
            
            time.sleep(0.1)
            
    except serial.SerialException as e:
        print(f"Error: {e}")
    except KeyboardInterrupt:
        print("\nStopped.")
        if 'ser' in locals() and ser.is_open:
            ser.close()

if __name__ == "__main__":
    test_sensor()
