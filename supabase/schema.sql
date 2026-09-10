create table if not exists public.submissions (
    submission_id text primary key,
    student_name text not null,
    student_id text not null default '',
    subject text not null,
    assignment_name text not null,
    submitted_at timestamptz not null,
    processing_status text,
    error text,
    results jsonb not null default '[]'::jsonb,
    storage_paths jsonb not null default '[]'::jsonb,
    storage_error text
);

create table if not exists public.duplicate_history (
    history_key text primary key,
    hash_value text not null,
    created_at timestamptz not null default now()
);

create index if not exists submissions_submitted_at_idx
    on public.submissions (submitted_at);

create index if not exists submissions_student_name_idx
    on public.submissions (student_name);