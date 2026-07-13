---
name: avitolog
description: AvitologAI — Telegram WebApp for Avito creatives via OpenRouter, XML Autoload, onboarding, billing header, Avito metrics. Use when editing this repo's orchestrator, feed, publications, metrics, or Mini App UI.
---

# Avitolog skill

## Route

| Task | Where |
|------|--------|
| Creative / chat | `app/services/orchestrator.py`, `app/routers/chat.py` |
| Onboarding (free model) | `app/services/onboarding.py`, `ONBOARDING_MODEL` |
| Listing prompts (hidden) | `app/services/prompts.py` |
| Competitors CSV/XLSX | `app/services/competitors.py`, `POST .../competitors/import` |
| Test run | `app/services/test_run.py`, trigger «тестовый прогон» |
| XML feed | `app/services/avito_feed.py`, feed endpoint on projects |
| Autoload API | `app/services/avito_autoload.py` |
| OpenRouter billing | `app/routers/billing.py` |
| Avito metrics | `app/routers/avito_metrics.py`, refresh-only |
| UI | `web/src/App.jsx`, `web/src/styles.css` |

## References

- [references/orchestrator-json.md](references/orchestrator-json.md)
- [references/onboarding.md](references/onboarding.md)
- [references/test-run.md](references/test-run.md)
- [references/competitors-apis.md](references/competitors-apis.md)
- [references/autoload-xml.md](references/autoload-xml.md)
- [references/avito-metrics.md](references/avito-metrics.md)

## MUST

- Isolate by `project_id` (creatives/settings/chat/feed)
- Commit + push after feature work
- Absolute HTTPS image URLs in XML (`PUBLIC_BASE_URL`)
- Emit explicit Russian status lines via `app/services/status_steps.emit_status` (`meta.status=true`); exclude them from LLM history
- Mistake memory: `classify_and_remember_mistake` → `global` (reusable) or `project` (niche-only); never put creatives in global pool

## Status steps (chat)

**Onboarding:** Выделяю основные критерии → Фиксирую идею → Уточняю боли → Прошу референс → (конкуренты) → Прописываю промпты → summary. Model: free only.

**Creative:** Обрабатываю запрос → (revise…) → Формирую идею → Учитываю конкурентов → Даю задание → Собираю текст по структуре → Планирую фото → Редактирую референс / Генерирую фото → Формирую публикацию → delivery.

**Approve:** Отправляю на публикацию → Готово…. In test run: Эмулирую публикацию на Авито.

## Agent guardrails

- Orchestrator / Vision / Onboarding: no off-topic advice (models, Avito tariffs, CRM); stay on slots/JSON/facts.
- Test run (`references/test-run.md`): emulate Avito; real creatives + memory; no real Autoload API.