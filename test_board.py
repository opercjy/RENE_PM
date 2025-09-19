import sys
import logging
from enum import IntFlag
from caen_libs import caenhvwrapper as hv

# --- 로깅 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ==============================================================================
#               § 제공된 소스를 기반으로 한 상태 디코딩 유틸리티 §
# ==============================================================================

# ==============================================================================
#               § 제공된 소스를 기반으로 한 상태 디코딩 유틸리티 (확장판) §
# ==============================================================================

# --- 보드 상태 (BDSTATUS) 정의 ---
class _BdStatusDefault(IntFlag):
    PW_FAIL     = 0x0001; FW_CHKERR   = 0x0002; HVCAL_ERR   = 0x0004
    TEMP_ERR    = 0x0008; UNDER_TEMP  = 0x0010; OVER_TEMP   = 0x0020
class _BdStatusN1470(IntFlag):
    CH0_ALARM   = 0x0001; CH1_ALARM   = 0x0002; CH2_ALARM   = 0x0004
    CH3_ALARM   = 0x0008; PW_FAIL     = 0x0010; OVER_POWER  = 0x0020; HV_CLK_FAIL = 0x0040
class _BdStatusDT55XXE(IntFlag):
    ALARMED     = 0x0001
class _BdStatusSMARTHV(IntFlag):
    PW_FAIL     = 0x0001; CAL_ERR     = 0x0002; INTERLOCK   = 0x0004; TEMP_ERR    = 0x0008

# --- 채널 상태 (CHSTATUS) 정의 ---
class _ChStatusDefault(IntFlag):
    ON          = 0x0001; RAMP_UP     = 0x0002; RAMP_DOWN   = 0x0004; OVERCURRENT = 0x0008
    OVERVOLTAGE = 0x0010; UNDERVOLTAGE= 0x0020; EXT_TRIP    = 0x0040; MAX_V       = 0x0080
    EXT_DISABLE = 0x0100; INT_TRIP    = 0x0200; CAL_ERROR   = 0x0400; UNPLUGGED   = 0x0800
class _ChStatusSY4527(IntFlag):
    ON          = 0x0001; RAMP_UP     = 0x0002; RAMP_DOWN   = 0x0004; OVERCURRENT = 0x0008
    OVERVOLTAGE = 0x0010; UNDERVOLTAGE= 0x0020; EXT_TRIP    = 0x0040; MAX_V       = 0x0080
    EXT_DISABLE = 0x0100; INT_TRIP    = 0x0200; CAL_ERROR   = 0x0400; UNPLUGGED   = 0x0800
    UNC         = 0x1000; OVV_PROT    = 0x2000; PWR_FAIL    = 0x4000; TEMP_FAIL   = 0x8000
class _ChStatusN1470(IntFlag):
    ON          = 0x0001; RAMP_UP     = 0x0002; RAMP_DOWN   = 0x0004; OVERCURRENT = 0x0008
    OVERVOLTAGE = 0x0010; UNDERVOLTAGE= 0x0020; MAX_V       = 0x0040; TRIPPED     = 0x0080
    OVP         = 0x0100; OVT         = 0x0200; DISABLED    = 0x0400; KILL        = 0x0800
    INTERLOCK   = 0x1000; CAL_ERROR   = 0x2000
class _ChStatusV65XX(IntFlag):
    ON          = 0x0001; RAMP_UP     = 0x0002; RAMP_DOWN   = 0x0004; OVERCURRENT = 0x0008
    OVERVOLTAGE = 0x0010; UNDERVOLTAGE= 0x0020; I_MAX       = 0x0040; MAX_V       = 0x0080
    TRIP        = 0x0100; OVP         = 0x0200; OVT         = 0x0400; DISABLED    = 0x0800
    INTERLOCK   = 0x1000; UNCAL       = 0x2000
class _ChStatusDT55XXE(IntFlag):
    ON          = 0x0001; RAMP_UP     = 0x0002; RAMP_DOWN   = 0x0004; OVERCURRENT = 0x0008
    OVERVOLTAGE = 0x0010; UNDERVOLTAGE= 0x0020; MAX_V       = 0x0040; TRIPPED     = 0x0080
    MAX_POWER   = 0x0100; TEMP_WARN   = 0x0200; DISABLED    = 0x0400; KILL        = 0x0800
    INTERLOCK   = 0x1000; CAL_ERROR   = 0x2000
class _ChStatusSMARTHV(IntFlag):
    ON          = 0x0001; RAMP_UP     = 0x0002; RAMP_DOWN   = 0x0004; OVERCURRENT = 0x0008
    OVERVOLTAGE = 0x0010; UNDERVOLTAGE= 0x0020; TRIPPED     = 0x0040; OVP         = 0x0080
    TEMP_WARN   = 0x0100; OVT         = 0x0200; KILL        = 0x0400; INTERLOCK   = 0x0800
    DISABLED    = 0x1000; COMM_FAIL   = 0x2000; LOCK        = 0x4000; MAX_V       = 0x8000
    CAL_ERROR   = 0x10000

# --- 시스템 타입별 상태 클래스 매핑 (확장) ---
_BD_STATUS_TYPE_MAP = {
    hv.SystemType.N1470:   _BdStatusN1470,
    hv.SystemType.DT55XXE: _BdStatusDT55XXE,
    hv.SystemType.SMARTHV: _BdStatusSMARTHV,
}

_CH_STATUS_TYPE_MAP = {
    hv.SystemType.SY4527:  _ChStatusSY4527,
    hv.SystemType.SY5527:  _ChStatusSY4527, # SY5527은 SY4527과 동일한 상태 코드 사용
    hv.SystemType.R6060:   _ChStatusSY4527, # R6060은 SY4527과 동일한 상태 코드 사용
    hv.SystemType.V65XX:   _ChStatusV65XX,
    hv.SystemType.N1470:   _ChStatusN1470,
    hv.SystemType.DT55XXE: _ChStatusDT55XXE,
    hv.SystemType.SMARTHV: _ChStatusSMARTHV,
}

def decode_status_flags(system_type, status_type, value: int) -> list[str]:
    """정수 값(bitmask)을 상태 플래그 문자열 리스트로 변환합니다."""
    if status_type == 'CHSTATUS':
        status_class = _CH_STATUS_TYPE_MAP.get(system_type, _ChStatusDefault)
    elif status_type == 'BDSTATUS':
        status_class = _BD_STATUS_TYPE_MAP.get(system_type, _BdStatusDefault)
    else:
        return [str(value)]

    if value == 0:
        return ["OK"]
        
    flags = [flag.name for flag in status_class if value & flag]
    return flags if flags else ["UNKNOWN_STATUS_CODE"]

# ==============================================================================
#                             § CAEN HV 시스템 탐색기 §
# ==============================================================================

class CaenHVExplorer:
    """CAEN 고전압 시스템을 탐색하고 모든 정보를 출력하는 클래스"""

    def __init__(self, config):
        self.config = config
        self.device = None

    def connect(self):
        try:
            system_type = getattr(hv.SystemType, self.config["system_type"])
            link_type = getattr(hv.LinkType, self.config["link_type"])
            logging.info(f"Connecting to CAEN HV at {self.config['ip_address']}...")
            self.device = hv.Device.open(
                system_type, link_type, self.config["ip_address"],
                self.config["username"], self.config["password"]
            )
            logging.info("✅ Successfully connected.")
            return True
        except Exception as e:
            logging.error(f"❌ Failed to connect: {e}")
            return False

    def disconnect(self):
        if self.device:
            logging.info("Disconnecting from CAEN HV system...")
            self.device.close()
            self.device = None
            logging.info("⏹️  Disconnected.")

    def explore_crate(self):
        """크레이트 전체를 탐색하며 발견된 모든 보드와 채널의 정보를 출력합니다."""
        if not self.device:
            logging.error("Not connected. Please connect first.")
            return

        try:
            # get_crate_map은 Board 객체의 튜플을 반환합니다.
            boards = self.device.get_crate_map()
            num_found_boards = len([b for b in boards if b is not None])
            logging.info(f"Crate scan complete. Found {num_found_boards} active board(s).")
            print("\n" + "="*80)

            for slot, board in enumerate(boards):
                # 슬롯에 보드가 장착되어 있는 경우에만 처리
                if board:
                    print(f"✅ BOARD in Slot #{slot}: {board.model} (S/N: {board.serial_number})")
                    print(f"   Description: {board.description}")
                    print(f"   Firmware: {board.fw_version}, Channels: {board.n_channel}")
                    print("-" * 80)

                    # --- 1. 보드 레벨 파라미터 탐색 및 출력 ---
                    print("   Board-Level Parameters:")
                    try:
                        bd_param_names = self.device.get_bd_param_info(slot)
                        for name in bd_param_names:
                            value = self.device.get_bd_param([slot], name)[0]
                            if name == 'BDSTATUS':
                                decoded_flags = decode_status_flags(self.device.system_type, 'BDSTATUS', value)
                                print(f"     - {name:<12}: {value} -> {decoded_flags}")
                            else:
                                print(f"     - {name:<12}: {value}")
                    except Exception as e:
                        print(f"     Could not retrieve board parameters. Error: {e}")
                    
                    print("-" * 80)

                    # --- 2. 채널 레벨 파라미터 탐색 및 출력 ---
                    print("   Channel-Level Parameters:")
                    try:
                        # 채널 0을 기준으로 파라미터 목록을 가져옵니다. (보통 모든 채널이 동일)
                        ch_param_names = self.device.get_ch_param_info(slot, 0)
                        ch_list = list(range(board.n_channel))

                        for name in ch_param_names:
                            values = self.device.get_ch_param(slot, ch_list, name)
                            
                            # CHSTATUS는 특별히 디코딩하여 출력합니다.
                            if name == 'CHSTATUS':
                                print(f"     - {name:<12}:")
                                for i, val in enumerate(values):
                                    decoded = decode_status_flags(self.device.system_type, 'CHSTATUS', val)
                                    print(f"         Ch {i:02d}: {val:<5} -> {decoded}")
                            else:
                                # 다른 파라미터들은 값 리스트를 그대로 출력합니다.
                                print(f"     - {name:<12}: {values}")
                    except Exception as e:
                         print(f"     Could not retrieve channel parameters. Error: {e}")

                    print("="*80 + "\n")

        except Exception as e:
            logging.error(f"🔥 An error occurred during exploration: {e}")

# ==============================================================================
#                                § 스크립트 실행 §
# ==============================================================================
if __name__ == "__main__":
    # ❗ 사용자의 환경에 맞게 이 부분을 수정하세요.
    config = {
        "system_type": "SY4527",
        "link_type": "TCPIP",
        "ip_address": "192.168.0.39",
        "username": "admin",
        "password": "admin"
    }

    explorer = CaenHVExplorer(config)
    if explorer.connect():
        try:
            explorer.explore_crate()
        finally:
            explorer.disconnect()