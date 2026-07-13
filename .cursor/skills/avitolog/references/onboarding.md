# Onboarding

1. On project create: assistant message «Давайте выполним настройку» (+ short hint).
2. `onboarding_status=awaiting_brief`.
3. Next user message → LLM extracts JSON into project fields only:
   - theme, ideas, constraints, orchestrator_prompt
   - optional vision_prompt, image_style_prompt
4. Confirm in chat; set `onboarding_status=done`.
5. Never write to another project.
