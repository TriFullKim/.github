# Lab 프로젝트 관리 도구

연구실 프로젝트 디렉토리 및 멤버 관리 도구

## 설치
```bash
sudo ./install.sh
```

## 제거
```bash
sudo ./uninstall.sh
```

## 사용법
```bash
# 프로젝트 생성
lab project create -n <이름> [멤버...]

# 프로젝트 목록
lab project list          # 내 프로젝트
lab project list --all    # 전체 프로젝트

# 프로젝트 삭제
lab project delete -n <이름>

# 멤버 관리
lab member add -p <프로젝트> <사용자>
lab member remove -p <프로젝트> <사용자>
lab member list -p <프로젝트>

# 도움말
lab help
```

## 폴더 구조
```
lab-project/
├── install.sh              # 설치 스크립트
├── uninstall.sh            # 제거 스크립트
├── bin/
│   └── lab                 # lab 명령어
├── profile.d/
│   └── lab-project.sh      # 환경변수
├── sudoers.d/
│   └── lab-project         # sudoers 설정
└── skel/
    └── bashrc-append       # .bashrc 추가 내용
```

## 주의사항

- 프로젝트 생성/삭제/멤버 추가는 해당 프로젝트 멤버만 가능
- 그룹 변경 적용을 위해 재로그인 필요
- labshare 그룹 멤버만 lab 명령어 사용 가능
