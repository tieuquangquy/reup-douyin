# Schema Decisions

## Workspace First, No User Table Yet

The schema includes `workspace_id` throughout the core tables, but it does not include users, roles, auth sessions, or billing yet. Phase 1 is a single local operator, and adding auth now would create unused surface area. Keeping workspaces now prevents a painful migration when multi-user SaaS support arrives.

## JSONB Usage

JSONB fields are limited to raw external payloads, tool outputs, flexible workflow settings, evidence, and metadata that is not stable enough for first-class columns yet. Core lifecycle fields, identifiers, timestamps, statuses, and relationships remain typed columns.

## Jobs Are Durable From The Start

Even before a queue runner exists, long-running work has `jobs` and `job_steps`. This avoids embedding long operations in HTTP handlers and gives future worker implementations a place for retry, resume, and progress state.

## Local Storage Through Media Assets

The schema does not store absolute local file paths as product truth. `media_assets.storage_provider` and `storage_key` can represent local disk in Phase 1 and object storage later.

