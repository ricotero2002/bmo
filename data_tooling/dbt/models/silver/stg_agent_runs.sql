{{ config(materialized='table', schema='silver') }}

with source_data as (
  select *
  from {{ source('lakehouse_bronze', 'raw_llm_traces') }}
),

cleaned as (
  select
    run_id,
    cast(start_time as timestamp) as start_time,
    date,
    lower(trim(status)) as status,
    error_message,
    cast(latency_ms as double) as latency_ms,
    
    -- Extracción nativa de JSON usando Spark SQL
    get_json_object(inputs_json, '$.user_info.user_id') as user_id,
    -- thread_id puede venir en los tags o lo extraemos si lo inyectaste
    get_json_object(inputs_json, '$.messages[0][1]') as user_query, 
    
    cast(prompt_tokens as bigint) as prompt_tokens,
    cast(completion_tokens as bigint) as completion_tokens,
    cast(total_tokens as bigint) as total_tokens,
    cast(total_cost_usd as double) as total_cost_usd,
    
    inputs_json,
    outputs_json,
    tools_used,
    ingested_at,
    case when lower(trim(status)) = 'error' then true else false end as is_error
  from source_data
)

select *
from cleaned
