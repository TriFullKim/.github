#!/bin/bash
set -e

echo "=== Lab 프로젝트 관리 도구 제거 ==="
echo ""

if [ -f /etc/profile.d/lab-project.sh ]; then
    source /etc/profile.d/lab-project.sh
fi

PROJECT_ROOT="${PROJECT_ROOT:-/projects}"
INSTALL_DIR="${INSTALL_DIR:-/usr/local/bin}"

echo "현재 설정:"
echo "  프로젝트 디렉토리: $PROJECT_ROOT"
echo "  명령어 경로: $INSTALL_DIR/lab"
echo ""

read -p "제거를 진행하시겠습니까? (y/n): " confirm
if [ "$confirm" != "y" ]; then
    echo "취소됨"
    exit 0
fi

echo ""

echo "[1/6] lab 명령어 제거"
if [ -f "$INSTALL_DIR/lab" ]; then
    sudo rm -f "$INSTALL_DIR/lab"
    echo "  제거 완료: $INSTALL_DIR/lab"
else
    echo "  없음: $INSTALL_DIR/lab"
fi

echo "[2/6] 환경변수 파일 제거"
if [ -f /etc/profile.d/lab-project.sh ]; then
    sudo rm -f /etc/profile.d/lab-project.sh
    echo "  제거 완료: /etc/profile.d/lab-project.sh"
else
    echo "  없음: /etc/profile.d/lab-project.sh"
fi

echo "[3/6] sudoers 파일 제거"
if [ -f /etc/sudoers.d/lab-project ]; then
    sudo rm -f /etc/sudoers.d/lab-project
    echo "  제거 완료: /etc/sudoers.d/lab-project"
else
    echo "  없음: /etc/sudoers.d/lab-project"
fi

echo "[4/6] /etc/skel/.bashrc 정리"
if grep -q "__get_prompt_path" /etc/skel/.bashrc 2>/dev/null; then
    sudo sed -i '/#.*Lab.*프로젝트/,/^PS1=/d' /etc/skel/.bashrc 2>/dev/null || true
    sudo sed -i '/__get_prompt_path/,/^PS1=/d' /etc/skel/.bashrc 2>/dev/null || true
    sudo sed -i '/lab-project\.sh/d' /etc/skel/.bashrc 2>/dev/null || true
    echo "  정리 완료: /etc/skel/.bashrc"
else
    echo "  없음: /etc/skel/.bashrc"
fi

echo "[5/6] 기존 사용자 .bashrc 정리"
read -p "  기존 사용자 .bashrc도 정리하시겠습니까? (y/n): " clean_users

if [ "$clean_users" = "y" ]; then
    for user in $(awk -F: '$3 >= 1000 && $3 < 65534 {print $1}' /etc/passwd); do
        home_dir=$(eval echo "~$user")
        bashrc="$home_dir/.bashrc"
        
        if [ "$user" = "nobody" ]; then
            continue
        fi
        
        if [ ! -f "$bashrc" ]; then
            continue
        fi
        
        if grep -q "__get_prompt_path" "$bashrc" 2>/dev/null; then
            sed -i '/#.*Lab.*프로젝트/,/^PS1=/d' "$bashrc" 2>/dev/null || true
            sed -i '/__get_prompt_path/,/^PS1=/d' "$bashrc" 2>/dev/null || true
            sed -i '/lab-project\.sh/d' "$bashrc" 2>/dev/null || true
            echo "  정리: $user"
        fi
    done
else
    echo "  건너뜀"
fi

echo "[6/6] 프로젝트 데이터 처리"
echo ""
echo "  주의: 프로젝트 디렉토리와 그룹은 자동으로 삭제하지 않습니다."
echo ""

read -p "  프로젝트 디렉토리를 삭제하시겠습니까? ($PROJECT_ROOT) (y/n): " delete_projects

if [ "$delete_projects" = "y" ]; then
    read -p "  정말 삭제하시겠습니까? 모든 프로젝트 데이터가 삭제됩니다! (yes를 입력): " confirm_delete
    if [ "$confirm_delete" = "yes" ]; then
        sudo rm -rf "$PROJECT_ROOT"
        echo "  삭제 완료: $PROJECT_ROOT"
        
        echo "  프로젝트 그룹 삭제 중..."
        for group in $(getent group | grep '^proj_' | cut -d: -f1); do
            sudo groupdel "$group" 2>/dev/null || true
            echo "    삭제: $group"
        done
    else
        echo "  취소됨"
    fi
else
    echo "  건너뜀"
    echo ""
    echo "  수동 삭제가 필요하면:"
    echo "    sudo rm -rf $PROJECT_ROOT"
    echo "    sudo groupdel proj_<프로젝트명>"
fi

echo ""
read -p "  labshare 그룹을 삭제하시겠습니까? (y/n): " delete_labshare

if [ "$delete_labshare" = "y" ]; then
    if getent group labshare > /dev/null 2>&1; then
        sudo groupdel labshare
        echo "  삭제 완료: labshare 그룹"
    else
        echo "  없음: labshare 그룹"
    fi
else
    echo "  건너뜀"
fi

echo ""
echo "=== 제거 완료 ==="
echo ""
echo "※ 변경사항 적용을 위해 재로그인하세요."
