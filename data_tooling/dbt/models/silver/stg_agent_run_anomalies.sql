-- Silver anomaly model.
-- TODO: later you can add richer anomaly classification.

{{ config(materialized='table', schema='silver') }}

with staged as (
    select *
    from {{ ref('stg_agent_runs') }}
)

select *
from staged
where is_error = true
