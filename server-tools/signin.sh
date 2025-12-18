#!/bin/bash
set -e

if [ -z "$1" ]; then
    echo "사용법: $0 <사용자명>"
    exit 1
fi

USERNAME=$1
HOME_DIR="/home/$USERNAME"

echo "=== 사용자 생성: $USERNAME ==="
sudo useradd -m -d "$HOME_DIR" -s /bin/bash "$USERNAME"

echo "=== 비밀번호 설정 ==="
sudo passwd "$USERNAME"

echo "=== 홈 디렉토리 권한 설정 ==="
sudo chmod 755 "$HOME_DIR"

echo "=== labshare 그룹 추가 ==="
sudo usermod -aG labshare "$USERNAME"

echo "=== 완료 ==="
echo "사용자: $USERNAME"
echo "홈 디렉토리: $HOME_DIR (755)"
echo "그룹: $(groups $USERNAME)"
