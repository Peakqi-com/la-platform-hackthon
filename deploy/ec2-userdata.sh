# 註：這是 docker 版；沒有 docker 或 repo 私有時改用 deploy/runbook_ec2.md 的手動步驟
#!/bin/bash
# EC2 (Ubuntu 24.04) user-data：開機自動裝 Docker 並啟動。當天把 REPO_URL / PUBLIC_HOST 換掉即可。
set -eux
REPO_URL="https://github.com/<org>/ntpc-appraisal-review.git"
export PUBLIC_HOST="$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4).sslip.io"
apt-get update && apt-get install -y ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
cd /opt && git clone "$REPO_URL" app && cd app
# 圖資與 OSRM 資料太大不進 git：從 S3 或 release asset 下載（當天決定）
# aws s3 sync s3://<bucket>/data ./data
echo "PUBLIC_HOST=$PUBLIC_HOST" >> .env
docker compose up -d --build
echo "READY: https://$PUBLIC_HOST"
