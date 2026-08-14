# Analyze OCR V34

`OCR-V34` is the official local-only recipe used by the frontend `Analyze OCR`
button and the Reup Queue auto pipeline. It retains the V29 completeness-first
audio/visual scheduler and adds the latest generic temporal panel, cover union,
protected-source, residual-stroke, and encoded-output QA fixes already present in
the production runtime.

The path is:

```text
Frontend -> POST /ocr -> durable ANALYZE_OCR job -> worker
-> QualityLocalizationService.run_phase12 -> MasterPhase1Extractor
```

The browser expects `OCR-V34`; the API returns the accepted runtime, every job is
hash-bound, and the worker rejects stale bindings. OCR and geometry remain 100%
local with zero network calls. Translation remains a separate downstream AI
operation.
