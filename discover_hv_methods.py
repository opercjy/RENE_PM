# discover_hv_methods.py

import sys
import json
import logging

try:
    from caen_libs import caenhvwrapper as hv
except ImportError:
    print("FATAL ERROR: 'caen_libs' 라이브러리를 찾을 수 없습니다. 설치를 확인해주세요.")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load_config(config_file="config_v2.json"):
    """설정 파일을 로드합니다."""
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error(f"설정 파일({config_file})을 찾을 수 없습니다.")
        return None
    except json.JSONDecodeError:
        logging.error(f"설정 파일({config_file})의 JSON 형식이 잘못되었습니다.")
        return None

def discover_methods():
    """CAEN 장비 객체에서 사용 가능한 모든 메서드를 찾아서 출력합니다."""
    config = load_config()
    if not config or 'caen_hv' not in config:
        logging.error("'caen_hv' 설정이 config 파일에 없습니다.")
        return

    hv_config = config['caen_hv']
    device = None
    
    try:
        system_type = getattr(hv.SystemType, hv_config["system_type"])
        link_type = getattr(hv.LinkType, hv_config["link_type"])
        
        logging.info(f"Connecting to CAEN HV system at {hv_config['ip_address']}...")
        device = hv.Device.open(
            system_type, link_type, hv_config["ip_address"],
            hv_config["username"], hv_config["password"]
        )
        logging.info("Connection successful.")

        # --- 핵심 로직: device 객체에서 사용 가능한 모든 속성과 메서드를 가져옵니다 ---
        print("\n" + "="*60)
        print("  Discovering available methods on the CAEN 'Device' object")
        print("="*60)

        available_attributes = dir(device)
        
        public_methods = [attr for attr in available_attributes if not attr.startswith('__') and callable(getattr(device, attr))]
        
        for method_name in sorted(public_methods):
            print(f"- {method_name}")
            
        print("="*60)
        logging.info(f"Found {len(public_methods)} available methods.")
        print("\n[요청]: 위 목록에서 'param', 'list', 'name', 'info' 등이 포함된 함수 이름을 찾아봐 주세요.")
        print("이 결과를 참고하여 매개변수들 기입 하세요")

    except Exception as e:
        logging.error(f"An error occurred: {e}")
    finally:
        if device:
            device.close()
            logging.info("Device connection closed.")

if __name__ == '__main__':
    discover_methods()
