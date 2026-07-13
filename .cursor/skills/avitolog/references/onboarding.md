# Onboarding

1. On project create: assistant seed «Давайте выполним настройку» (+ slots hint).
2. `onboarding_status=awaiting_brief`.
3. Multi-turn on **free** model only: `ONBOARDING_MODEL` / `settings.onboarding_model` default `openrouter/free` — never the project's paid orchestrator model.
4. Each user reply → LLM JSON with slots + `need_user_input` / `questions` / `done`. No hallucinations; ask if missing.
5. Max rounds: `onboarding_max_rounds` (default 4), then finish with what we have.
6. Writes project fields: theme/ideas/constraints, listing slots (`listing_type`, `ad_idea`, `search_query`, `conversion_offer`, `advantages`, `buyer_pains`, `why_here`, `company_info`, `photo_count`, `allow_people`, `allow_text_overlays`), overlay prompts.
7. Reference photos: store in `project.extra.reference_images`; Vision deferred to first creative.
8. Competitors CSV/XLSX: `POST /api/projects/{id}/competitors/import` → compressed `competitor_insights` on free model.
9. Set `onboarding_status=done` when complete. Never write to another project.
