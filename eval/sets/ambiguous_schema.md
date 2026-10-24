# ambiguous_100.json schema (Phase 2 ambiguity test set)

```json
{"question_id": "amb_001", "db_id": "california_schools", "base_question_id": 5,
 "question": "<the ambiguous version>", "edit": "dropped_time_range|column_synonym|vague_filter|stripped_evidence",
 "readings": [{"label": "...", "gold_sql": "..."}, {"label": "...", "gold_sql": "..."}]}
```
Built from BIRD dev questions (`data/mini_dev_sqlite.json`) by PRACTIQ-style edits (see research_notes). Each `gold_sql` executed and non-empty, and the two readings' result sets must differ (scripts/check_ambiguous.py), or it is not really ambiguous.
