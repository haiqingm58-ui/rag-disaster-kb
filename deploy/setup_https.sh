#!/usr/bin/env bash
# 用 certbot 给 georisklab.com.cn 申请并自动安装 Let's Encrypt 证书。
# 前置条件：
#   1. nginx 已经按 deploy/nginx.conf.example 运行，且能从公网通过 80 端口访问到本机。
#   2. 域名 A 记录已经指向本机公网 IP。
#   3. 阿里云安全组放行 80/443。
set -euo pipefail

DOMAIN="${DOMAIN:-georisklab.com.cn}"
EMAIL="${EMAIL:-}"

if [ -z "$EMAIL" ]; then
  echo "请通过环境变量传入邮箱：EMAIL=you@example.com bash deploy/setup_https.sh"
  exit 1
fi

sudo apt-get update
sudo apt-get install -y certbot python3-certbot-nginx

sudo certbot --nginx \
  -d "$DOMAIN" \
  --non-interactive --agree-tos \
  --redirect \
  --email "$EMAIL"

# certbot 在 Ubuntu 上会自动注册 systemd timer 续期，下面只是显式确认。
sudo systemctl enable --now certbot.timer
sudo systemctl status certbot.timer --no-pager || true

echo
echo "证书已申请。请把 deploy/nginx-https.conf.example 覆盖到 /etc/nginx/sites-available/rag-fastapi 后重载 nginx："
echo "  sudo cp deploy/nginx-https.conf.example /etc/nginx/sites-available/rag-fastapi"
echo "  sudo nginx -t && sudo systemctl reload nginx"
