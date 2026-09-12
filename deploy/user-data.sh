#!/bin/bash
# EC2 開機腳本（provision.sh 帶入）：只裝系統層的東西，程式與資料由 provision.sh 之後上傳。
# 對應 runbook 第 1 步：Python 3.12、Node 22、Caddy；另加 2 GB swap（t3.medium 跑 next build 保險）。
set -eux
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3.12 python3.12-venv python3-pip git curl unzip rsync debian-keyring debian-archive-keyring apt-transport-https ca-certificates
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
apt-get update && apt-get install -y caddy
if ! swapon --show | grep -q swapfile; then fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab; fi
mkdir -p /opt/app && chown ubuntu:ubuntu /opt/app
