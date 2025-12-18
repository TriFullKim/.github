#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Lab 프로젝트 관리 도구 설치 ==="
echo ""

# 프로젝트 루트 디렉토리 설정
read -p "프로젝트 디렉토리 경로 [/projects]: " PROJECT_ROOT
PROJECT_ROOT=${PROJECT_ROOT:-/projects}

# lab 명령어 설치 경로
read -p "lab 명령어 설치 경로 [/usr/local/bin]: " INSTALL_DIR
INSTALL_DIR=${INSTALL_DIR:-/usr/local/bin}

echo ""
echo "설정 확인:"
echo "  프로젝트 디렉토리: $PROJECT_ROOT"
echo "  설치 경로: $INSTALL_DIR/lab"
echo ""
read -p "계속하시겠습니까? (y/n): " confirm
if [ "$confirm" != "y" ]; then
    echo "취소됨"
    exit 0
fi

echo ""

# [1/8] labshare 그룹 생성
echo "[1/8] labshare 그룹 생성"
if getent group labshare > /dev/null 2>&1; then
    echo "  이미 존재: labshare"
else
    sudo groupadd labshare
    echo "  생성 완료: labshare"
fi

CURRENT_USER="${SUDO_USER:-$USER}"
if groups "$CURRENT_USER" | grep -q '\blabshare\b'; then
    echo "  $CURRENT_USER 이미 labshare 그룹 멤버"
else
    sudo usermod -aG labshare "$CURRENT_USER"
    echo "  $CURRENT_USER → labshare 그룹 추가됨"
fi

# [2/8] 프로젝트 루트 디렉토리 생성
echo "[2/8] 프로젝트 디렉토리 생성"
if [ -d "$PROJECT_ROOT" ]; then
    echo "  이미 존재: $PROJECT_ROOT"
else
    sudo mkdir -p "$PROJECT_ROOT"
    sudo chmod 755 "$PROJECT_ROOT"
    echo "  생성 완료: $PROJECT_ROOT"
fi

# [3/8] 설치 디렉토리 확인
echo "[3/8] 설치 디렉토리 확인"
if [ ! -d "$INSTALL_DIR" ]; then
    echo "  디렉토리 생성: $INSTALL_DIR"
    sudo mkdir -p "$INSTALL_DIR"
else
    echo "  이미 존재: $INSTALL_DIR"
fi

# [4/8] 환경변수 설정
echo "[4/8] 환경변수 설정"
PROFILE_FILE="/etc/profile.d/lab-project.sh"
INSTALL_PROFILE=true

if [ -f "$PROFILE_FILE" ]; then
    echo "  이미 존재: $PROFILE_FILE"
    read -p "  덮어쓰시겠습니까? (y/n): " overwrite_profile
    if [ "$overwrite_profile" != "y" ]; then
        echo "  건너뜀"
        INSTALL_PROFILE=false
    fi
fi

if [ "$INSTALL_PROFILE" = true ]; then
    sed "s|{{PROJECT_ROOT}}|$PROJECT_ROOT|g; s|{{INSTALL_DIR}}|$INSTALL_DIR|g" \
        "$SCRIPT_DIR/profile.d/lab-project.sh" | sudo tee "$PROFILE_FILE" > /dev/null
    echo "  설정 완료"
fi

export PROJECT_ROOT="$PROJECT_ROOT"
export PATH="$INSTALL_DIR:$PATH"

# [5/8] lab 명령어 설치
echo "[5/8] lab 명령어 설치"
INSTALL_LAB=true
if [ -f "$INSTALL_DIR/lab" ]; then
    read -p "  이미 존재합니다. 덮어쓰시겠습니까? (y/n): " overwrite
    if [ "$overwrite" != "y" ]; then
        echo "  건너뜀"
        INSTALL_LAB=false
    fi
fi

if [ "$INSTALL_LAB" = true ]; then
    sudo cp "$SCRIPT_DIR/bin/lab" "$INSTALL_DIR/lab"
    sudo chmod +x "$INSTALL_DIR/lab"
    echo "  설치 완료"
fi

# [6/8] sudoers 설정
echo "[6/8] sudoers 설정"
SUDOERS_FILE="/etc/sudoers.d/lab-project"
INSTALL_SUDOERS=true

if [ -f "$SUDOERS_FILE" ]; then
    echo "  이미 존재: $SUDOERS_FILE"
    read -p "  덮어쓰시겠습니까? (y/n): " overwrite_sudoers
    if [ "$overwrite_sudoers" != "y" ]; then
        echo "  건너뜀"
        INSTALL_SUDOERS=false
    fi
fi

if [ "$INSTALL_SUDOERS" = true ]; then
    sed "s|{{PROJECT_ROOT}}|$PROJECT_ROOT|g" \
        "$SCRIPT_DIR/sudoers.d/lab-project" | sudo tee "$SUDOERS_FILE" > /dev/null
    sudo chmod 440 "$SUDOERS_FILE"
    echo "  설정 완료"
fi

# [7/8] /etc/skel/.bashrc 업데이트
echo "[7/8] /etc/skel/.bashrc 업데이트"
UPDATE_SKEL=true

if grep -q "__get_prompt_path" /etc/skel/.bashrc 2>/dev/null; then
    echo "  이미 설정됨"
    read -p "  덮어쓰시겠습니까? (y/n): " overwrite_skel
    if [ "$overwrite_skel" != "y" ]; then
        echo "  건너뜀"
        UPDATE_SKEL=false
    else
        sudo sed -i '/#.*Lab.*프로젝트/,/^PS1=/d' /etc/skel/.bashrc 2>/dev/null || true
        sudo sed -i '/__get_prompt_path/,/^PS1=/d' /etc/skel/.bashrc 2>/dev/null || true
    fi
fi

if [ "$UPDATE_SKEL" = true ]; then
    cat "$SCRIPT_DIR/skel/bashrc-append" | sudo tee -a /etc/skel/.bashrc > /dev/null
    echo "  설정 완료"
fi

# [8/8] 기존 사용자 .bashrc 업데이트
echo "[8/8] 기존 사용자 .bashrc 업데이트"
read -p "  기존 사용자에게도 적용하시겠습니까? (y/n): " update_users

if [ "$update_users" = "y" ]; then
    for user in $(awk -F: '$3 >= 1000 && $3 < 65534 {print $1}' /etc/passwd); do
        home_dir=$(eval echo "~$user")
        bashrc="$home_dir/.bashrc"
        
        if [ "$user" = "nobody" ]; then
            continue
        fi
        
        if [ ! -f "$bashrc" ]; then
            echo "  건너뜀: $user (.bashrc 없음)"
            continue
        fi
        
        sed -i '/#.*Lab.*프로젝트/,/^PS1=/d' "$bashrc" 2>/dev/null || true
        sed -i '/__get_prompt_path/,/^PS1=/d' "$bashrc" 2>/dev/null || true
        
        cat "$SCRIPT_DIR/skel/bashrc-append" >> "$bashrc"
        
        if ! groups "$user" 2>/dev/null | grep -q '\blabshare\b'; then
            sudo usermod -aG labshare "$user"
            echo "  업데이트: $user (+labshare 그룹)"
        else
            echo "  업데이트: $user"
        fi
    done
else
    echo "  건너뜀"
fi

echo ""
echo "=== 설치 완료 ==="
echo ""
echo "설정:"
echo "  프로젝트 경로: $PROJECT_ROOT"
echo "  명령어 경로: $INSTALL_DIR/lab"
echo "  환경변수: /etc/profile.d/lab-project.sh"
echo "  sudoers: /etc/sudoers.d/lab-project"
echo ""
echo "사용법:"
echo "  lab project create -n <이름> [멤버...]"
echo "  lab project list"
echo "  lab project list --all"
echo "  lab member add -p <프로젝트> <사용자>"
echo "  lab help"
echo ""
echo "※ 적용하려면 재로그인하거나:"
echo "  source /etc/profile.d/lab-project.sh"
echo "  source ~/.bashrc"
