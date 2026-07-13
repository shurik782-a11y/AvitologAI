# Avito metrics

- Menu «Метрики»: list publications for current project.
- Select one → detail view.
- **No auto-fetch** on open. Button «Обновить» calls Avito and stores snapshot.
- APIs: `GET .../items/{item_id}/`, `POST /stats/v1/accounts/{user_id}/items`.
- Store in `avito_stat_snapshots` with `fetched_at`.
