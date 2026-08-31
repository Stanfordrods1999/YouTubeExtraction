-- Tier 0.1 — keep every embedding attached to the text it was computed from.
--
-- `extracted_units.content` and `.semantic_type` already exist in the initial
-- migration, but nothing ever wrote them: `updateUnitEmbeddings` inserted rows
-- holding only {extraction_run_id, embedding}. Every stored vector was therefore
-- orphaned — a nearest neighbour could be found but not read.
--
-- `unit_index` is the missing piece: the ordinal of a unit inside its extraction
-- run's `metadata` array. It gives each unit a stable identity, which is what
-- makes re-embedding a run idempotent instead of duplicative.

alter table "public"."extracted_units"
  add column if not exists "unit_index" integer;

-- One row per (run, ordinal). This is the conflict target for the upsert in
-- SupabaseRepository.updateUnitEmbeddings; without it, re-running the embed node
-- appends a second full copy of every unit.
create unique index if not exists extracted_units_run_unit_index_key
  on public.extracted_units (extraction_run_id, unit_index);

-- Rows written before this migration have content = null and unit_index = null,
-- and their position in the metadata array is not recoverable (the whole batch
-- shares one created_at). They cannot be backfilled — delete and re-embed:
--
--   delete from extracted_units where content is null;
