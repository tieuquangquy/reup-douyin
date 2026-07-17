# Douyin Wording Normalization Resume

## Current Step

Normalize Douyin module wording across `/accounts/douyin`, `/intake`, and related i18n strings.

## Done

- Audited `/accounts/douyin` component.
- Audited `/intake` component.
- Audited English and Vietnamese i18n sections related to Douyin accounts, browser profile, validation, and live fetch.
- Created normalization log and glossary.

## In Progress

- Normalize i18n strings and small UI label mappings.

## Next Exact Task

Patch `apps/web/src/lib/i18n/en.json`, `apps/web/src/lib/i18n/vi.json`, and `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`, then run web typecheck/build.

## Key Files To Continue

- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/components/intake/IntakePage.tsx`
