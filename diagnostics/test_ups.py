# diagnostics/test_ups.py

import subprocess

def test_ups():
    print("🔋 APC UPS 데몬(apcaccess) 정밀 진단 시작...")
    try:
        output = subprocess.check_output(['apcaccess'], text=True, timeout=2)
        print("✅ apcaccess 명령 실행 성공.\n")
        
        status, linev, bcharge, timeleft = "N/A", "0", "0", "0"
        
        for line in output.split('\n'):
            if line.startswith('STATUS '): status = line.split(':', 1)[1].strip()
            elif line.startswith('LINEV '): linev = line.split(':', 1)[1].strip().split()[0]
            elif line.startswith('BCHARGE '): bcharge = line.split(':', 1)[1].strip().split()[0]
            elif line.startswith('TIMELEFT '): timeleft = line.split(':', 1)[1].strip().split()[0]
            
        print(f"▶ STATUS: {status}")
        print(f"▶ LINEV: {linev} V")
        print(f"▶ BCHARGE: {bcharge} %")
        print(f"▶ TIMELEFT: {timeleft} Minutes")
        
        print("\n✅ 진단 완료.")
    except FileNotFoundError:
        print("❌ 'apcaccess' 명령을 찾을 수 없습니다. apcupsd 데몬이 설치되었는지 확인하십시오.")
    except Exception as e:
        print(f"❌ 진단 실패: {e}")

if __name__ == "__main__":
    test_ups()