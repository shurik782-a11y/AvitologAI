# Orchestrator JSON

Single LLM pass. Reply JSON (no markdown fences preferred):

```json
{
  "ad_idea": "...",
  "title": "...",
  "search_query": "...",
  "conversion_offer": "...",
  "description": "...",
  "sections": {
    "usp_4u": "",
    "cta_1": "",
    "seller": "",
    "fulfillment": "",
    "product": "",
    "objections": "",
    "cta_2": "",
    "keywords": "",
    "sku": ""
  },
  "pains": [],
  "image_briefs": [
    {"role": "hero|pain|proof", "prompt": "...", "edit_from": "ref|none"}
  ],
  "image_prompt": "...",
  "analysis": "...",
  "need_images": true,
  "price": "",
  "propose_new_idea": false
}
```

Rules:

- `title` = short `search_query` + `conversion_offer` (≈25–55 chars). No keyword stuffing, no «купить», no full lowercase soup, no dumping the whole brief into the title.
- `description` = join non-empty `sections` as rich paragraphs (usp/product/objections/cta required when brief has data). Keywords only at the end.
- `need_images`: false for text-only edits / «без картинки».
- `image_briefs` length ≈ project `photo_count` (hard max 5). Hero first; prefer `edit_from=ref` when reference exists.
- `propose_new_idea`: optional hint; do not auto-create a new listing.
- Revisions update the same creative; «новое объявление / другая идея» → new creative.
