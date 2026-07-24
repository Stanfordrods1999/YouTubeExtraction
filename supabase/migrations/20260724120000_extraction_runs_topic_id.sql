-- The application inserts topic_id on every extraction_runs row
-- (db/supabaseRepository.py createExtractions), but the initial migration
-- never declared the column — local databases had it added out-of-band.
-- This captures that drift so `supabase db reset` reproduces the real schema.

alter table "public"."extraction_runs"
  add column if not exists "topic_id" uuid references public.topics(id);
