# Avito Autoload XML

- Public feed: `GET /api/projects/{id}/avito-feed.xml?token=...`
- Only `approved` creatives of that project.
- Fields (starter): Id, Title, Description, Price, Images, Address/Contact.
- Docs: https://autoload.avito.ru/format/
- Validator: https://autoload.avito.ru/format/xmlcheck/
- Optional API: OAuth client credentials → profile v2 `feeds_data` → `upload` → reports v4.
