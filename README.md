# eth-dex-radar

MVP backend-сервис для мониторинга, скоринга и аналитики Ethereum DEX token pairs через DEX Screener API.

Проект не содержит автотрейдинга, приватных ключей, wallet execution, auto-buy или управления кошельками. Он только собирает рыночные snapshots, считает базовый score и готовит Telegram-алерты.

Деплой на Ubuntu VPS без Docker описан в [README_SERVER.md](README_SERVER.md).

## Стек

- Python 3.11+
- FastAPI
- PostgreSQL
- SQLAlchemy 2.x
- Alembic
- Pydantic v2 и pydantic-settings
- httpx
- APScheduler
- python-telegram-bot
- Docker Compose

## Быстрый старт

```bash
cp .env.example .env
docker compose up --build
```

В отдельном терминале примените миграции:

```bash
docker compose exec app alembic upgrade head
```

Это обычная команда Alembic `alembic upgrade head`, запущенная внутри app-контейнера, где доступен hostname `postgres` из `DATABASE_URL`.

Проверка health endpoint:

```bash
curl http://localhost:8000/health
```

Ручной запуск одного collection cycle:

```bash
curl -X POST http://localhost:8000/jobs/collect-once
```

Проверка последних алертов:

```bash
curl http://localhost:8000/alerts/recent
```

## Локальный запуск без Docker

Если зависимости уже установлены в `.venv`, сервис можно запустить через PowerShell:

```powershell
.\scripts\run_local.ps1
```

Скрипт переходит в директорию проекта, активирует `.venv` и запускает:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

После запуска проверьте:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/status
```

## Проверка после установки

Запустите контейнеры:

```bash
docker compose up --build
```

Примените миграции:

```bash
docker compose exec app alembic upgrade head
```

Проверьте health endpoint:

```bash
curl http://localhost:8000/health
```

Проверьте status endpoint:

```bash
curl http://localhost:8000/status
```

Запустите collection cycle вручную:

```bash
curl -X POST http://localhost:8000/jobs/collect-once
```

Проверьте recent alerts:

```bash
curl http://localhost:8000/alerts/recent
```

Дополнительно можно запустить smoke-test внутри app-контейнера:

```bash
docker compose exec app python scripts/smoke_test.py
```

В Docker Compose приложение получает `DATABASE_URL` с host `postgres`. Для локального запуска без Docker используйте `localhost` в `DATABASE_URL`.

## Переменные окружения

Скопируйте `.env.example` в `.env` и при необходимости заполните:

- `DATABASE_URL` - SQLAlchemy URL для PostgreSQL.
- `TELEGRAM_BOT_TOKEN` - токен Telegram bot. Может быть пустым.
- `TELEGRAM_CHAT_ID` - chat id для отправки алертов. Может быть пустым.
- `DEXSCREENER_BASE_URL` - базовый URL DEX Screener API.
- `POLL_INTERVAL_SECONDS` - интервал фонового сбора данных.

Если Telegram-настройки пустые, сервис не падает: он логирует warning и сохраняет alert с `sent_to_telegram=false`.

## Архитектура

### Collector

`app/collectors/dexscreener.py` ходит в DEX Screener API через `httpx.AsyncClient`.

Для MVP используются широкие search query:

- `WETH`
- `ETH`
- `USDC`
- `PEPE`
- `AI`

После загрузки данные нормализуются, дедуплицируются по pair address и фильтруются до `chainId == "ethereum"`.

### Filters

`app/services/filters.py` применяет базовые фильтры:

- Ethereum chain.
- Liquidity от `$100k`.
- 1h volume от `$50k`.
- 1h transactions от `50`.
- FDV должен присутствовать.
- FDV до `$50m`.

### Filter profiles

`early_watch` — мягкий профиль для наблюдения за ранними кандидатами:

- Ethereum chain.
- Liquidity от `$20k`.
- 1h volume от `$5k`.
- 1h transactions от `10`.
- FDV должен присутствовать.
- FDV до `$100m`.

`basic` — более строгий профиль для signal/alert eligibility:

- Ethereum chain.
- Liquidity от `$100k`.
- 1h volume от `$50k`.
- 1h transactions от `50`.
- FDV должен присутствовать.
- FDV до `$50m`.

Пары, прошедшие `early_watch`, пока только считаются и логируются. Alerts создаются только для пар, которые прошли `basic`, получили market score и достигли alert threshold.

### Scoring

`app/services/scoring.py` считает market score от `0` до `100` по liquidity, volume, transactions, 1h price change, FDV и buy/sell ratio. Функция возвращает score и список причин начисления или снятия баллов.

### Alerts

`app/services/alerts.py` определяет уровень алерта:

- `high` при score от `75`.
- `watch` при score от `60`.
- иначе алерт не создаётся.

### Telegram

`app/telegram/templates.py` форматирует читаемое сообщение с token pair, score, liquidity, volume, FDV, transactions, price changes, pair age и DEX Screener link.

`app/telegram/bot.py` отправляет сообщение через Telegram API, если заданы `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID`.

### Database snapshots

`Token` и `Pair` создаются или обновляются без дублей. Каждый collection cycle добавляет новый `PairSnapshot`, чтобы хранить исторический срез рынка. Если score проходит порог, создаётся `Alert`.

## Логика сохранения snapshots

`PairSnapshot` сохраняется для каждой fetched candidate pair до применения basic filters.

Фильтры используются только для signal/alert eligibility: пара, которая не прошла фильтры, остаётся в базе как рыночная история, но не получает market score и не создаёт alert.

Это нужно, чтобы позже анализировать rejected candidates, missed opportunities и токены, которые не выглядели интересными в момент первого обнаружения, но могли вырасти после нескольких collection cycles.

## API

### GET `/health`

Возвращает:

```json
{"status": "ok"}
```

### POST `/jobs/collect-once`

Запускает сбор данных вручную и возвращает summary:

```json
{
  "fetched": 13,
  "snapshots_created": 13,
  "early_watch_passed": 0,
  "passed_filters": 0,
  "scored": 0,
  "alerts_created": 0,
  "telegram_sent": 0
}
```

### GET `/alerts/recent`

Возвращает последние 20 алертов с базовой информацией по pair, token и snapshot.

### GET `/status`

Возвращает runtime-status сервиса, последнее collection summary и текущие счётчики базы:

```json
{
  "status": "ok",
  "current_time": "2026-05-06T19:00:00+00:00",
  "last_collection_at": null,
  "last_collection_summary": null,
  "total_tokens": 0,
  "total_pairs": 0,
  "total_snapshots": 0,
  "total_alerts": 0
}
```

## Alembic

Миграции настроены на чтение `DATABASE_URL` из окружения:

```bash
docker compose exec app alembic upgrade head
```

Для локального запуска без Docker используйте PostgreSQL, доступный по вашему `DATABASE_URL`, затем:

```bash
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```
