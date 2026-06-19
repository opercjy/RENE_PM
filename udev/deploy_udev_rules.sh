#!/bin/bash

# RENE-PM v3.0 Udev Rules Deployment Script

# 설정 변수 (실제 작성한 폴더명과 파일명으로 일치시킬 것)
SOURCE_DIR="./udev"
RULE_FILE="99-rene-sensors.rules"
TARGET_DIR="/etc/udev/rules.d"
TARGET_PATH="$TARGET_DIR/$RULE_FILE"

# 1. 관리자(Root) 권한 검증
# udev 데몬을 제어하고 /etc 경로에 쓰기 위해서는 루트 권한이 필수적입니다.
if [ "$EUID" -ne 0 ]; then
  echo "[오류] 권한이 부족합니다. 'sudo ./deploy_udev_rules.sh' 형태로 실행하십시오."
  exit 1
fi

# 2. 소스 파일 무결성 검증
if [ ! -f "$SOURCE_DIR/$RULE_FILE" ]; then
  echo "[오류] 소스 파일을 찾을 수 없습니다: $SOURCE_DIR/$RULE_FILE"
  exit 1
fi

# 3. 규칙 파일 복사 및 소유권/권한 강제 할당
# 시스템 데몬이 파일을 정상적으로 파싱할 수 있도록 root 소유권과 644(rw-r--r--) 권한을 강제합니다.
echo "[진행] 룰스 파일을 커널 데몬 디렉터리로 복사합니다. ($TARGET_PATH)"
cp "$SOURCE_DIR/$RULE_FILE" "$TARGET_PATH"
chown root:root "$TARGET_PATH"
chmod 644 "$TARGET_PATH"

# 4. Udev 데몬 리로드 및 장치 이벤트 트리거
# 커널 메모리에 로드된 기존 Udev 규칙을 폐기하고 새 규칙을 로드한 뒤,
# 현재 연결된 모든 USB 버스를 스캔하여 uevent를 강제로 다시 발생(Trigger)시킵니다.
echo "[진행] 커널의 Udev 규칙을 다시 로드하고 이벤트를 트리거합니다..."
udevadm control --reload-rules
udevadm trigger

# 5. 백그라운드 적용 대기 및 검증
# 트리거 후 가상 파일 시스템(/dev)에 심볼릭 링크가 노출되기까지의 I/O 지연 시간을 확보합니다.
sleep 1
echo "[완료] 생성된 가상 센서 심볼릭 링크 목록:"
ls -l /dev/sensor_*

exit 0