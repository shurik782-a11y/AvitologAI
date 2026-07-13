# AvitologAI

Telegram Mini App + FastAPI для генерации креативов Авито через **OpenRouter**.

## Что умеет v0.1

- Подключение OpenRouter API (ключ в UI)
- Оркестратор на быстрой/бесплатной модели (`openrouter/free` по умолчанию)
- Отдельная модель генерации картинок (`black-forest-labs/flux.2-flex`)
- Обработка входящих фото (vision)
- Собственная инструкция оркестратора
- Проекты: тема, идеи, ограничения, изолированный чат
- Память проекта: правки и частые действия сохраняются и усиливают контекст
- Метрики воронки/ошибок
- Деплой на Railway (Dockerfile)

## Локальный запуск

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend (dev):

```bash
cd web
npm install
npm run dev
```

Откройте http://127.0.0.1:5173 (прокси на API) или соберите `npm run build` и откройте http://127.0.0.1:8000.

## Railway

1. Подключите репозиторий `shurik782-a11y/AvitologAI`
2. Railway подхватит `Dockerfile` / `railway.toml`
3. Задайте переменные:
   - `OPENROUTER_API_KEY` (можно и в UI)
   - `PUBLIC_BASE_URL` = URL сервиса
   - опционально `ORCHESTRATOR_MODEL`, `VISION_MODEL`, `IMAGE_MODEL`
4. Для persistence добавьте Volume на `/data`

## Telegram WebApp

В BotFather: Menu Button / Web App URL → URL Railway-сервиса.

## Архитектура

См. `docs/architecture.excalidraw`.
