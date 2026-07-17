from __future__ import annotations

import json

from sqlalchemy import create_engine, text

from src.core.settings import get_settings

engine = create_engine(get_settings().database_url)
with engine.connect() as conn:
    row = conn.execute(
        text(
            """
            SELECT left(coalesce(sp.raw_payload_json::text, ''), 400) AS raw,
                   left(coalesce(sp.metadata_json::text, ''), 400) AS meta
            FROM source_profiles sp
            WHERE sp.source_profile_external_id LIKE 'MS4wLjABAAAA965SRwbGiCEb%'
            LIMIT 1
            """
        )
    ).mappings().first()
    print(json.dumps({k: v for k, v in dict(row).items()}, ensure_ascii=True))

    item = conn.execute(
        text(
            """
            SELECT left(coalesce(ci.metadata_json::text, ''), 500) AS meta,
                   left(coalesce(cs.metadata_json::text, ''), 400) AS session_meta,
                   left(coalesce(cs.result_summary_json::text, ''), 400) AS summary
            FROM captured_items ci
            JOIN capture_sessions cs ON cs.id = ci.capture_session_id
            WHERE ci.source_profile_external_id LIKE 'MS4wLjABAAAA965SRwbGiCEb%'
            ORDER BY ci.updated_at DESC NULLS LAST
            LIMIT 1
            """
        )
    ).mappings().first()
    print("item", json.dumps({k: v for k, v in dict(item).items()}, ensure_ascii=True) if item else None)
