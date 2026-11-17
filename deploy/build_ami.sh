#!/bin/bash
# Odpalamy RAZ na tymczasowej EC2 (Amazon Linux 2023), potem robimy z niej AMI.
# Uzycie (z katalogu domowego):
#   sudo dnf install -y git
#   git clone https://github.com/lil-mixail/alledrogo.git     # repo prywatne -> login + token tylko do odczytu
#   sudo bash alledrogo/deploy/build_ami.sh
set -euo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)"

dnf install -y python3.11 python3.11-pip
id alledrogo >/dev/null 2>&1 || useradd --system --create-home --home-dir /opt/alledrogo alledrogo

rm -rf /opt/alledrogo/app
mkdir -p /opt/alledrogo/app
cp -r "$SRC"/. /opt/alledrogo/app/
rm -rf /opt/alledrogo/app/.git          # w obrazie nie trzymamy historii ani tokena

python3.11 -m venv /opt/alledrogo/venv
/opt/alledrogo/venv/bin/pip install --upgrade pip
/opt/alledrogo/venv/bin/pip install -r /opt/alledrogo/app/requirements.txt

# statyki zbieramy przy budowie obrazu (baza nie jest potrzebna)
cd /opt/alledrogo/app
DJANGO_DEBUG=False DJANGO_SECRET_KEY=build DATABASE_URL=sqlite:////tmp/build.db \
  /opt/alledrogo/venv/bin/python manage.py collectstatic --noinput

chown -R alledrogo:alledrogo /opt/alledrogo
install -m 644 deploy/alledrogo.service /etc/systemd/system/alledrogo.service
systemctl daemon-reload
# usluga startuje dopiero z user data (tam powstaje /etc/alledrogo.env)
rm -rf "$SRC"
echo "Gotowe. Teraz: EC2 -> Actions -> Image and templates -> Create image"
