# check_hardware_improved.py
import sys
import json
import logging
import os
import re # VISA 리소스 문자열 파싱을 위해 추가

# --- 라이브러리 임포트 및 오류 처리 ---
try:
    import nidaqmx
    from nidaqmx.system import System
except ImportError:
    nidaqmx = None

try:
    import pyvisa
except ImportError:
    pyvisa = None

try:
    import serial
    import serial.tools.list_ports
    from pymodbus.client import ModbusSerialClient
except ImportError:
    serial = None
    ModbusSerialClient = None

# 로깅 기본 설정 비활성화
logging.basicConfig(level=logging.CRITICAL)

# --- ANSI 색상 코드 ---
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'

def print_status(component, status, message):
    """상태 메시지를 색상과 함께 출력하는 헬퍼 함수"""
    status_color = Colors.GREEN if status == "OK" else Colors.YELLOW if status == "DISABLED" else Colors.RED
    print(f"[{Colors.BLUE}{component:^18}{Colors.ENDC}] [{status_color}{status:^9}{Colors.ENDC}] {message}")

def load_config(config_file="config_v2.json"):
    """설정 파일을 로드하는 함수"""
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print_status("System", "ERROR", f"Configuration file not found: {config_file}")
        sys.exit(1)
    except json.JSONDecodeError:
        print_status("System", "ERROR", f"Error decoding JSON from: {config_file}")
        sys.exit(1)

def check_ni_devices(config):
    """NI-DAQ 장비 연결을 확인하는 함수 (기존과 유사)"""
    print("\n--- Checking National Instruments (NI-DAQ) Devices ---")
    if not nidaqmx:
        print_status("NI-DAQ", "ERROR", "nidaqmx library is not installed.")
        return

    try:
        connected_devices = {dev.serial_num: dev.name for dev in System.local().devices}
        if not connected_devices:
            print_status("NI-DAQ System", "NOT FOUND", "No NI devices found on the local system.")
            return
        
        print(f"  > Found {len(connected_devices)} NI device(s) on the system.")

        daq_config = config.get('daq', {})
        if not daq_config.get('enabled'):
            print_status("NI-DAQ", "DISABLED", "NI-DAQ monitoring is disabled in config.")
            return

        for module in daq_config.get('modules', []):
            role = module.get('role')
            sn_hex = module.get('serial_number')
            try:
                sn_int = int(sn_hex, 16)
                if sn_int in connected_devices:
                    dev_name = connected_devices[sn_int]
                    print_status(role, "OK", f"Module found as '{dev_name}' (S/N: {sn_hex})")
                else:
                    print_status(role, "NOT FOUND", f"Module with S/N {sn_hex} is not connected.")
            except (ValueError, TypeError):
                print_status(role, "ERROR", f"Invalid serial number format: {sn_hex}")

    except Exception as e:
        print_status("NI-DAQ System", "ERROR", f"An error occurred while scanning: {e}")

def check_visa_devices(config):
    """[개선됨] VISA 장비 연결을 자동 탐지 방식으로 확인하는 함수"""
    print("\n--- Checking VISA Devices (e.g., Magnetometer) ---")
    if not pyvisa:
        print_status("PyVISA", "ERROR", "pyvisa library is not installed.")
        return

    mag_config = config.get('magnetometer', {})
    if not mag_config.get('enabled'):
        print_status("Magnetometer", "DISABLED", "Magnetometer monitoring is disabled in config.")
        return

    # 설정에서 Vendor ID와 Product ID를 가져옴 (16진수 문자열)
    vendor_id = mag_config.get('idVendor')
    product_id = mag_config.get('idProduct')

    if not vendor_id or not product_id:
        print_status("Magnetometer", "ERROR", "idVendor or idProduct is not defined in config.")
        return

    # 시도할 VISA 백엔드 목록 (플랫폼 호환성 개선)
    backends_to_try = ['@ni', '@py']
    device_found_and_communicated = False

    for backend in backends_to_try:
        print(f"\n  > Trying VISA backend: '{backend}'")
        try:
            rm = pyvisa.ResourceManager(backend)
            resources = rm.list_resources()
            print(f"    - Found {len(resources)} resource(s): {resources}")
            
            target_resource = None
            for res in resources:
                # USB 리소스 문자열에서 Vendor/Product ID를 추출하여 비교
                match = re.search(r'USB[0-9]*::([0-9A-Fa-f]+)::([0-9A-Fa-f]+)::', res, re.IGNORECASE)
                if match:
                    res_vid, res_pid = match.groups()
                    if res_vid.lower() == vendor_id.lower().replace('0x', '') and \
                       res_pid.lower() == product_id.lower().replace('0x', ''):
                        target_resource = res
                        print_status("Magnetometer", "OK", f"Device matched! Found at '{target_resource}'")
                        break
            
            if target_resource:
                try:
                    inst = rm.open_resource(target_resource)
                    inst.timeout = 2000 # 2초 타임아웃
                    idn = inst.query('*IDN?').strip()
                    print_status("Communication", "OK", f"Successfully communicated. ID: {idn}")
                    inst.close()
                    device_found_and_communicated = True
                    break # 성공했으므로 다른 백엔드는 시도할 필요 없음
                except pyvisa.errors.VisaIOError as e:
                    print_status("Communication", "FAILED", f"Found device but could not query IDN. Error: {e}")
                finally:
                    # 연결을 시도한 후에는 리소스 관리자를 닫아주는 것이 안전합니다.
                    rm.close()

        except Exception as e:
            # NI-VISA가 설치되지 않은 경우 'Could not open VISA library'와 같은 오류가 발생할 수 있습니다.
            print(f"    - Error initializing or using this backend: {e}")

    if not device_found_and_communicated:
        print_status("Magnetometer", "NOT FOUND", f"Device (Vendor={vendor_id}, Product={product_id}) could not be found or communication failed with all attempted backends.")


def check_serial_devices(config):
    """pyserial 장비 연결을 확인하는 함수 (기존과 유사)"""
    print("\n--- Checking Serial & Modbus Devices ---")
    if not serial:
        print_status("PySerial", "ERROR", "pyserial library is not installed.")
        return

    available_ports = [port.device for port in serial.tools.list_ports.comports()]
    print(f"  > Found {len(available_ports)} serial port(s): {available_ports}")

    devices_to_check = {
        'Radon': config.get('radon', {}),
        'TH/O2 (Modbus)': config.get('th_o2', {}),
        'Arduino': config.get('arduino', {})
    }

    for name, dev_config in devices_to_check.items():
        if not dev_config.get('enabled'):
            print_status(name, "DISABLED", f"{name} monitoring is disabled in config.")
            continue

        port = dev_config.get('port')
        baudrate = dev_config.get('baudrate')

        if not port or not baudrate:
            print_status(name, "ERROR", "Port or baudrate is not defined in config.")
            continue

        if port in available_ports:
            print_status(name, "OK", f"Port '{port}' found. Trying to open with baudrate {baudrate}...")
            
            try:
                with serial.Serial(port, baudrate, timeout=0.1) as ser:
                    print_status(f"{name} Port", "OK", f"Successfully opened and closed port at {baudrate} bps.")

                if "Modbus" in name and ModbusSerialClient:
                    client = ModbusSerialClient(port=port, baudrate=baudrate, timeout=1)
                    if client.connect():
                        print_status(f"{name} Modbus", "OK", "Modbus connection successful.")
                        client.close()
                    else:
                        print_status(f"{name} Modbus", "FAILED", "Could not establish Modbus connection.")
            except serial.SerialException as e:
                print_status(f"{name} Port", "FAILED", f"Found port but failed to open: {e}")
        else:
            print_status(name, "NOT FOUND", f"Port '{port}' is not available on the system.")


if __name__ == "__main__":
    print(f"{Colors.YELLOW}====================================================={Colors.ENDC}")
    print(f"{Colors.YELLOW} RENE-PM Hardware Connection Diagnostics Utility (Improved) {Colors.ENDC}")
    print(f"{Colors.YELLOW}====================================================={Colors.ENDC}")
    
    config = load_config("config_v2.json")
    if config:
        check_ni_devices(config)
        check_visa_devices(config)
        check_serial_devices(config)
    
    print("\n--- Diagnostics Complete ---")
