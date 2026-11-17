# Codex Repository Instructions

## Goal
Build a production-quality, installable IP asset production Skill for Tencent WorkBuddy and DeepSeek Harness. The repository starts as a specification/prototype only. The authoritative product contract is `docs/SPEC.md`; the milestones are in `docs/IMPLEMENTATION_PLAN.md`.

## Source of truth and scope
- Never silently diverge from the written SPEC. If implementation reveals constraints, record an ADR in `docs/DECISIONS.md` and update acceptance tests.
- Keep `SKILL.md` short; use linked references, templates, schemas and scripts as needed. Do not dump all prompts into a single context.
- Separate `WorkBuddy/DeepSeek host`, `business workflow`, `image provider` and `postprocessing/QA` concerns. No hardcoded vendor endpoint or API key in the core logic.
- Preserve all 41 `legacy_id` mappings, NEW-01..14 and APP-01..10. Also implement the v1.1 style system: taxonomy/catalog/compatibility, preview manifest and sample generation workflow. Annotated / clean and single / sheet are variants, not separate template families.

## Privacy / public repo
- Never commit any user photo, original AIKate HTML or embedded image, prompt transcript, API key, auth token, personal workspace output, proprietary font or non-licensed image.
- Never place user's private media or cleartext personal data in logs, test snapshots or PR descriptions. Use synthetic mocks instead.
- No outbound reference-image upload without permission. No secret in source or CI.
- Before any push to a **public** remote, run privacy/secret scanning and review git staged files. Do not push without an explicitly configured remote and user authorization.

## Development
- First implement M0 only; after each milestone create tests and a clear changelog of SPEC acceptance criteria. Treat 48 curated styles and at least one reviewed real preview per style as first-release scope, not a future nice-to-have.
- Prefer Python 3.11+ for deterministic media workflows if no contrary verified constraint; use small typed interfaces and standard JSON schemas. Avoid eager dependencies.
- Tests must work without network and without image service credentials using MockProvider.
- Every produced file has real metadata (bytes, width, height, format, content hash); a prompt is not a generated image.
- Image output specifications must be validated programmatically; exact text belongs to a deterministic layout layer.
- For unsupported body topology, skip or adapt the asset template, never force human hands/feet or proportions.
- Use finite retries and explicit failure states. Preserve immutable approved character versions.

## Required per-PR checks
- Run `python scripts/secret_scan.py`, `python scripts/validate_spec.py`, `ruff check .`, `ruff format --check .`, `mypy` and `pytest` (all offline; see README).
- Update schemas, catalogs, prompts, docs and test cases together for any template or behavior change.
- Report which target host/device was actually tested, and which integrations remain unverified.

## Code review priorities
- Unauthorized image exfiltration or public asset leakage.
- Contradiction between type/topology/style rules.
- Fake image generation success, mistaken native resolution claims, incorrect print dimensions.
- Unbounded retry loops or invalid dependency DAG.
- Missing variant outputs and incomplete batch delivery.

- Public preview samples must be self-generated or otherwise clearly redistributable; do not commit third-party copyrighted reference art as style previews.

- Style IDs STYLE-001..STYLE-048 are product-facing stable IDs; do not renumber or remove without a migration. Every style needs an English prompt fragment and subject applicability.
- M1A builds planned preview requests; M2A performs real image generation only after M2 Provider integration. Do not count placeholder or mock previews toward the 48 approved images release gate.

- Before any v1 release run `python scripts/check_style_release.py`, which must fail until all 48 approved samples exist; never bypass the release gate.
