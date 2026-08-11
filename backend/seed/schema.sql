-- Ripple - Supabase (Postgres) schema
--
-- Apply this once in the Supabase SQL editor, then load seed.sql.
-- seed.sql is generated; this file is hand-maintained.
--
-- Design notes:
--  * `prerequisites` is a table, not an array column on `courses`, because real
--    requirements are OR-groups ("CS 225 or MTH 231") and an array cannot
--    express that. Rows sharing a group_id are ORed; separate groups are ANDed.
--  * `registration_state` is keyed by (course_id, term). A missing row means the
--    course is not offered that term.
--  * Every row in `student_states` is synthetic. The `synthetic` column is
--    CHECK-constrained to true so real student data cannot be inserted here.

-- ---------------------------------------------------------------------------
-- programs
-- ---------------------------------------------------------------------------
create table if not exists programs (
    program            text primary key,
    institution        text    not null,
    label              text    not null,
    catalog_year       text    not null,
    total_min_credits  integer not null check (total_min_credits >= 0),
    -- Public catalog provenance, required by the competition compliance rules.
    source_url         text    not null,
    accessed           text    not null
);

-- ---------------------------------------------------------------------------
-- courses
-- ---------------------------------------------------------------------------
create table if not exists courses (
    course_id         text primary key,
    title             text    not null,
    credits           integer not null check (credits between 0 and 16),
    -- Seasons the course is normally offered: subset of {FA, WI, SP, SU}.
    -- Fall-only / spring-only courses are the main source of plan fragility.
    offered_terms     text[]  not null check (array_length(offered_terms, 1) >= 1),
    typical_capacity  integer not null check (typical_capacity >= 0)
);

-- ---------------------------------------------------------------------------
-- prerequisites  (course_id requires requires_course_id)
-- ---------------------------------------------------------------------------
create table if not exists prerequisites (
    course_id           text not null references courses (course_id) on delete cascade,
    requires_course_id  text not null references courses (course_id) on delete cascade,
    relation            text not null check (relation in ('AND', 'OR')),
    group_id            text not null,
    primary key (course_id, requires_course_id, group_id),
    -- A course cannot be its own prerequisite. Deeper cycles are rejected in
    -- application code via networkx.is_directed_acyclic_graph.
    constraint prerequisites_no_self_loop check (course_id <> requires_course_id)
);

create index if not exists prerequisites_course_idx  on prerequisites (course_id);
create index if not exists prerequisites_requires_idx on prerequisites (requires_course_id);

-- ---------------------------------------------------------------------------
-- degree_requirements
-- ---------------------------------------------------------------------------
create table if not exists degree_requirements (
    program           text    not null references programs (program) on delete cascade,
    requirement_id    text    not null,
    label             text    not null,
    min_credits       integer not null check (min_credits >= 0),
    -- Satisfy at least n_of_m courses drawn from eligible_courses.
    n_of_m            integer not null check (n_of_m >= 1),
    eligible_courses  text[]  not null check (array_length(eligible_courses, 1) >= 1),
    primary key (program, requirement_id)
);

-- ---------------------------------------------------------------------------
-- registration_state  (seat availability per course per term)
-- ---------------------------------------------------------------------------
create table if not exists registration_state (
    course_id        text    not null references courses (course_id) on delete cascade,
    -- Term code such as '2026FA'.
    term             text    not null check (term ~ '^[0-9]{4}(FA|WI|SP|SU)$'),
    available_seats  integer not null check (available_seats >= 0),
    total_seats      integer not null check (total_seats >= 0),
    primary key (course_id, term),
    constraint registration_seats_sane check (available_seats <= total_seats)
);

create index if not exists registration_state_term_idx on registration_state (term);

-- ---------------------------------------------------------------------------
-- student_states  (SYNTHETIC PERSONAS ONLY)
-- ---------------------------------------------------------------------------
create table if not exists student_states (
    student_id              text primary key,
    display_name            text    not null,
    -- Enforced at the schema level: Ripple stores no real student records.
    synthetic               boolean not null default true check (synthetic = true),
    scenario                text    not null,
    program                 text    not null references programs (program) on delete cascade,
    completed_courses       text[]  not null default '{}',
    current_term            text    not null check (current_term ~ '^[0-9]{4}(FA|WI|SP|SU)$'),
    target_graduation_term  text    not null check (target_graduation_term ~ '^[0-9]{4}(FA|WI|SP|SU)$'),
    max_term_credits        integer not null check (max_term_credits >= 1),
    min_term_credits        integer not null check (min_term_credits >= 0),
    constraint student_credit_window check (min_term_credits <= max_term_credits)
);

-- ---------------------------------------------------------------------------
-- Row level security
-- ---------------------------------------------------------------------------
-- The catalog is public reference data, so anonymous reads are safe and let the
-- API use the anon key. Writes are restricted to the service role, which only
-- the backend container holds. No table here contains personal data.
alter table programs            enable row level security;
alter table courses             enable row level security;
alter table prerequisites       enable row level security;
alter table degree_requirements enable row level security;
alter table registration_state  enable row level security;
alter table student_states      enable row level security;

do $$
declare
    t text;
begin
    foreach t in array array[
        'programs', 'courses', 'prerequisites',
        'degree_requirements', 'registration_state', 'student_states'
    ]
    loop
        execute format(
            'drop policy if exists %I on %I', t || '_public_read', t
        );
        execute format(
            'create policy %I on %I for select using (true)',
            t || '_public_read', t
        );
    end loop;
end $$;
