# Caption translator Phase 2.5

Batch ZH→VI for hard-sub captions via **one** OpenAI-compatible LLM call.

## Caption AI settings (riêng biệt)

**Không** dùng / ghi đè **Translation settings** (thoại audio).

| Setting | DB key | UI |
|---------|--------|-----|
| Dialogue Translate | `translation_ai`, `translation_user_prompt` | Ops → **Translation settings** |
| Hard-sub caption | `caption_ai`, `caption_prompt` | Ops → **Caption AI settings** |

UI: Ops Console → Risk & Tools → **Caption AI settings**

1. **Caption AI** — enable override, provider, Base URL, key, model  
2. **Caption prompt** — system prompt phụ đề

## Code

```python
from src.media_pipeline.translator import translate_subtitles

vi = translate_subtitles(phase2.to_dict(), db=db, workspace_id=source_video.workspace_id)
# reads caption_ai + caption_prompt only
```

## Smoke

```bash
cd apps/api
python -m src.media_pipeline.translator
```
