Repair only the supplied extraction for the supplied source document. Use the
PRECISO validation errors as the constraint. Do not add facts, relationships,
or entities that are not directly supported by the source. Keep the same
document identity, filename, and source evidence.

Preserve all valid extraction content. Modify only the smallest set of
entities, relationships, or chunks required to resolve the reported
validation errors. Do not regenerate the full extraction JSON. Return one
structured patch object only, using this shape:

{
  "operation": "replace_entity | replace_relationship | replace_chunk | add_entity | add_relationship | add_chunk | remove_entity | remove_relationship | remove_chunk",
  "match": {"stable_field": "existing value"},
  "replacement": {"only": "the fields that must change"}
}

Use stable identifiers in `match`: `entity_name` for entities, `src_id`,
`tgt_id`, and optionally `keywords` for relationships, and `chunk_id` for
chunks. Replacement edits merge only the supplied fields into the uniquely
matched object. For remove operations omit `replacement`; for add operations
use `replacement` as the new object. Never use raw text replacement, array
indexes as the only target, or a patch that changes another source document.
