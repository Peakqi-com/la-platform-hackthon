#!/usr/bin/env bash
# 收攤：終止 provision.sh 建的 EC2、釋放固定 IP、刪安全群組／金鑰對／IAM role。賽後執行。
#   ./deploy/teardown.sh            # 會先列出要刪的資源再問一次
#   ./deploy/teardown.sh --yes      # 不問
set -euo pipefail
NAME="${NAME:-ntpc}"
REGION="${REGION:-$(aws configure get region || echo us-west-2)}"
export AWS_DEFAULT_REGION="$REGION"
TAG_NAME="${NAME}-appraisal"; KEY_NAME="${NAME}-key"; SG_NAME="${NAME}-web"; ROLE_NAME="${NAME}-ec2-bedrock"
q() { aws --output text --query "$@"; }

IDS="$(q 'Reservations[].Instances[].InstanceId' ec2 describe-instances --filters Name=tag:Name,Values="$TAG_NAME" Name=instance-state-name,Values=pending,running,stopping,stopped || true)"
ALLOC="$(q 'Addresses[].AllocationId' ec2 describe-addresses --filters Name=tag:Name,Values="$TAG_NAME" || true)"
SG_ID="$(q 'SecurityGroups[].GroupId' ec2 describe-security-groups --filters Name=group-name,Values="$SG_NAME" || true)"
echo "將刪除（${REGION}）：EC2 [$IDS]  EIP [$ALLOC]  SG [$SG_ID]  key [$KEY_NAME]  role [$ROLE_NAME]"
if [[ "${1:-}" != "--yes" ]]; then read -r -p "確定？(yes/N) " a; [[ "$a" == "yes" ]] || exit 0; fi

if [[ -n "$IDS" ]]; then aws ec2 terminate-instances --instance-ids $IDS >/dev/null; aws ec2 wait instance-terminated --instance-ids $IDS; echo "EC2 已終止"; fi
for a in $ALLOC; do aws ec2 release-address --allocation-id "$a" && echo "EIP $a 已釋放"; done
for s in $SG_ID; do aws ec2 delete-security-group --group-id "$s" && echo "SG $s 已刪"; done
aws ec2 delete-key-pair --key-name "$KEY_NAME" >/dev/null 2>&1 && echo "key pair 已刪（本機 ~/.ssh/$KEY_NAME.pem 自行處理）" || true
if aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  aws iam remove-role-from-instance-profile --instance-profile-name "$ROLE_NAME" --role-name "$ROLE_NAME" 2>/dev/null || true
  aws iam delete-instance-profile --instance-profile-name "$ROLE_NAME" 2>/dev/null || true
  aws iam delete-role-policy --role-name "$ROLE_NAME" --policy-name bedrock-invoke 2>/dev/null || true
  aws iam delete-role --role-name "$ROLE_NAME" && echo "IAM role 已刪"
fi
echo "完成"
