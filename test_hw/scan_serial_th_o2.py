import serial
import time

PORT = "/dev/ttyUSB0"  # 포트가 확실하다면

# 테스트할 설정들
BAUDRATES = [4800, 9600, 19200, 38400, 57600, 115200]
PARITIES = [serial.PARITY_NONE, serial.PARITY_EVEN, serial.PARITY_ODD]

def scan():
    print(f"Scanning {PORT}...")
    
    for baud in BAUDRATES:
        for parity in PARITIES:
            print(f"Testing Baud: {baud}, Parity: {parity}...", end="", flush=True)
            try:
                ser = serial.Serial(
                    port=PORT,
                    baudrate=baud,
                    bytesize=serial.EIGHTBITS,
                    parity=parity,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0.5
                )
                
                # 데이터가 들어오는지 1초간 대기
                start = time.time()
                received = False
                while time.time() - start < 1.5:
                    if ser.in_waiting > 0:
                        raw = ser.read(ser.in_waiting)
                        print(f" [DATA!] Hex: {raw.hex()}")
                        received = True
                        break
                    time.sleep(0.1)
                
                ser.close()
                
                if not received:
                    print(" No data.")
                else:
                    # 데이터를 찾았으면 루프 중단 (원하면 계속 스캔 가능)
                    print(f"\n>>> SUCCESS! Found data at {baud}, {parity}")
                    return 

            except serial.SerialException:
                print(" Open Failed.")
                
if __name__ == "__main__":
    scan()
