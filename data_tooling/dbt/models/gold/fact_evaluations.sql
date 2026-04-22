{{ config(materialized='table', schema='gold') }}

with runs as (
  select *
  from {{ ref('stg_agent_runs') }}
)

select
  run_id,
  date_trunc('day', start_time) as run_day,
  user_id,
  source_type,
  status,
  case
    when status = 'success' then 'pending_deepeval'
    else 'failed_before_eval'
  end as evaluation_state,
  cast(null as double) as faithfulness_score,
  cast(null as double) as answer_relevancy_score,
  cast(null as double) as context_precision_score,
  cast(null as double) as context_recall_score,
  ingested_at
from runs
