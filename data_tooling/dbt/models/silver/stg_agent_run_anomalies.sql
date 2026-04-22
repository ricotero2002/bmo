-- Silver anomaly model.
-- TODO: later you can add richer anomaly classification.

{{ config(materialized='table', schema='silver') }}

with staged as (
    select *
    from {{ ref('stg_agent_runs') }}
)

select
    run_id,
    name,
    start_time,
    latency_ms,
    status,
    user_id,
    thread_id,
    test_type,
    tags,
    tags_array,
    prompt_tokens,
    completion_tokens,
    total_tokens,
    total_cost_usd,
    source_type,
    ingested_at,
    is_error
from staged
where is_error = true
