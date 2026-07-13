# AvitologAI — agent instructions

Telegram Mini App + FastAPI for Avito creatives via OpenRouter. Repo: `https://github.com/shurik782-a11y/AvitologAI`. Deploy: Railway (`Dockerfile`).

## Hard rules

- **Project isolation:** never mix chats, prompts, memory, feeds, or Avito credentials across `project_id`.
- After project create: seed chat with «Давайте выполним настройку»; first user reply → onboarding parser → write theme/ideas/constraints/**project overlay prompts** for **that** project only.
- **Built-in agent instructions** live in `app/services/prompts.py` and are always applied at runtime. They must **never** be shown or edited in the Mini App UI. Settings fields are project overlays from знакомство only.
- Image generation: orchestrator sets `need_images` from the user request — no UI checkbox.
- Approve creative → rebuild project XML feed; optional Autoload `upload` if Avito API keys exist.
- Avito metrics: fetch **only** on user «Обновить»; otherwise show last snapshot.
- After code changes: commit + push to `origin/main` (unless user forbids). Never commit `.env` secrets.

## Stack

- Backend: FastAPI, SQLAlchemy, Postgres (`DATABASE_URL`) or SQLite
- Frontend: React/Vite in `web/` (built into `web/dist` in Docker)
- AI: OpenRouter (orchestrator / vision / images)
- Publish: Avito Autoload XML feed URL + API

## Env (Railway)

`PUBLIC_BASE_URL`, `TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`, `ORCHESTRATOR_MODEL`, `VISION_MODEL`, `IMAGE_MODEL`, `DATABASE_URL`, **`ADMIN_IDS`** (comma-separated Telegram user IDs — required in production; empty = open API for local/smoke only).

## Access control

- API (except health / telegram webhook / token-gated feed) requires valid Telegram WebApp `initData` and `user.id ∈ ADMIN_IDS`.
- Bot `/start` denied for non-admins when `ADMIN_IDS` is set.
- Feed XML stays public with `?token=` (Avito Autoload).

## Skill

Read `.cursor/skills/avitolog/SKILL.md` for task routing.
