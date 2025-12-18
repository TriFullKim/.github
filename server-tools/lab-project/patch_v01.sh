#!/bin/bash
set -e

echo "=== Lab 프로젝트 도구 패치 ==="
echo ""

# 환경변수 로드
if [ -f /etc/profile.d/lab-project.sh ]; then
    source /etc/profile.d/lab-project.sh
fi

INSTALL_DIR="${INSTALL_DIR:-/usr/local/bin}"

# [1/3] lab 명령어 패치 (project_delete 수정)
echo "[1/3] lab 명령어 패치"

if [ ! -f "$INSTALL_DIR/lab" ]; then
    echo "  오류: $INSTALL_DIR/lab 없음"
    exit 1
fi

# project_delete 함수 교체
sudo sed -i '/^project_delete()/,/^}/c\
project_delete() {\
    local name=""\
\
    while [[ $# -gt 0 ]]; do\
        case $1 in\
            -n|--name) name="$2"; shift 2 ;;\
            *) shift ;;\
        esac\
    done\
\
    if [ -z "$name" ]; then\
        echo -e "${RED}오류: 프로젝트 이름 필요 (-n)${NC}"\
        exit 1\
    fi\
\
    local project_dir="$PROJECT_ROOT/$name"\
    local group_name="proj_$name"\
\
    if ! getent group "$group_name" \\&>/dev/null; then\
        echo -e "${RED}오류: 프로젝트 '"'"'$name'"'"' 없음${NC}"\
        exit 1\
    fi\
\
    if ! id -nG | grep -qw "$group_name"; then\
        echo -e "${RED}오류: '"'"'$name'"'"' 프로젝트의 멤버가 아닙니다.${NC}"\
        exit 1\
    fi\
\
    echo -e "${YELLOW}프로젝트 삭제: $name${NC}"\
    echo "그룹: $group_name"\
    echo ""\
    echo -e "${BLUE}※ 폴더는 삭제되지 않습니다: $project_dir${NC}"\
    echo ""\
    read -p "정말 삭제하시겠습니까? (y/n): " confirm\
\
    if [ "$confirm" != "y" ]; then\
        echo "취소됨"\
        exit 0\
    fi\
\
    sudo groupdel "$group_name" 2>/dev/null || true\
\
    echo -e "${GREEN}삭제 완료${NC}"\
    echo ""\
    echo "폴더를 수동으로 삭제하려면:"\
    echo "  sudo rm -rf $project_dir"\
}' "$INSTALL_DIR/lab"

echo "  완료: project_delete 수정됨"

# [2/3] /etc/skel/.bashrc 패치
echo "[2/3] /etc/skel/.bashrc 패치"

# 기존 설정 제거
sudo sed -i '/#.*Lab.*프로젝트/,/^PS1=/d' /etc/skel/.bashrc 2>/dev/null || true
sudo sed -i '/__get_prompt_path/,/^PS1=/d' /etc/skel/.bashrc 2>/dev/null || true
sudo sed -i '/__get_conda_env/,/^$/d' /etc/skel/.bashrc 2>/dev/null || true
sudo sed -i '/lab-project\.sh/d' /etc/skel/.bashrc 2>/dev/null || true
sudo sed -i '/changeps1/d' /etc/skel/.bashrc 2>/dev/null || true

# 새 설정 추가
sudo tee -a /etc/skel/.bashrc << 'EOF' > /dev/null

# Lab 프로젝트 환경변수 로드
if [ -f /etc/profile.d/lab-project.sh ]; then
    source /etc/profile.d/lab-project.sh
fi

# conda 자체 프롬프트 비활성화
if [ -n "$CONDA_EXE" ]; then
    conda config --set changeps1 false 2>/dev/null
fi

# conda 환경 이름 추출 (경로면 basename, 아니면 그대로)
__get_conda_env() {
    if [ -n "$CONDA_DEFAULT_ENV" ]; then
        echo "($(basename "$CONDA_DEFAULT_ENV"))"
    fi
}

# 프롬프트에 현재 프로젝트 표시
__get_prompt_path() {
    local current_path="$PWD"
    
    # 프로젝트 디렉토리
    if [ -n "$PROJECT_ROOT" ] && [[ "$current_path" == "$PROJECT_ROOT"/* ]]; then
        local depth=$(echo "$PROJECT_ROOT" | tr -cd '/' | wc -c)
        local field=$((depth + 2))
        local project_name=$(echo "$current_path" | cut -d'/' -f$field)
        local sub_path=$(echo "$current_path" | sed "s|^$PROJECT_ROOT/$project_name||")
        if [ -z "$sub_path" ]; then
            echo "<$project_name>"
        else
            echo "<$project_name>$sub_path"
        fi
    # 홈 디렉토리
    elif [[ "$current_path" == "$HOME"* ]]; then
        echo "${current_path/#$HOME/\~}"
    else
        echo "$current_path"
    fi
}

PS1='$(__get_conda_env)${debian_chroot:+($debian_chroot)}\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]$(__get_prompt_path)\[\033[00m\]\$ '
EOF

echo "  완료: /etc/skel/.bashrc 업데이트됨"

# [3/3] 기존 사용자 .bashrc 패치
echo "[3/3] 기존 사용자 .bashrc 패치"
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
        
        # 기존 설정 제거
        sed -i '/#.*Lab.*프로젝트/,/^PS1=/d' "$bashrc" 2>/dev/null || true
        sed -i '/__get_prompt_path/,/^PS1=/d' "$bashrc" 2>/dev/null || true
        sed -i '/__get_conda_env/,/^$/d' "$bashrc" 2>/dev/null || true
        sed -i '/lab-project\.sh/d' "$bashrc" 2>/dev/null || true
        sed -i '/changeps1/d' "$bashrc" 2>/dev/null || true
        
        # 새 설정 추가
        cat << 'EOF' >> "$bashrc"

# Lab 프로젝트 환경변수 로드
if [ -f /etc/profile.d/lab-project.sh ]; then
    source /etc/profile.d/lab-project.sh
fi

# conda 자체 프롬프트 비활성화
if [ -n "$CONDA_EXE" ]; then
    conda config --set changeps1 false 2>/dev/null
fi

# conda 환경 이름 추출 (경로면 basename, 아니면 그대로)
__get_conda_env() {
    if [ -n "$CONDA_DEFAULT_ENV" ]; then
        echo "($(basename "$CONDA_DEFAULT_ENV"))"
    fi
}

# 프롬프트에 현재 프로젝트 표시
__get_prompt_path() {
    local current_path="$PWD"
    
    # 프로젝트 디렉토리
    if [ -n "$PROJECT_ROOT" ] && [[ "$current_path" == "$PROJECT_ROOT"/* ]]; then
        local depth=$(echo "$PROJECT_ROOT" | tr -cd '/' | wc -c)
        local field=$((depth + 2))
        local project_name=$(echo "$current_path" | cut -d'/' -f$field)
        local sub_path=$(echo "$current_path" | sed "s|^$PROJECT_ROOT/$project_name||")
        if [ -z "$sub_path" ]; then
            echo "<$project_name>"
        else
            echo "<$project_name>$sub_path"
        fi
    # 홈 디렉토리
    elif [[ "$current_path" == "$HOME"* ]]; then
        echo "${current_path/#$HOME/\~}"
    else
        echo "$current_path"
    fi
}

PS1='$(__get_conda_env)${debian_chroot:+($debian_chroot)}\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]$(__get_prompt_path)\[\033[00m\]\$ '
EOF
        echo "  업데이트: $user"
    done
else
    echo "  건너뜀"
fi

echo ""
echo "=== 패치 완료 ==="
echo ""
echo "변경사항:"
echo "  - project_delete: 폴더 삭제 안 함, 그룹만 삭제"
echo "  - PS1: conda 환경 이름만 표시 (경로 X)"
echo "  - conda changeps1 비활성화"
echo ""
echo "※ 적용하려면:"
echo "  source ~/.bashrc"
