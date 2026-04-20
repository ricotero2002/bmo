-- Gold fact model skeleton.
-- TODO: aggregate daily cost and token usage per user.

{{ config(materialized='table') }}

select
  1 as placeholder
