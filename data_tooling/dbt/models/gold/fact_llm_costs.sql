{{ config(materialized='table', schema='gold') }}

with runs as (
  select *
  from {{ ref('stg_agent_runs') }}
)

select
  date_trunc('day', start_time) as run_day,
  user_id,
  count(*) as run_count,
  sum(coalesce(prompt_tokens, 0)) as prompt_tokens,
  sum(coalesce(completion_tokens, 0)) as completion_tokens,
  sum(coalesce(total_tokens, 0)) as total_tokens,
  round(sum(coalesce(total_cost_usd, 0)), 6) as total_cost_usd
from runs
group by 1, 2
