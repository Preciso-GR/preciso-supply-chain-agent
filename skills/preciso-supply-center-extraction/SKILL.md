---
name: preciso-supply-center-extraction
description: >
  Extract evidence-backed supply-chain entities and dependencies for the PRECISO
  Supply Center application. Use when uploaded source documents must become a
  validated supply_chain extraction before graph creation. Do not use for
  forecasting, inventory, delay, severity, or business-impact analysis.
---

# PRECISO Supply Center Extraction Skill

This skill is the extraction contract for the Supply Center agent. PRECISO is
the authority for validation, ingestion, graph persistence, traversal, and
evidence retrieval. The model proposes facts; it must never claim that a
proposal is graph truth before PRECISO accepts it.

## Runtime contract

- All PRECISO operations use `workspace="supply_chain"`.
- Extract only from the uploaded source documents and the supplied canonical-ID
  registry. Never use outside knowledge to complete a dependency path.
- The graph-build action is separate from asking a question. Do not query or
  ingest merely because files were uploaded; wait for the explicit create-graph
  action.
- If PRECISO validation fails, stop. Do not retry ingestion with weakened rules
  or silently rewrite unsupported facts.
- A successful model response is only a candidate extraction until PRECISO
  validation and ingestion succeed.

## Controlled ontology

Only these entity types are allowed:

| Entity type | Canonical-ID shape |
|---|---|
| `COMPANY` | `company:{company-slug}` |
| `FACILITY` | `facility:{company-slug}:{facility-slug}` |
| `COMPONENT` | `component:{company-slug}:{component-slug}` |
| `PRODUCT` | `product:{product-family}:{model}` |

Only these directed relationships are allowed:

| Source | `keywords` | Target |
|---|---|---|
| `COMPANY` | `OPERATES` | `FACILITY` |
| `FACILITY` | `MANUFACTURES` | `COMPONENT` |
| `COMPONENT` | `USED_IN` | `PRODUCT` |

Do not emit `DEPENDS_ON`, `SUPPLIES`, `PRODUCES`, `CONTAINS`, `MAKES`, or
reverse edges. Do not emit relationships about inventory, orders, alternatives,
capacity, delay, severity, risk, forecasts, or business impact.

## Identity rules

- Reuse a registry canonical ID only when the document supports the identity or
  explicitly documents the alias.
- Keep a human-readable name in `description`; keep `entity_name` stable and
  canonical.
- Never merge similar names across companies or facilities without evidence.
- If identity is ambiguous, omit the unsupported relationship and surface the
  ambiguity for review.

## Evidence rules — non-negotiable

Chunks are the only evidence surface. Every entity and relationship must cite
one real chunk in the same extraction.

- `source_id` must be exactly one existing `chunk_id` string.
- Never use comma-separated IDs, arrays, whitespace-separated IDs, or a custom
  delimiter in `source_id`.
- Do not use PRECISO's internal multi-value separator (`<SEP>`) in model output.
- If a fact appears in several chunks, choose the single chunk that most
  directly supports the fact. Duplicate the fact only when separate records
  are genuinely needed.
- Never create an entity or relationship whose `source_id` cannot be found in
  `chunks` byte-for-byte.
- Keep chunks coherent and preserve the source file path and source wording.

## Required output

Return one JSON object and no prose:

```json
{
  "document_id": "bundle:2026-09-07",
  "file_path": "uploaded-source-bundle",
  "snapshot_effective_date": "2026-09-07",
  "chunks": [
    {
      "chunk_id": "source.md#chunk_001",
      "content": "A direct source passage.",
      "chunk_order_index": 0,
      "file_path": "source.md"
    }
  ],
  "entities": [
    {
      "entity_name": "facility:example:site",
      "entity_type": "FACILITY",
      "description": "Documented facility name and supported facts.",
      "source_id": "source.md#chunk_001",
      "file_path": "source.md"
    }
  ],
  "relationships": [
    {
      "src_id": "facility:example:site",
      "tgt_id": "component:example:part",
      "keywords": "MANUFACTURES",
      "description": "Directly documented manufacturing claim.",
      "source_id": "source.md#chunk_001",
      "file_path": "source.md",
      "weight": 1.0
    }
  ]
}
```

Required top-level fields are `document_id`, `file_path`, `chunks`, `entities`,
and `relationships`. Every entity must contain `entity_name`, `entity_type`,
`description`, `source_id`, and `file_path`. Every relationship must contain
`src_id`, `tgt_id`, `keywords`, `description`, `source_id`, `file_path`, and
numeric `weight`.

## Preflight checklist

Before returning JSON, verify:

1. Every `source_id` is an exact member of the chunk ID set.
2. Every relationship endpoint exists in `entities`.
3. Every entity type is one of the four allowed types.
4. Every relationship matches the allowed source/type/target table.
5. Every claim is directly documented and includes the snapshot date where the
   application requires it.
6. No ambiguous identity or unsupported business conclusion was added.
7. Output is valid JSON with no markdown fence or explanatory prose.

## Answer boundary

After ingestion, answers may distinguish:

- **DOCUMENTED** — directly supported by a source chunk;
- **PERSISTED** — accepted and stored by PRECISO;
- **DERIVED** — obtained by traversing persisted relationships.

Facility-unavailable analysis means potential exposure through documented
dependency paths only. It does not establish that a product will be delayed,
short, unavailable, severe, or financially impacted.
