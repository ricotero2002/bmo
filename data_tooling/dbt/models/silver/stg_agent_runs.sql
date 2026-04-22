{{ config(materialized='table', schema='silver') }}

with source_data as (
  select *
  from {{ source('lakehouse_bronze', 'raw_llm_traces') }}
),

cleaned as (
  select
    run_id,
    name,
    cast(start_time as timestamp) as start_time,
    cast(latency_ms as double) as latency_ms,
    lower(trim(status)) as status,
    user_id,
    thread_id,
    test_type,
    tags,
    split(regexp_replace(coalesce(tags, ''), '\\s+', ''), ',') as tags_array,
    cast(prompt_tokens as bigint) as prompt_tokens,
    cast(completion_tokens as bigint) as completion_tokens,
    cast(total_tokens as bigint) as total_tokens,
    cast(total_cost_usd as double) as total_cost_usd,
    source_type,
    ingested_at,
    case when lower(trim(status)) = 'error' then true else false end as is_error
  from source_data
)

select *
from cleaned
