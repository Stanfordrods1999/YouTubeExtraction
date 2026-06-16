create extension if not exists "vector" with schema "public";


  create table "public"."extracted_units" (
    "id" uuid not null default gen_random_uuid(),
    "extraction_run_id" uuid,
    "semantic_type" text,
    "content" text,
    "source_offset" text,
    "confidence" double precision,
    "embedding" public.vector(1536),
    "created_at" timestamp without time zone default now()
      );



  create table "public"."extraction_runs" (
    "id" uuid not null default gen_random_uuid(),
    "source_id" uuid,
    "extraction_strategy" text,
    "status" text,
    "confidence" double precision,
    "failure_reason" text,
    "started_at" timestamp without time zone,
    "completed_at" timestamp without time zone,
    "requires_human" boolean default false,
    "metadata" jsonb
      );



  create table "public"."sources" (
    "id" uuid not null default gen_random_uuid(),
    "topic_id" uuid,
    "source_type" text,
    "source_url" text,
    "discovery_reason" text,
    "priority_score" double precision,
    "status" text,
    "created_at" timestamp without time zone default now()
      );



  create table "public"."topics" (
    "id" uuid not null default gen_random_uuid(),
    "topic_text" text not null,
    "status" text not null,
    "created_by" text,
    "confidence" double precision,
    "created_at" timestamp without time zone default now(),
    "metadata" jsonb
      );


CREATE UNIQUE INDEX extracted_units_pkey ON public.extracted_units USING btree (id);

CREATE UNIQUE INDEX extraction_runs_pkey ON public.extraction_runs USING btree (id);

CREATE UNIQUE INDEX sources_pkey ON public.sources USING btree (id);

CREATE UNIQUE INDEX topics_pkey ON public.topics USING btree (id);

alter table "public"."extracted_units" add constraint "extracted_units_pkey" PRIMARY KEY using index "extracted_units_pkey";

alter table "public"."extraction_runs" add constraint "extraction_runs_pkey" PRIMARY KEY using index "extraction_runs_pkey";

alter table "public"."sources" add constraint "sources_pkey" PRIMARY KEY using index "sources_pkey";

alter table "public"."topics" add constraint "topics_pkey" PRIMARY KEY using index "topics_pkey";

alter table "public"."extracted_units" add constraint "extracted_units_extraction_run_id_fkey" FOREIGN KEY (extraction_run_id) REFERENCES public.extraction_runs(id) not valid;

alter table "public"."extracted_units" validate constraint "extracted_units_extraction_run_id_fkey";

alter table "public"."extraction_runs" add constraint "extraction_runs_source_id_fkey" FOREIGN KEY (source_id) REFERENCES public.sources(id) not valid;

alter table "public"."extraction_runs" validate constraint "extraction_runs_source_id_fkey";

alter table "public"."sources" add constraint "sources_topic_id_fkey" FOREIGN KEY (topic_id) REFERENCES public.topics(id) not valid;

alter table "public"."sources" validate constraint "sources_topic_id_fkey";

grant delete on table "public"."extracted_units" to "anon";

grant insert on table "public"."extracted_units" to "anon";

grant references on table "public"."extracted_units" to "anon";

grant select on table "public"."extracted_units" to "anon";

grant trigger on table "public"."extracted_units" to "anon";

grant truncate on table "public"."extracted_units" to "anon";

grant update on table "public"."extracted_units" to "anon";

grant delete on table "public"."extracted_units" to "authenticated";

grant insert on table "public"."extracted_units" to "authenticated";

grant references on table "public"."extracted_units" to "authenticated";

grant select on table "public"."extracted_units" to "authenticated";

grant trigger on table "public"."extracted_units" to "authenticated";

grant truncate on table "public"."extracted_units" to "authenticated";

grant update on table "public"."extracted_units" to "authenticated";

grant delete on table "public"."extracted_units" to "service_role";

grant insert on table "public"."extracted_units" to "service_role";

grant references on table "public"."extracted_units" to "service_role";

grant select on table "public"."extracted_units" to "service_role";

grant trigger on table "public"."extracted_units" to "service_role";

grant truncate on table "public"."extracted_units" to "service_role";

grant update on table "public"."extracted_units" to "service_role";

grant delete on table "public"."extraction_runs" to "anon";

grant insert on table "public"."extraction_runs" to "anon";

grant references on table "public"."extraction_runs" to "anon";

grant select on table "public"."extraction_runs" to "anon";

grant trigger on table "public"."extraction_runs" to "anon";

grant truncate on table "public"."extraction_runs" to "anon";

grant update on table "public"."extraction_runs" to "anon";

grant delete on table "public"."extraction_runs" to "authenticated";

grant insert on table "public"."extraction_runs" to "authenticated";

grant references on table "public"."extraction_runs" to "authenticated";

grant select on table "public"."extraction_runs" to "authenticated";

grant trigger on table "public"."extraction_runs" to "authenticated";

grant truncate on table "public"."extraction_runs" to "authenticated";

grant update on table "public"."extraction_runs" to "authenticated";

grant delete on table "public"."extraction_runs" to "service_role";

grant insert on table "public"."extraction_runs" to "service_role";

grant references on table "public"."extraction_runs" to "service_role";

grant select on table "public"."extraction_runs" to "service_role";

grant trigger on table "public"."extraction_runs" to "service_role";

grant truncate on table "public"."extraction_runs" to "service_role";

grant update on table "public"."extraction_runs" to "service_role";

grant delete on table "public"."sources" to "anon";

grant insert on table "public"."sources" to "anon";

grant references on table "public"."sources" to "anon";

grant select on table "public"."sources" to "anon";

grant trigger on table "public"."sources" to "anon";

grant truncate on table "public"."sources" to "anon";

grant update on table "public"."sources" to "anon";

grant delete on table "public"."sources" to "authenticated";

grant insert on table "public"."sources" to "authenticated";

grant references on table "public"."sources" to "authenticated";

grant select on table "public"."sources" to "authenticated";

grant trigger on table "public"."sources" to "authenticated";

grant truncate on table "public"."sources" to "authenticated";

grant update on table "public"."sources" to "authenticated";

grant delete on table "public"."sources" to "service_role";

grant insert on table "public"."sources" to "service_role";

grant references on table "public"."sources" to "service_role";

grant select on table "public"."sources" to "service_role";

grant trigger on table "public"."sources" to "service_role";

grant truncate on table "public"."sources" to "service_role";

grant update on table "public"."sources" to "service_role";

grant delete on table "public"."topics" to "anon";

grant insert on table "public"."topics" to "anon";

grant references on table "public"."topics" to "anon";

grant select on table "public"."topics" to "anon";

grant trigger on table "public"."topics" to "anon";

grant truncate on table "public"."topics" to "anon";

grant update on table "public"."topics" to "anon";

grant delete on table "public"."topics" to "authenticated";

grant insert on table "public"."topics" to "authenticated";

grant references on table "public"."topics" to "authenticated";

grant select on table "public"."topics" to "authenticated";

grant trigger on table "public"."topics" to "authenticated";

grant truncate on table "public"."topics" to "authenticated";

grant update on table "public"."topics" to "authenticated";

grant delete on table "public"."topics" to "service_role";

grant insert on table "public"."topics" to "service_role";

grant references on table "public"."topics" to "service_role";

grant select on table "public"."topics" to "service_role";

grant trigger on table "public"."topics" to "service_role";

grant truncate on table "public"."topics" to "service_role";

grant update on table "public"."topics" to "service_role";


