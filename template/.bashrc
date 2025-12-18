cudev() {
    export CUDA_VISIBLE_DEVICES="$1"
    echo "CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES"
}

alias free='free -h'
alias df='df -h'
alias gpustat='gpustat -pu'
alias cda='conda activate'
alias cdd='conda deactivate'
alias tmatch='tmux attach -t'
alias rtop="watch -n 1 'free -h;df -h;gpustat -pu'"