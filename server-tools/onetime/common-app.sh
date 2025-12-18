#!/bin/bash

# 서버 초기 설정 스크립트
# 사용법: sudo ./setup.sh

set -e

echo "=== 시스템 업데이트 ==="
sudo apt update
sudo apt upgrade -y

echo "=== 기본 패키지 설치 ==="
sudo apt install -y \
    build-essential \
    net-tools \
    python3 \
    python3-pip \
    python3-venv \
    vim \
    tmux \
    htop \
    openssh-server \
    ufw \
    curl \
    wget \
    git

echo "=== gpustat 설치 ==="
pip3 install gpustat --break-system-packages

echo "=== Tailscale 설치 ==="
curl -fsSL https://tailscale.com/install.sh | sh

echo "=== SSH 서비스 활성화 ==="
sudo systemctl enable --now ssh


echo "=== Miniconda 다운로드 ==="
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /tmp/miniconda.sh

echo "=== /opt/miniconda 설치 ==="
sudo bash /tmp/miniconda.sh -b -p /opt/miniconda

echo "=== 권한 설정 ==="
sudo chmod -R 755 /opt/miniconda

echo "=== 전역 환경변수 설정 ==="
sudo tee /etc/profile.d/conda.sh << 'EOF'
export PATH="/opt/miniconda/bin:$PATH"
. /opt/miniconda/etc/profile.d/conda.sh
EOF

echo "=== 정리 ==="
rm /tmp/miniconda.sh

echo "=== 완료 ==="

