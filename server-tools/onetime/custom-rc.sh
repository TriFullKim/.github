sudo tee -a /etc/skel/.bashrc << 'EOF'
# Custom Func
cudev() {
    export CUDA_VISIBLE_DEVICES="$1"
    echo "CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES"
}

# 사용자 정의 별칭
alias free='free -h'
alias df='df -h'
alias gpustat='gpustat -pu'
alias cda='conda activate'
alias cdd='conda deactivate'
alias tmatch='tmux attach -t'
alias rtop="watch -n 1 'free -h;df -h;gpustat -pu'"

for script in /etc/profile.d/*.sh; do
    if [ -r "$script" ]; then
        source "$script"
    fi
done
EOF


sudo tee /etc/skel/.tmux.conf << 'EOF'

# 프리픽스 키 변경 (Ctrl+a)
unbind C-b
set -g prefix C-a
bind C-a send-prefix

# 마우스 지원
set -g mouse on

# 256 컬러 지원
set -g default-terminal "screen-256color"
set -ga terminal-overrides ",xterm-256color:Tc"

# 히스토리 크기
set -g history-limit 50000

# 인덱스 1부터 시작
set -g base-index 1
setw -g pane-base-index 1

# 창 번호 자동 재정렬
set -g renumber-windows on

# 빠른 키 반응
set -sg escape-time 0

# 설정 리로드
bind r source-file ~/.tmux.conf \; display "설정 리로드!"

# 상태바 설정
set -g status-position bottom
set -g status-interval 5

# 상태바 색상
set -g status-style bg=colour235,fg=colour250
set -g window-status-current-style bg=colour39,fg=colour232,bold
set -g pane-border-style fg=colour240
set -g pane-active-border-style fg=colour39

# 상태바 내용
set -g status-left '#[fg=colour39,bold][#S] '
set -g status-right '#[fg=colour250]%Y-%m-%d %H:%M '

# 활동 알림
setw -g monitor-activity on
set -g visual-activity off

EOF
