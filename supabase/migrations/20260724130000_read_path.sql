-- Read path: similarity search happens in Postgres, not Python.
--
-- 1. HNSW index for approximate nearest-neighbour search over unit embeddings.
-- 2. match_units(): one RPC returning the top-k units for a query embedding,
--    each joined to its source for citation (URL + discovery reason).
-- 3. topic_centroids: persists the initial and Rocchio-refined centroids per
--    graph thread, so retrieval can blend a session's refined centroid and
--    evals can compare before/after feedback.

create index if not exists extracted_units_embedding_idx
  on public.extracted_units using hnsw (embedding vector_cosine_ops);


create table if not exists public.topic_centroids (
  id uuid primary key default gen_random_uuid(),
  thread_id text not null,
  topic_text text,
  kind text not null check (kind in ('initial', 'refined')),
  iteration int not null default 0,
  centroid public.vector(1536) not null,
  created_at timestamp without time zone default now()
);

create index if not exists topic_centroids_thread_idx
  on public.topic_centroids (thread_id, created_at desc);

grant select, insert on table public.topic_centroids to anon;
grant select, insert on table public.topic_centroids to authenticated;
grant select, insert, update, delete on table public.topic_centroids to service_role;


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
