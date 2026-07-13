# Тестовый прогон

Trigger: user message **starts with** `тестовый прогон` (case-insensitive).

## Behavior

1. Set `project.extra.test_run = true`.
2. Fill demo Avito feed fields if empty (category/address/phone) so UI looks «connected».
3. Strip the trigger; remainder is the brief.
4. If onboarding not done → real onboarding (free model) fills slots.
5. After onboarding, user says `сделай пост` → real orchestrator creative (text + photos).
6. Approve → **emulated** publish (`publish_run.status=test_emulated`), fake `avito_item_id`; **no** Avito API upload.
7. Mistake memory / revisions / approvals still **real** learning.

## Do not

- Ask for Client ID/Secret in test mode.
- Suggest switching models, ads budget, third-party tools.
- Skip memory on edits.

## Code

- `app/services/test_run.py`
- `app/routers/chat.py` (trigger)
- `app/routers/publications.py` (emulated upload)
