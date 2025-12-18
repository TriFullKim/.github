#!/bin/bash
set -e

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

# 현재 사용자를 labshare 그룹에 추가
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

# [4/8] 환경변수 설정 (가장 먼저!)
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
sudo tee "$PROFILE_FILE" << EOF > /dev/null
export PROJECT_ROOT="$PROJECT_ROOT"
export PATH="$INSTALL_DIR:\$PATH"
EOF
echo "  설정 완료"
fi

# 현재 세션에 환경변수 적용
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
sudo tee "$INSTALL_DIR/lab" << 'LABEOF' > /dev/null
#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# PROJECT_ROOT 환경변수 확인
if [ -z "$PROJECT_ROOT" ]; then
    # 환경변수 파일에서 로드 시도
    if [ -f /etc/profile.d/lab-project.sh ]; then
        source /etc/profile.d/lab-project.sh
    fi
    
    # 여전히 없으면 에러
    if [ -z "$PROJECT_ROOT" ]; then
        echo -e "${RED}오류: PROJECT_ROOT 환경변수가 설정되지 않았습니다.${NC}"
        echo "재로그인하거나 다음 명령어를 실행하세요:"
        echo "  source /etc/profile.d/lab-project.sh"
        exit 1
    fi
fi

show_help() {
    echo "사용법: lab <명령> [옵션]"
    echo ""
    echo "명령:"
    echo "  project create -n <이름> [멤버...]   프로젝트 생성"
    echo "  project delete -n <이름>             프로젝트 삭제"
    echo "  project list                         내 프로젝트 목록"
    echo "  project list --all                   전체 프로젝트 목록"
    echo ""
    echo "  member add -p <프로젝트> <사용자>    멤버 추가"
    echo "  member remove -p <프로젝트> <사용자> 멤버 제거"
    echo "  member list -p <프로젝트>            멤버 목록"
    echo ""
    echo "프로젝트 경로: $PROJECT_ROOT"
    echo ""
    echo "예시:"
    echo "  lab project create -n vpr-research user1 user2"
    echo "  lab member add -p vpr-research user3"
    echo "  lab project list"
}

project_create() {
    local name=""
    local members=()

    while [[ $# -gt 0 ]]; do
        case $1 in
            -n|--name) name="$2"; shift 2 ;;
            *) members+=("$1"); shift ;;
        esac
    done

    if [ -z "$name" ]; then
        echo -e "${RED}오류: 프로젝트 이름 필요 (-n)${NC}"
        exit 1
    fi

    local project_dir="$PROJECT_ROOT/$name"
    local group_name="proj_$name"

    if [ -d "$project_dir" ]; then
        echo -e "${RED}오류: 프로젝트 '$name' 이미 존재${NC}"
        exit 1
    fi

    echo -e "${BLUE}프로젝트 생성: $name${NC}"

    sudo groupadd "$group_name" 2>/dev/null || true
    sudo mkdir -p "$project_dir"
    sudo usermod -aG "$group_name" "$USER"
    echo -e "  ${GREEN}+${NC} $USER (생성자)"

    for member in "${members[@]}"; do
        if id "$member" &>/dev/null; then
            sudo usermod -aG "$group_name" "$member"
            echo -e "  ${GREEN}+${NC} $member"
        else
            echo -e "  ${RED}✗${NC} $member (사용자 없음)"
        fi
    done

    sudo chgrp -R "$group_name" "$project_dir"
    sudo chmod -R 2775 "$project_dir"

    echo ""
    echo -e "${GREEN}완료!${NC}"
    echo "경로: $project_dir"
    echo "※ 멤버는 재로그인 후 접근 가능"
}

project_delete() {
    local name=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            -n|--name) name="$2"; shift 2 ;;
            *) shift ;;
        esac
    done

    if [ -z "$name" ]; then
        echo -e "${RED}오류: 프로젝트 이름 필요 (-n)${NC}"
        exit 1
    fi

    local project_dir="$PROJECT_ROOT/$name"
    local group_name="proj_$name"

    if [ ! -d "$project_dir" ]; then
        echo -e "${RED}오류: 프로젝트 '$name' 없음${NC}"
        exit 1
    fi

    # 멤버 확인
    if ! id -nG | grep -qw "$group_name"; then
        echo -e "${RED}오류: '$name' 프로젝트의 멤버가 아닙니다.${NC}"
        exit 1
    fi

    echo -e "${YELLOW}프로젝트 삭제: $name${NC}"
    echo "경로: $project_dir"
    echo ""
    read -p "정말 삭제하시겠습니까? (y/n): " confirm

    if [ "$confirm" != "y" ]; then
        echo "취소됨"
        exit 0
    fi

    sudo rm -rf "$project_dir"
    sudo groupdel "$group_name" 2>/dev/null || true

    echo -e "${GREEN}삭제 완료${NC}"
}

project_list() {
    local show_all=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --all|-a) show_all=true; shift ;;
            *) shift ;;
        esac
    done

    if [ "$show_all" = true ]; then
        echo -e "${BLUE}=== 전체 프로젝트 ===${NC}"
        echo ""
        
        if [ ! -d "$PROJECT_ROOT" ]; then
            echo "프로젝트 디렉토리가 없습니다: $PROJECT_ROOT"
            return
        fi
        
        local found=false
        for dir in "$PROJECT_ROOT"/*/; do
            if [ -d "$dir" ]; then
                found=true
                local name=$(basename "$dir")
                local group="proj_$name"
                local members=$(getent group "$group" 2>/dev/null | cut -d: -f4)
                local size=$(du -sh "$dir" 2>/dev/null | cut -f1)

                echo -e "📁 ${GREEN}$name${NC} ($size)"
                echo "   멤버: ${members:-없음}"
                echo ""
            fi
        done
        
        if [ "$found" = false ]; then
            echo "프로젝트 없음"
        fi
    else
        echo -e "${BLUE}=== 내 프로젝트 ===${NC}"
        echo ""
        
        # 현재 사용자의 그룹에서 proj_ 로 시작하는 것 찾기
        local my_projects=$(id -nG | tr ' ' '\n' | grep '^proj_' | sed 's/proj_//')
        
        if [ -z "$my_projects" ]; then
            echo "참여 중인 프로젝트 없음"
            echo ""
            echo "※ 프로젝트 생성 후 재로그인이 필요합니다."
        else
            for name in $my_projects; do
                local dir="$PROJECT_ROOT/$name"
                if [ -d "$dir" ]; then
                    local size=$(du -sh "$dir" 2>/dev/null | cut -f1)
                    echo -e "📁 ${GREEN}$name${NC} ($size)"
                    echo "   경로: $dir"
                    echo ""
                fi
            done
        fi
    fi
}

member_add() {
    local project=""
    local user=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            -p|--project) project="$2"; shift 2 ;;
            *) user="$1"; shift ;;
        esac
    done

    if [ -z "$project" ]; then
        echo -e "${RED}오류: 프로젝트 이름 필요 (-p)${NC}"
        exit 1
    fi

    if [ -z "$user" ]; then
        echo -e "${RED}오류: 사용자 이름 필요${NC}"
        exit 1
    fi

    local group_name="proj_$project"

    if ! getent group "$group_name" &>/dev/null; then
        echo -e "${RED}오류: 프로젝트 '$project' 없음${NC}"
        exit 1
    fi

    if ! id "$user" &>/dev/null; then
        echo -e "${RED}오류: 사용자 '$user' 없음${NC}"
        exit 1
    fi

    sudo usermod -aG "$group_name" "$user"
    echo -e "${GREEN}$user → $project 추가됨${NC}"
    echo "※ 재로그인 후 접근 가능"
}

member_remove() {
    local project=""
    local user=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            -p|--project) project="$2"; shift 2 ;;
            *) user="$1"; shift ;;
        esac
    done

    if [ -z "$project" ]; then
        echo -e "${RED}오류: 프로젝트 이름 필요 (-p)${NC}"
        exit 1
    fi

    if [ -z "$user" ]; then
        echo -e "${RED}오류: 사용자 이름 필요${NC}"
        exit 1
    fi

    local group_name="proj_$project"

    if ! getent group "$group_name" &>/dev/null; then
        echo -e "${RED}오류: 프로젝트 '$project' 없음${NC}"
        exit 1
    fi

    sudo gpasswd -d "$user" "$group_name"
    echo -e "${GREEN}$user → $project 제거됨${NC}"
}

member_list() {
    local project=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            -p|--project) project="$2"; shift 2 ;;
            *) shift ;;
        esac
    done

    if [ -z "$project" ]; then
        echo -e "${RED}오류: 프로젝트 이름 필요 (-p)${NC}"
        exit 1
    fi

    local group_name="proj_$project"

    if ! getent group "$group_name" &>/dev/null; then
        echo -e "${RED}오류: 프로젝트 '$project' 없음${NC}"
        exit 1
    fi

    echo -e "${BLUE}=== $project 멤버 ===${NC}"
    getent group "$group_name" | cut -d: -f4 | tr ',' '\n' | while read member; do
        if [ -n "$member" ]; then
            echo "  👤 $member"
        fi
    done
}

case "$1" in
    project)
        case "$2" in
            create) shift 2; project_create "$@" ;;
            delete) shift 2; project_delete "$@" ;;
            list) shift 2; project_list "$@" ;;
            *) show_help; exit 1 ;;
        esac
        ;;
    member)
        case "$2" in
            add) shift 2; member_add "$@" ;;
            remove) shift 2; member_remove "$@" ;;
            list) shift 2; member_list "$@" ;;
            *) show_help; exit 1 ;;
        esac
        ;;
    help|--help|-h) show_help ;;
    *) show_help; exit 1 ;;
esac
LABEOF

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
sudo tee "$SUDOERS_FILE" << EOF > /dev/null
%labshare ALL=(ALL) NOPASSWD: /usr/sbin/groupadd proj_*
%labshare ALL=(ALL) NOPASSWD: /usr/sbin/groupdel proj_*
%labshare ALL=(ALL) NOPASSWD: /usr/sbin/usermod -aG proj_* *
%labshare ALL=(ALL) NOPASSWD: /usr/bin/gpasswd -d * proj_*
%labshare ALL=(ALL) NOPASSWD: /bin/mkdir -p $PROJECT_ROOT/*
%labshare ALL=(ALL) NOPASSWD: /bin/chgrp -R proj_* $PROJECT_ROOT/*
%labshare ALL=(ALL) NOPASSWD: /bin/chmod -R 2775 $PROJECT_ROOT/*
%labshare ALL=(ALL) NOPASSWD: /bin/rm -rf $PROJECT_ROOT/*
EOF
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
        # 기존 설정 제거
        sudo sed -i '/#.*프롬프트.*프로젝트/,/^PS1=/d' /etc/skel/.bashrc 2>/dev/null || true
        sudo sed -i '/__get_prompt_path/,/^PS1=/d' /etc/skel/.bashrc 2>/dev/null || true
    fi
fi

if [ "$UPDATE_SKEL" = true ]; then
sudo tee -a /etc/skel/.bashrc << 'BASHRCEOF' > /dev/null

# Lab 프로젝트 환경변수 로드
if [ -f /etc/profile.d/lab-project.sh ]; then
    source /etc/profile.d/lab-project.sh
fi

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

PS1='${CONDA_DEFAULT_ENV:+($CONDA_DEFAULT_ENV)}${debian_chroot:+($debian_chroot)}\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]$(__get_prompt_path)\[\033[00m\]\$ '
BASHRCEOF
echo "  설정 완료"
fi

# [8/8] 기존 사용자 .bashrc 업데이트
echo "[8/8] 기존 사용자 .bashrc 업데이트"
read -p "  기존 사용자에게도 적용하시겠습니까? (y/n): " update_users

if [ "$update_users" = "y" ]; then
    for user in $(awk -F: '$3 >= 1000 && $3 < 65534 {print $1}' /etc/passwd); do
        home_dir=$(eval echo "~$user")
        bashrc="$home_dir/.bashrc"
        
        # lost+found 등 건너뛰기
        if [ "$user" = "nobody" ]; then
            continue
        fi
        
        if [ ! -f "$bashrc" ]; then
            echo "  건너뜀: $user (.bashrc 없음)"
            continue
        fi
        
        # 기존 설정 제거
        sed -i '/#.*프롬프트.*프로젝트/,/^PS1=/d' "$bashrc" 2>/dev/null || true
        sed -i '/__get_prompt_path/,/^PS1=/d' "$bashrc" 2>/dev/null || true
        sed -i '/#.*profile.d.*스크립트/,/^fi$/d' "$bashrc" 2>/dev/null || true
        
        cat << 'BASHRCEOF' >> "$bashrc"

# Lab 프로젝트 환경변수 로드
if [ -f /etc/profile.d/lab-project.sh ]; then
    source /etc/profile.d/lab-project.sh
fi

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

PS1='${CONDA_DEFAULT_ENV:+($CONDA_DEFAULT_ENV)}${debian_chroot:+($debian_chroot)}\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]$(__get_prompt_path)\[\033[00m\]\$ '
BASHRCEOF
        
        # labshare 그룹에 추가
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
echo "  lab member list -p <프로젝트>"
echo "  lab help"
echo ""
echo "※ 적용하려면 재로그인하거나:"
echo "  source /etc/profile.d/lab-project.sh"
echo "  source ~/.bashrc"
echo ""
echo "※ 프로젝트 생성 후 '내 프로젝트'에 표시되려면 재로그인 필요"
