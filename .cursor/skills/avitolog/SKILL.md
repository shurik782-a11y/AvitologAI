---
name: avitolog
description: AvitologAI — Telegram WebApp for Avito creatives via OpenRouter, XML Autoload, onboarding, billing header, Avito metrics. Use when editing this repo's orchestrator, feed, publications, metrics, or Mini App UI.
---

# Avitolog skill

## Route

| Task | Where |
|------|--------|
| Creative / chat | `app/services/orchestrator.py`, `app/routers/chat.py` |
| Onboarding | `app/services/onboarding.py` |
| XML feed | `app/services/avito_feed.py`, feed endpoint on projects |
| Autoload API | `app/services/avito_autoload.py` |
| OpenRouter billing | `app/routers/billing.py` |
| Avito metrics | `app/routers/avito_metrics.py`, refresh-only |
| UI | `web/src/App.jsx`, `web/src/styles.css` |

## References

- [references/orchestrator-json.md](references/orchestrator-json.md)
- [references/onboarding.md](references/onboarding.md)
- [references/autoload-xml.md](references/autoload-xml.md)
- [references/avito-metrics.md](references/avito-metrics.md)

## MUST

- Isolate by `project_id` (creatives/settings/chat/feed)
- Commit + push after feature work
- Absolute HTTPS image URLs in XML (`PUBLIC_BASE_URL`)
- Emit explicit Russian status lines via `app/services/status_steps.emit_status` (`meta.status=true`); exclude them from LLM history
- Mistake memory: `classify_and_remember_mistake` → `global` (reusable) or `project` (niche-only); never put creatives in global pool

## Status steps (chat)

**Onboarding:** Выделяю основные критерии → Фиксирую идею → Устанавливаю ограничения → Прописываю промпты → summary.

**Creative:** Обрабатываю запрос → (revise: Фиксирую ошибку (общая|только этот проект) + Выполняю правки) → Даю задание на генерацию → Делегирую создание текста → optional image → Формирую публикацию → delivery.

**Approve:** Отправляю на публикацию → Готово….
