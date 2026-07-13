# Avito Autoload XML

- Public feed: `GET /api/projects/{id}/avito-feed.xml?token=...`
- Only `approved` creatives of **that** project.
- `formatVersion="3"` / `target="Avito.ru"`.

## Field mapping

| XML | Source | Rules |
|-----|--------|--------|
| `Id` | `creative.avito_ad_id` (or `p{pid}-c{cid}`) | Stable across updates |
| `Title` | `creative.title` | ≤50 chars; strip «купить онлайн / с доставкой» |
| `Description` | `creative.description` | ≤7500; no English CoT leaks |
| `Price` | `creative.price` | Digits only; omitted if empty |
| `Category` | `project.avito_category` | Required for real Autoload |
| `Address` | `project.avito_address` | Required for real Autoload |
| `ContactPhone` | `project.avito_contact_phone` | Digits/+ only |
| `Images/Image@url` | `creative.images[].url` | Absolute http(s); max 10 |

## Ops

- Docs: https://autoload.avito.ru/format/
- Validator: https://autoload.avito.ru/format/xmlcheck/
- Optional API: OAuth → profile feeds → `upload` → reports v4.
