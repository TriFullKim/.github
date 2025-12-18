#!/bin/bash
set -e

if [ -z "$1" ]; then
    echo "사용법: $0 <사용자명>"
    exit 1
fi

USERNAME=$1

echo "=== 사용자 삭제: $USERNAME ==="
echo "홈 디렉토리도 삭제됩니다. 계속하시겠습니까? (y/n)"
read -r confirm

if [ "$confirm" != "y" ]; then
    echo "취소됨"
    exit 0
fi

sudo deluser --remove-home "$USERNAME"

echo "=== 완료 ==="
echo "사용자 $USERNAME 삭제됨"
