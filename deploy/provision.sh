#!/usr/bin/env bash
# 一鍵佈建：在目前 AWS 憑證的帳號開一台 EC2，把本專案（＋data/）送上去並起服務，最後印出 https://<IP>.sslip.io。
# 對應 deploy/runbook_ec2.md 第 1–5 步；可重複執行（已存在的資源直接沿用）。
#
#   ./deploy/provision.sh                 # 全部：建資源 → 上傳 → 遠端安裝 → 健康檢查
#   ./deploy/provision.sh --sync-only     # 只重新上傳程式並重啟（EC2 已在）
#   DATA_TGZ=~/ntpc-data.tgz ./deploy/provision.sh   # 指定資料包；沒給就打包本機 data/（沒有 data/ 就略過）
#
# 可調環境變數：NAME（資源名前綴，預設 ntpc）、INSTANCE_TYPE（t3.medium）、REGION（aws configure 的 region）、
#               BEDROCK_MODEL_ID（預設 us.anthropic.claude-sonnet-4-5-20250929-v1:0）、ANTHROPIC_API_KEY（有給就改走 anthropic）、
#               SSH_CIDR（預設本機公網 IP/32）、KEY_FILE（~/.ssh/<NAME>-key.pem）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME="${NAME:-ntpc}"
REGION="${REGION:-$(aws configure get region || echo us-west-2)}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.medium}"
BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-us.anthropic.claude-sonnet-4-5-20250929-v1:0}"
KEY_NAME="${NAME}-key"
KEY_FILE="${KEY_FILE:-$HOME/.ssh/${KEY_NAME}.pem}"
SG_NAME="${NAME}-web"
ROLE_NAME="${NAME}-ec2-bedrock"
TAG_NAME="${NAME}-appraisal"
SYNC_ONLY=0
[[ "${1:-}" == "--sync-only" ]] && SYNC_ONLY=1
export AWS_DEFAULT_REGION="$REGION"

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
aws_q() { aws --output text --query "$@"; }

# ---------- 0. 憑證與區域 ----------
log "帳號與區域"
aws sts get-caller-identity --output table
case "$REGION" in us-east-1|us-west-2) ;; *) echo "競賽規範：區域須為 us-east-1 或 us-west-2（目前 ${REGION}）"; exit 1;; esac

# ---------- 1. 金鑰對 ----------
log "金鑰對 $KEY_NAME"
if ! aws ec2 describe-key-pairs --key-names "$KEY_NAME" >/dev/null 2>&1; then
  aws_q 'KeyMaterial' ec2 create-key-pair --key-name "$KEY_NAME" --key-type ed25519 > "$KEY_FILE"
  chmod 600 "$KEY_FILE"; echo "已建立，私鑰存 $KEY_FILE"
elif [[ ! -f "$KEY_FILE" ]]; then
  echo "AWS 上已有 $KEY_NAME 但本機沒有 ${KEY_FILE}；請把私鑰放到該路徑，或改 NAME 重建。"; exit 1
else echo "沿用 $KEY_FILE"; fi

# ---------- 2. 安全群組：443／80 對外，22 只給本機 IP ----------
log "安全群組 $SG_NAME"
VPC_ID="$(aws_q 'Vpcs[0].VpcId' ec2 describe-vpcs --filters Name=is-default,Values=true)"
SG_ID="$(aws_q 'SecurityGroups[0].GroupId' ec2 describe-security-groups --filters Name=group-name,Values="$SG_NAME" Name=vpc-id,Values="$VPC_ID" 2>/dev/null || true)"
if [[ -z "$SG_ID" || "$SG_ID" == "None" ]]; then
  SG_ID="$(aws_q 'GroupId' ec2 create-security-group --group-name "$SG_NAME" --description "ntpc appraisal web: 80/443 public, 22 restricted" --vpc-id "$VPC_ID")"
fi
MY_IP="$(curl -s -m 5 https://checkip.amazonaws.com | tr -d '[:space:]')"
[[ -n "$MY_IP" ]] || { echo "取不到本機公網 IP，請用 SSH_CIDR=x.x.x.x/32 指定"; exit 1; }
SSH_CIDR="${SSH_CIDR:-${MY_IP}/32}"
for rule in "tcp,80,0.0.0.0/0" "tcp,443,0.0.0.0/0" "tcp,22,$SSH_CIDR"; do
  IFS=, read -r proto port cidr <<<"$rule"
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol "$proto" --port "$port" --cidr "$cidr" >/dev/null 2>&1 || true
done
echo "SG ${SG_ID}（22 只開 ${SSH_CIDR}）"

# ---------- 3. IAM role：EC2 可呼叫 Bedrock（不用金鑰） ----------
log "IAM role ${ROLE_NAME}（bedrock:InvokeModel）"
if ! aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE_NAME" --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name bedrock-invoke --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["bedrock:InvokeModel","bedrock:InvokeModelWithResponseStream","bedrock:Converse","bedrock:ConverseStream"],"Resource":"*"}]}'
  aws iam create-instance-profile --instance-profile-name "$ROLE_NAME" >/dev/null
  aws iam add-role-to-instance-profile --instance-profile-name "$ROLE_NAME" --role-name "$ROLE_NAME"
  echo "已建立；等 IAM 傳播 10 秒"; sleep 10
else echo "沿用"; fi

# ---------- 4. EC2 ----------
log "EC2 ${TAG_NAME}（${INSTANCE_TYPE}）"
INSTANCE_ID="$(aws_q 'Reservations[0].Instances[0].InstanceId' ec2 describe-instances --filters Name=tag:Name,Values="$TAG_NAME" Name=instance-state-name,Values=pending,running,stopping,stopped 2>/dev/null || true)"
if [[ -z "$INSTANCE_ID" || "$INSTANCE_ID" == "None" ]]; then
  [[ $SYNC_ONLY == 1 ]] && { echo "--sync-only 但找不到機器"; exit 1; }
  AMI="$(aws_q 'Parameter.Value' ssm get-parameter --name /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id)"
  SUBNET="$(aws_q 'Subnets[0].SubnetId' ec2 describe-subnets --filters Name=vpc-id,Values="$VPC_ID" Name=default-for-az,Values=true)"
  INSTANCE_ID="$(aws_q 'Instances[0].InstanceId' ec2 run-instances \
    --image-id "$AMI" --instance-type "$INSTANCE_TYPE" --key-name "$KEY_NAME" \
    --security-group-ids "$SG_ID" --subnet-id "$SUBNET" --associate-public-ip-address \
    --iam-instance-profile Name="$ROLE_NAME" \
    --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":30,"VolumeType":"gp3","DeleteOnTermination":true}}]' \
    --user-data file://"$ROOT/deploy/user-data.sh" \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$TAG_NAME}]" \
    --metadata-options HttpTokens=required)"
  echo "已啟動 ${INSTANCE_ID}（Ubuntu 24.04 ${AMI}）"
else
  echo "沿用 $INSTANCE_ID"
  STATE="$(aws_q 'Reservations[0].Instances[0].State.Name' ec2 describe-instances --instance-ids "$INSTANCE_ID")"
  [[ "$STATE" == "stopped" ]] && aws ec2 start-instances --instance-ids "$INSTANCE_ID" >/dev/null
fi
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"

# ---------- 5. 固定 IP（sslip.io 網址才不會因重開機而變） ----------
log "Elastic IP"
ALLOC="$(aws_q 'Addresses[0].AllocationId' ec2 describe-addresses --filters Name=tag:Name,Values="$TAG_NAME" 2>/dev/null || true)"
if [[ -z "$ALLOC" || "$ALLOC" == "None" ]]; then
  ALLOC="$(aws_q 'AllocationId' ec2 allocate-address --domain vpc --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=$TAG_NAME}]")"
fi
aws ec2 associate-address --instance-id "$INSTANCE_ID" --allocation-id "$ALLOC" --allow-reassociation >/dev/null
PUBLIC_IP="$(aws_q 'Addresses[0].PublicIp' ec2 describe-addresses --allocation-ids "$ALLOC")"
PUBLIC_HOST="${PUBLIC_IP}.sslip.io"
echo "IP $PUBLIC_IP → https://$PUBLIC_HOST"

# ---------- 6. 等 SSH 與 cloud-init 裝完系統套件 ----------
log "等待 SSH 與系統套件（user-data）"
SSH=(ssh -i "$KEY_FILE" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=8 -o LogLevel=ERROR "ubuntu@$PUBLIC_IP")
for i in $(seq 1 40); do "${SSH[@]}" true 2>/dev/null && break; sleep 6; [[ $i == 40 ]] && { echo "SSH 連不上（SG 22 是否只開 ${SSH_CIDR}？本機 IP 變了就重跑）"; exit 1; }; done
"${SSH[@]}" 'cloud-init status --wait >/dev/null 2>&1 || true; test -f /var/lib/cloud/instance/boot-finished && node -v && python3.12 --version && caddy version | head -1'

# ---------- 7. 上傳程式與資料 ----------
log "打包並上傳程式"
SRC_TGZ="$(mktemp -t ntpc-src).tgz"
COPYFILE_DISABLE=1 tar czf "$SRC_TGZ" -C "$ROOT" --exclude='._*' --exclude=.DS_Store --exclude=node_modules --exclude=.next --exclude=.venv --exclude=.git --exclude=data --exclude='*.pyc' --exclude=__pycache__ .
scp -i "$KEY_FILE" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -q "$SRC_TGZ" "ubuntu@$PUBLIC_IP:/tmp/ntpc-src.tgz"; rm -f "$SRC_TGZ"
if [[ -n "${DATA_TGZ:-}" && -f "$DATA_TGZ" ]]; then
  log "上傳資料包 ${DATA_TGZ}（$(du -h "$DATA_TGZ" | cut -f1)）"
  scp -i "$KEY_FILE" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR "$DATA_TGZ" "ubuntu@$PUBLIC_IP:/tmp/ntpc-data.tgz"
elif [[ -d "$ROOT/data" && $SYNC_ONLY == 0 ]]; then
  log "同步本機 data/（rsync，排除 PDF／shp／zip／walk_cache）"
  rsync -av --exclude='*.pdf' --exclude='*.shp' --exclude='*.zip' --exclude='walk_cache' \
    -e "ssh -i $KEY_FILE -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR" --exclude='._*' --exclude=.DS_Store "$ROOT/data/" "ubuntu@$PUBLIC_IP:/opt/app/data/"
else echo "沒有資料包也沒有本機 data/：先起服務，資料之後用 DATA_TGZ= 或 --sync-only 補"; fi

# ---------- 8. 遠端安裝與啟動 ----------
log "遠端安裝（venv、npm build、systemd、Caddy）"
ENV_FILE="$(mktemp -t ntpc-env)"
cat > "$ENV_FILE" <<EOF
PUBLIC_HOST=$PUBLIC_HOST
AWS_REGION=$REGION
BEDROCK_MODEL_ID=$BEDROCK_MODEL_ID
LLM_PROVIDER=${LLM_PROVIDER:-$([[ -n "${ANTHROPIC_API_KEY:-}" ]] && echo anthropic || echo bedrock)}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
OSRM_URL=${OSRM_URL:-}
EOF
scp -i "$KEY_FILE" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -q "$ENV_FILE" "ubuntu@$PUBLIC_IP:/tmp/ntpc.env"; rm -f "$ENV_FILE"
"${SSH[@]}" bash -s < "$ROOT/deploy/remote_setup.sh"

# ---------- 9. 健康檢查 ----------
log "健康檢查 https://$PUBLIC_HOST"
for i in $(seq 1 20); do
  if curl -s -m 10 "https://$PUBLIC_HOST/api/health" | grep -q '"ok":true'; then
    curl -s -m 10 "https://$PUBLIC_HOST/api/health" | python3 -c 'import json,sys; h=json.load(sys.stdin); print("llm:",h["llm"]); print("poi:",h["spatial"]["poi"]["count"],"tiles:",h["tiles"]["tiles"],"lvr:",h["lvr"]["n"])'
    curl -s -m 10 -o /dev/null -w "首頁 HTTP %{http_code}\n" "https://$PUBLIC_HOST/"
    printf '\n\033[1;32m完成：https://%s\033[0m\nSSH：ssh -i %s ubuntu@%s\n' "$PUBLIC_HOST" "$KEY_FILE" "$PUBLIC_IP"
    exit 0
  fi
  sleep 6
done
echo "健康檢查未通過；看遠端 log：ssh -i $KEY_FILE ubuntu@$PUBLIC_IP 'sudo journalctl -u ntpc-backend -u ntpc-frontend -u caddy -n 50'"; exit 1
