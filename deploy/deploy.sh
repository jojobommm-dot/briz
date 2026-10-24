#!/usr/bin/env bash
# Обновить «Бриз» на сервере до свежего main. Запускать от root:
#   bash /opt/briz/deploy/deploy.sh
# Перед обновлением снимается бэкап базы — откатиться можно в любой момент.
set -euo pipefail
cd /opt/briz

TS=$(date +%Y%m%d-%H%M%S)
sudo -u postgres pg_dump briz | gzip > "/opt/backups/briz-$TS.sql.gz"
echo "бэкап базы: /opt/backups/briz-$TS.sql.gz"

OLD=$(sudo -u briz git rev-parse --short HEAD)
# git только от briz: от root сломается владелец .git/objects
sudo -u briz git pull --ff-only -q
NEW=$(sudo -u briz git rev-parse --short HEAD)
echo "код: $OLD → $NEW"

sudo -u briz venv/bin/pip install -q -r requirements.txt
systemctl restart briz

# Таблицы и новые колонки приложение досоздаёт само при запуске
for i in $(seq 1 20); do
    if curl -fs http://127.0.0.1:8200/healthz >/dev/null; then
        echo "сайт отвечает"
        exit 0
    fi
    sleep 1
done
echo "сайт не поднялся — journalctl -u briz -n 50" >&2
exit 1
