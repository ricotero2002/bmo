{{ config(materialized='table', schema='gold') }}

with runs as (
  select *
  from {{ ref('stg_agent_runs') }}
)

select
  date_trunc('day', start_time) as run_day,
  count(*) as run_count,
  avg(latency_ms) as avg_latency_ms,
  max(latency_ms) as max_latency_ms,
  min(latency_ms) as min_latency_ms,
  sum(case when status = 'success' then 1 else 0 end) as success_runs,
  sum(case when status = 'error' then 1 else 0 end) as error_runs,
  case
    when count(*) = 0 then 0
    else sum(case when status = 'success' then 1 else 0 end) * 1.0 / count(*)
  end as success_rate
from runs
group by 1
