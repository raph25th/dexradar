# Деплой eth-dex-radar на Ubuntu VPS без Docker

Инструкция рассчитана на Ubuntu 22.04 или 24.04. Все команды ниже предполагают, что проект будет находиться в `/opt/eth-dex-radar`, а сервис будет запускаться от пользователя `ethradar`. Пути и имена можно заменить под свой сервер.

## 1. Обновите сервер

```bash
sudo apt update
sudo apt upgrade -y
```

## 2. Установите системные пакеты

```bash
sudo apt install -y python3 python3-venv python3-pip git postgresql postgresql-contrib curl
```

Проверьте версии:

```bash
python3 --version
psql --version
```

## 3. Создайте Linux-пользователя для сервиса

```bash
sudo useradd --system --create-home --shell /bin/bash ethradar
```

## 4. Загрузите проект на сервер

Вариант через `git`:

```bash
sudo mkdir -p /opt/eth-dex-radar
sudo chown ethradar:ethradar /opt/eth-dex-radar
sudo -u ethradar git clone <YOUR_REPOSITORY_URL> /opt/eth-dex-radar
```

Если проект загружается архивом или через `scp`, поместите файлы в `/opt/eth-dex-radar` и выставьте владельца:

```bash
sudo chown -R ethradar:ethradar /opt/eth-dex-radar
```

## 5. Создайте PostgreSQL базу и пользователя

Откройте `psql` от пользователя `postgres`:

```bash
sudo -u postgres psql
```

Выполните SQL:

```sql
CREATE USER dex_user WITH PASSWORD 'CHANGE_ME_STRONG_PASSWORD';
CREATE DATABASE dex_radar OWNER dex_user;
GRANT ALL PRIVILEGES ON DATABASE dex_radar TO dex_user;
\q
```

Проверьте подключение:

```bash
psql "postgresql://dex_user:CHANGE_ME_STRONG_PASSWORD@localhost:5432/dex_radar" -c "SELECT 1;"
```

## 6. Настройте `.env`

```bash
cd /opt/eth-dex-radar
sudo -u ethradar cp .env.example .env
sudo -u ethradar nano .env
```

Пример для VPS без Docker:

```env
DATABASE_URL=postgresql+psycopg://dex_user:CHANGE_ME_STRONG_PASSWORD@localhost:5432/dex_radar
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
DEXSCREENER_BASE_URL=https://api.dexscreener.com
POLL_INTERVAL_SECONDS=300
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=admin
```

Если Telegram пока не нужен, оставьте `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID` пустыми. Сервис не должен падать без Telegram credentials.

Важно: на VPS обязательно замените `DASHBOARD_USERNAME=admin` и `DASHBOARD_PASSWORD=admin` на собственные значения. `admin/admin` допустимы только для локальной разработки.

## 7. Создайте виртуальное окружение и установите зависимости

```bash
cd /opt/eth-dex-radar
sudo -u ethradar python3 -m venv .venv
sudo -u ethradar .venv/bin/python -m pip install --upgrade pip
sudo -u ethradar .venv/bin/pip install -r requirements.txt
```

## 8. Примените миграции Alembic

```bash
cd /opt/eth-dex-radar
sudo -u ethradar .venv/bin/alembic upgrade head
```

## 9. Выполните тестовый запуск Uvicorn

```bash
cd /opt/eth-dex-radar
sudo -u ethradar .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

В другом терминале проверьте:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/status
curl http://127.0.0.1:8000/status
curl -X POST http://127.0.0.1:8000/jobs/collect-once
curl http://127.0.0.1:8000/alerts/recent
```

Остановите тестовый запуск через `Ctrl+C`.

## 10. Проверьте snapshots в PostgreSQL

После `POST /jobs/collect-once` проверьте, что snapshots пишутся в базу:

```bash
psql "postgresql://dex_user:CHANGE_ME_STRONG_PASSWORD@localhost:5432/dex_radar" \
  -c "SELECT COUNT(*) AS pair_snapshots_count FROM pair_snapshots;"
```

Можно также проверить основные таблицы:

```bash
psql "postgresql://dex_user:CHANGE_ME_STRONG_PASSWORD@localhost:5432/dex_radar" \
  -c "SELECT (SELECT COUNT(*) FROM tokens) AS tokens, (SELECT COUNT(*) FROM pairs) AS pairs, (SELECT COUNT(*) FROM pair_snapshots) AS snapshots, (SELECT COUNT(*) FROM alerts) AS alerts;"
```

## 11. Запуск через shell script

```bash
cd /opt/eth-dex-radar
chmod +x scripts/run_server.sh scripts/check_server.sh
sudo -u ethradar ./scripts/run_server.sh
```

Проверка:

```bash
./scripts/check_server.sh
```

## 12. Настройка systemd

Скопируйте example unit:

```bash
sudo cp /opt/eth-dex-radar/systemd/eth-dex-radar.service.example /etc/systemd/system/eth-dex-radar.service
sudo nano /etc/systemd/system/eth-dex-radar.service
```

В файле замените:

- `User`
- `WorkingDirectory`
- путь в `ExecStart`

Затем запустите service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable eth-dex-radar
sudo systemctl start eth-dex-radar
sudo systemctl status eth-dex-radar
```

Логи systemd:

```bash
journalctl -u eth-dex-radar -f
```

Логи приложения:

```bash
tail -f /opt/eth-dex-radar/logs/app.log
tail -f /opt/eth-dex-radar/logs/errors.log
```

## 13. Web Dashboard

Dashboard доступен по URL:

```text
http://SERVER_IP:8000/dashboard
```

Dashboard защищён Basic Auth. Логин и пароль берутся из `.env`:

```env
DASHBOARD_USERNAME=your_dashboard_user
DASHBOARD_PASSWORD=your_strong_dashboard_password
```

Если UFW закрывает порт `8000`, dashboard будет доступен только локально на сервере или через SSH tunnel.

Пример SSH tunnel с локального компьютера:

```bash
ssh -L 8000:127.0.0.1:8000 root@SERVER_IP
```

После этого dashboard можно открыть локально:

```text
http://127.0.0.1:8000/dashboard
```

Проверка JSON status:

```bash
curl http://127.0.0.1:8000/api/status
```

## 14. Firewall

Если API должен быть доступен снаружи, откройте порт `8000`:

```bash
sudo ufw allow 8000/tcp
sudo ufw status
```

Для production обычно лучше поставить Nginx reverse proxy и не открывать Uvicorn напрямую в интернет.

## 15. Filter v2 Observations

После этой версии сервис сохраняет диагностические результаты Filter v2 в таблицу `candidate_observations`.

Назначение этого слоя:

- 2–3 дня копить историю по всем fetched candidate pairs;
- видеть, какие пары попадали в `early_watch`, `watch`, `high_signal`, `avoid`, `rejected`;
- анализировать missed opportunities и шумные критерии без изменения Telegram и текущих alerts.

После деплоя обязательно примените новую миграцию:

```bash
cd /opt/eth-dex-radar
sudo -u ethradar .venv/bin/alembic upgrade head
sudo systemctl restart eth-dex-radar
```

Проверка dashboard:

```text
http://SERVER_IP:8000/dashboard
http://SERVER_IP:8000/dashboard/observations
http://SERVER_IP:8000/dashboard/pairs
```

Если порт `8000` закрыт firewall, используйте SSH tunnel:

```bash
ssh -L 8000:127.0.0.1:8000 root@SERVER_IP
```

И откройте локально:

```text
http://127.0.0.1:8000/dashboard/observations
```

SQL-проверка количества observations:

```sql
SELECT COUNT(*) FROM candidate_observations;
```

Распределение статусов за последние 24 часа:

```sql
SELECT v2_status, COUNT(*)
FROM candidate_observations
WHERE observed_at >= NOW() - INTERVAL '24 hours'
GROUP BY v2_status
ORDER BY COUNT(*) DESC;
```

Последние 20 observations:

```sql
SELECT *
FROM candidate_observations
ORDER BY observed_at DESC
LIMIT 20;
```

Эти данные стоит собирать минимум 2–3 дня перед изменением реальных alert thresholds.
