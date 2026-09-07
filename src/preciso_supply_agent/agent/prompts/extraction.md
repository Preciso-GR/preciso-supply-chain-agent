Extract exactly one uploaded source document into one PRECISO-compatible JSON
object. Use only the supplied source and canonical-ID registry. Return JSON
only. Preserve the source filename, source wording, effective date, aliases,
uncertainty, and temporal qualifications. Every entity and relationship must
cite exactly one real chunk from this same document.

Return this complete shape, including empty arrays when no supported facts are
documented:

```json
{
  "document_id": "document:stable-source-id",
  "file_path": "source.md",
  "snapshot_effective_date": "YYYY-MM-DD",
  "chunks": [{"chunk_id": "source.md#chunk_001", "content": "exact source passage", "chunk_order_index": 0, "file_path": "source.md"}],
  "entities": [{"entity_name": "company:example", "entity_type": "COMPANY", "description": "documented claim", "source_id": "source.md#chunk_001", "file_path": "source.md"}],
  "relationships": [{"src_id": "company:example", "tgt_id": "facility:example:site", "keywords": "OPERATES", "description": "documented claim", "source_id": "source.md#chunk_001", "file_path": "source.md", "weight": 1.0}]
}
```

Allowed entity types: `COMPANY`, `FACILITY`, `COMPONENT`, `PRODUCT`.
Allowed directed relationships only: `COMPANY --OPERATES--> FACILITY`,
`FACILITY --MANUFACTURES--> COMPONENT`, and `COMPONENT --USED_IN--> PRODUCT`.
Use canonical IDs when evidence supports them; otherwise create stable IDs in
those shapes. Never emit reverse edges or other relationship keywords. Do not
infer unsupported dependency, inventory, capacity, delay, risk, business-impact,
or current-sourcing claims. A planned or announced relationship must retain its
temporal qualification in its description.
