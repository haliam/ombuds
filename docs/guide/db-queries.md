# Useful queries for the ombuds database

Read-only queries to inspect the Postgres data from DBeaver or `psql`. Connection: `localhost:5433`, database, user and password all `ombuds` (see `docs/developer-guide.md`). Run them as a read-only connection: `audit_log` rejects updates and deletes, and nothing else here should be edited by hand.

Tables: `approval_requests` (the human-approval queue), `claims` and `payments` (what approvals executed), `audit_log` (append-only trail), `kb_chunks` (RAG), `long_term_memory`.

## 1. Orientation

```sql
-- row count per table
select 'claims' t, count(*) from claims
union all select 'payments', count(*) from payments
union all select 'approval_requests', count(*) from approval_requests
union all select 'audit_log', count(*) from audit_log
union all select 'kb_chunks', count(*) from kb_chunks
union all select 'long_term_memory', count(*) from long_term_memory;

-- applied migrations
select * from schema_migrations;
```

## 2. The approval queue

```sql
-- what is waiting for a human right now, oldest first
select id, action, created_at, payload->>'claim_id' as claim_id,
       payload->>'compensation_eur' as compensation_eur
from approval_requests
where status = 'pending'
order by created_at;

-- requests by status and action
select status, action, count(*) from approval_requests group by 1, 2 order by 1, 2;

-- approved but never executed: the executor failed and needs a retry
select id, action, approver, updated_at, payload->>'claim_id' as claim_id
from approval_requests
where status = 'approved';

-- who approved or denied what
select approver, status, count(*) from approval_requests
where approver is not null group by 1, 2;
```

## 3. Claims and payments

```sql
-- approved claims in readable form
select claim_id, created_at,
       facts->>'disruption'     as disruption,
       facts->>'distance_km'    as distance_km,
       facts->>'arrival_delay'  as arrival_delay,
       decision
from claims
order by created_at desc;

-- payments joined to their claim and the approval that released them
select p.claim_id, p.amount_eur, p.created_at, a.approver
from payments p
join approval_requests a on a.id = p.approval_request_id
order by p.created_at desc;

-- total paid out
select count(*) as payments, coalesce(sum(amount_eur), 0) as total_eur from payments;

-- claims without a payment
select c.claim_id, c.created_at
from claims c left join payments p using (claim_id)
where p.claim_id is null;
```

## 4. The audit trail

`kind` is one of `tool_call`, `policy_decision`, `approval_submitted`, `approval_approved`, `approval_executed` (and `approval_denied` for refusals).

```sql
-- latest activity
select id, occurred_at, kind, subject, outcome, claim_id
from audit_log order by id desc limit 50;

-- the full story of one claim, in order (replace the id)
select occurred_at, kind, subject, outcome, detail
from audit_log
where claim_id = '<claim_id>'
order by id;

-- the story of one approval request
select occurred_at, kind, outcome, detail
from audit_log
where approval_request_id = '<approval_request_id>'
order by id;

-- everything the OPA policy denied, and why
select occurred_at, subject, claim_id, detail->'reasons' as reasons
from audit_log
where kind = 'policy_decision' and outcome <> 'allow'
order by id desc;

-- tool calls that errored
select occurred_at, subject, claim_id, detail
from audit_log
where kind = 'tool_call' and outcome <> 'ok'
order by id desc;

-- activity per minute and kind (a good chart: X = minute, series = kind)
select date_trunc('minute', occurred_at) as minute, kind, count(*)
from audit_log group by 1, 2 order by 1, 2;

-- jump from an audit row to its trace in your tracing backend
select occurred_at, kind, subject, trace_id
from audit_log where trace_id is not null order by id desc limit 20;
```

## 5. Health checks

```sql
-- every executed approval should have an "approval_executed" audit row
select a.id, a.action
from approval_requests a
where a.status = 'executed'
  and not exists (
    select 1 from audit_log l
    where l.approval_request_id = a.id and l.kind = 'approval_executed'
  );

-- every payment should reference a claim with an approved log_claim (expect zero rows)
select p.claim_id
from payments p
where not exists (
  select 1 from approval_requests a
  where a.action = 'log_claim' and a.status = 'executed' and a.payload->>'claim_id' = p.claim_id
);

-- pending requests older than a day
select id, action, created_at from approval_requests
where status = 'pending' and created_at < now() - interval '1 day';
```

## 6. Knowledge base and memory

Never select `kb_chunks.embedding` in a grid (1536 numbers per row).

```sql
-- what the RAG index holds
select source, count(*) as chunks from kb_chunks group by 1;

-- read the chunks of one source in order
select chunk_index, left(content, 200) as preview
from kb_chunks where source = 'eu261_delays_cancellations.md'
order by chunk_index;

-- cross-run memory per claimant
select claimant_id, facts, updated_at from long_term_memory order by updated_at desc;
```

## Notes

- `->>` extracts a JSON field as text, `->` keeps it as JSON. In DBeaver, press `F7` on a JSON cell for the value panel.
- The audit insert is not in the same transaction as the state change (ADR-0016), so a crash can leave a state change without its audit row. The health checks above surface that.
- Only a dev database should ever be reset (`make db-reset`); the audit table cannot be cleared any other way.
