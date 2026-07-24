-- Reliability & corroboration:
--
-- 1. Idempotent source discovery: a unique (topic_id, source_url) key lets
--    createSources upsert, so node retries / re-runs can't duplicate rows.
-- 2. corroboration_count on extracted_units: near-duplicate facts collapse
--    into one canonical unit that records how many independent sources
--    stated it.
-- 3. dedupe_units(run_id, threshold): for each unit of a run, finds the
--    nearest unit of the same topic from OTHER runs; above the cosine
--    threshold the new unit is deleted and the canonical one's count bumped.
-- 4. match_units gains corroboration_count in its result (return-shape
--    change requires drop + recreate).

create unique index if not exists sources_topic_url_key
  on public.sources (topic_id, source_url);


alter table "public"."extracted_units"
  add column if not exists "corroboration_count" int not null default 1;


create or replace function public.dedupe_units(
  run_id uuid,
  threshold double precision default 0.95
)
returns int
language plpgsql
as $$
declare
  unit record;
  canonical record;
  removed int := 0;
begin
  for unit in
    select eu.id, eu.embedding, er.topic_id
    from public.extracted_units eu
    join public.extraction_runs er on er.id = eu.extraction_run_id
    where eu.extraction_run_id = run_id
      and eu.embedding is not null
  loop
    select eu2.id, 1 - (eu2.embedding <=> unit.embedding) as sim
      into canonical
      from public.extracted_units eu2
      join public.extraction_runs er2 on er2.id = eu2.extraction_run_id
      where er2.topic_id = unit.topic_id
        and eu2.extraction_run_id <> run_id
        and eu2.embedding is not null
      order by eu2.embedding <=> unit.embedding
      limit 1;

    if canonical.id is not null and canonical.sim >= threshold then
      update public.extracted_units
        set corroboration_count = corroboration_count + 1
        where id = canonical.id;
      delete from public.extracted_units where id = unit.id;
      removed := removed + 1;
    end if;
  end loop;

  return removed;
end
$$;

grant execute on function public.dedupe_units to anon, authenticated, service_role;


drop function if exists public.match_units(public.vector, int, uuid);

create or replace function public.match_units(
  query_embedding public.vector(1536),
  match_count int default 10,
  filter_topic uuid default null
)
returns table (
  id uuid,
  content text,
  semantic_type text,
  similarity double precision,
  corroboration_count int,
  source_id uuid,
  source_url text,
  discovery_reason text
)
language sql
stable
as $$
  select
    eu.id,
    eu.content,
    eu.semantic_type,
    1 - (eu.embedding <=> query_embedding) as similarity,
    eu.corroboration_count,
    s.id as source_id,
    s.source_url,
    s.discovery_reason
  from public.extracted_units eu
  join public.extraction_runs er on er.id = eu.extraction_run_id
  join public.sources s on s.id = er.source_id
  where eu.embedding is not null
    and eu.content is not null
    and (filter_topic is null or s.topic_id = filter_topic)
  order by eu.embedding <=> query_embedding
  limit match_count
$$;

grant execute on function public.match_units to anon, authenticated, service_role;
