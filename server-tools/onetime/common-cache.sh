#!/bin/bash
set -e

CACHE_ROOT="/home/shared_cache"

echo "=== 공유 캐시 디렉토리 생성 ==="
sudo mkdir -p "$CACHE_ROOT"/{conda_pkgs,conda_envs,huggingface,torch,pip,kaggle}

echo "=== 공유 그룹 생성 ==="
sudo groupadd -f labshare

echo "=== 권한 설정 ==="
sudo chgrp -R labshare "$CACHE_ROOT"
sudo chmod -R 2775 "$CACHE_ROOT"

echo "=== 환경변수 설정 ==="
sudo tee /etc/profile.d/shared_cache.sh << EOF
# Conda
export CONDA_PKGS_DIRS="$CACHE_ROOT/conda_pkgs"
export CONDA_ENVS_DIRS="$CACHE_ROOT/conda_envs"

# Hugging Face
export HF_HOME="$CACHE_ROOT/huggingface"
export HUGGINGFACE_HUB_CACHE="$CACHE_ROOT/huggingface/hub"
export TRANSFORMERS_CACHE="$CACHE_ROOT/huggingface/transformers"

# PyTorch
export TORCH_HOME="$CACHE_ROOT/torch"

# pip
export PIP_CACHE_DIR="$CACHE_ROOT/pip"

# Kaggle
export KAGGLE_CACHE_DIR="$CACHE_ROOT/kaggle"
EOF

echo "condarc. 설정"
sudo tee /opt/miniconda/.condarc << EOF
pkgs_dirs:
  - $CACHE_ROOT/conda_pkgs
envs_dirs:
  - $CACHE_ROOT/conda_envs
channels:
  - conda-forge
  - defaults
auto_activate_base: false
EOF

echo "=== 완료 ==="
echo "사용자를 labshare 그룹에 추가하세요:"
echo "  sudo usermod -aG labshare <사용자명>"
