# check_hv_params.py (슬롯 자동 감지 및 값 읽기 검증 최종본)

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
    try:
        with open(config_file, 'r', encoding='utf-8') as f: return json.load(f)
    except Exception as e:
        logging.error(f"설정 파일 로드 오류: {e}"); return None

def verify_parameters():
    config = load_config()
    if not config or 'caen_hv' not in config:
        logging.error("'caen_hv' 설정이 config 파일에 없습니다."); return

    hv_config = config['caen_hv']
    
    # <<< 변경점: config 파일에서 직접 슬롯 목록을 읽어옵니다.
    slots_to_check = [int(s) for s in hv_config.get('crate_map', {}).keys()]
    if not slots_to_check:
        logging.error("설정 파일의 'crate_map'에 슬롯 정보가 없습니다."); return
    
    # 검증할 파라미터 이름 후보 목록
    CANDIDATE_PARAMS = [
        'VMon', 'IMon', 'VMeas', 'IMeas', 'V0Set', 'I0Set', 'Pw', 'Status', 'Trip'
    ]
    
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

        # <<< 변경점: 모든 슬롯에 대해 반복 검사합니다.
        for slot in slots_to_check:
            print("\n" + "="*50)
            print(f"  Verifying parameters for Slot {slot}")
            print("="*50)
            
            found_params = []
            for param_name in CANDIDATE_PARAMS:
                try:
                    # <<< 변경점: 속성 대신 값을 직접 읽어서 존재 여부를 확인합니다.
                    # 성공하면 존재하는 파라미터입니다.
                    device.get_ch_param(slot, [0], param_name)
                    print(f"[  OK  ] Parameter '{param_name}' exists.")
                    found_params.append(param_name)
                except Exception:
                    # 오류가 발생하면 존재하지 않는 파라미터입니다.
                    pass
            
            print(f"\n--- Found {len(found_params)} valid parameters for Slot {slot}: {', '.join(found_params)}")

    except Exception as e:
        logging.error(f"An error occurred: {e}")
    finally:
        if device:
            device.close()
            logging.info("Device connection closed.")

if __name__ == '__main__':
    verify_parameters()