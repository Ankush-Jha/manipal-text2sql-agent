# conversations_50.json schema (Phase 2 follow-ups test set)

One entry per conversation:
```json
{
  "conv_id": "cs_001",
  "db_id": "california_schools",
  "turns": [
    {"question": "...", "standalone": "<same as question for turn 1>", "gold_sql": "...", "type": "root"},
    {"question": "<the follow-up as a user would type it>", "standalone": "<hand-written, fully self-contained>", "gold_sql": "...", "type": "add_filter|replace_value|change_agg|coref|ellipsis|topic_shift|undo", "depends_on_turn": 1},
    {"question": "...", "standalone": "...", "gold_sql": "...", "type": "...", "depends_on_turn": 2}
  ]
}
```
Rules: every `gold_sql` is executed and checked non-empty before the conversation is kept (scripts/check_conversations.py).
~4-5 conversations per BIRD dev DB, spread evenly across the 7 follow-up types across turns 2-3.
Freeze this file before prompt tuning; iterate on `conversations_dev_20.json` (same schema, smaller) instead.
