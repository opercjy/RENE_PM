from pymodbus.client import ModbusSerialClient
import time

PORT = "/dev/ttyUSB0"
BAUDRATE = 4800  # 혹은 4800
SLAVE_ID = 1     # 보통 1번

def test_modbus():
    client = ModbusSerialClient(
        port=PORT,
        baudrate=BAUDRATE,
        parity='N',
        stopbits=1,
        bytesize=8,
        timeout=1
    )
    
    if client.connect():
        print(f"Connected to {PORT}. Sending Modbus request...")
        
        # Input Register 0번지부터 3개 읽기 시도
        rr = client.read_input_registers(address=0, count=3, slave=SLAVE_ID)
        
        if rr.isError():
            print(f"Read Error: {rr}")
        else:
            print(f"Success! Registers: {rr.registers}")
            
        client.close()
    else:
        print("Failed to connect.")

if __name__ == "__main__":
    test_modbus()
