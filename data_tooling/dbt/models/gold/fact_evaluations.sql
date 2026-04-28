{{ config(materialized='table', schema='gold') }}

with runs as (
  select *
  from {{ ref('stg_agent_runs') }}
),

evals as (
  select *
  from {{ source('lakehouse_gold', 'agent_evaluations') }}
)

select
  r.run_id,
  date_trunc('day', r.start_time) as run_day,
  r.user_id,
  r.status,
  e.answer_relevancy,
  e.faithfulness,
  e.relevancy_reason,
  e.faithfulness_reason,
  case
    when e.run_id is not null then 'evaluated'
    when r.is_error then 'failed_before_eval'
    else 'pending_or_skipped'
  end as evaluation_state
from runs r
left join evals e on r.run_id = e.run_id