# Diagrams explained

Each diagram has two plain-text explanations: one for a child, and one you could say out loud to an interviewer. The interviewer version ends with a likely follow-up question and says honestly what is not built yet. The index of all diagrams is in [README.md](README.md).

## 1. Component architecture

Diagram: [architecture.md](../architecture.md#component-view)

**Like I'm 5.** Imagine a post office. A person hands over a letter asking for help with a cancelled flight. A friendly clerk reads it and asks a very smart helper what to do. The helper is allowed to look things up in a big book of rules and to use a calculator, but the helper is never allowed to give out money. If something needs money or a stamp, the clerk writes a note and puts it in a box. Only the boss, a real person, can open the box and say yes or no. Everything is written down in one big notebook that everybody shares, so nothing gets lost.

**For an interviewer.** Ombuds triages EU261 airline compensation claims. A FastAPI app receives a claim and a use case runs a LangGraph agent. The agent calls an LLM, which can only use three tools: search the policy knowledge base, check eligibility with a deterministic rules engine, and log a claim. The model asks for eligibility, it never decides it. Anything that changes state does not execute inline. It submits an approval request, and a human approves it before the action runs. Postgres with pgvector holds claims, payments, approvals and the knowledge base embeddings, so there is one database to operate. Code is feature-sliced: claims-specific code is separate from a feature-agnostic platform layer (LLM providers, guardrails, MCP, infrastructure), and only the composition roots wire them together. The trade-off is more structure than a prototype needs, in exchange for a second vertical being cheap to add. Honest gap: tracing, the Rego payout policy and the audit trail are Week 4 stubs, so there is no policy engine in front of the approval gate yet.

**Likely follow-up.** Why not let the LLM decide eligibility? Because it is a legal calculation with exact tiers, so a deterministic engine is auditable and the model's answer is checked against it.

## 2. Triage and approval sequence

Diagram: [architecture.md](../architecture.md#triage-and-approval-flow)

**Like I'm 5.** Think of ordering something from a shop with a parent. You tell the shop what you want. The shop checks your message for tricks and covers up private things like your address. A helper reads it, looks up the rules, and writes a form that says "this child may get a refund of this much". But the form is only a request. It goes into a tray. Later, a grown-up looks at the tray, reads the form, and signs it. Only after the signature does anything happen, and it happens exactly one time. Until then, nothing has changed anywhere.

**For an interviewer.** This sequence shows one triage and then the later approval, which are two separate moments. In the first, the API screens the claim for prompt injection and redacts personal data, then the agent loop runs. The only state-changing tool the agent has, log_claim, does not write anything. It submits a payload-bound approval request. The payload is derived from the rules engine, never from model text, and the claim identifier is issued by the server, so the model cannot choose it. In the second moment, a human calls the approvals API. Approving runs an executor registered for that action, which writes to Postgres, and the request moves to executed exactly once. This is the decision in ADR-0009. The alternative, a LangGraph interrupt with a checkpointer, ties approvals to graph checkpoints and does not cover external MCP clients, so it was rejected for now. The cost is that the agent cannot tell the passenger the final outcome in the same run. Honest gap: until the Rego policy exists, log_claim also needs a human, though the target is to auto-approve it by policy.

**Likely follow-up.** What if the executor fails after approval? The request stays approved, the write is idempotent, and execute_approved can be re-run safely, although nothing calls it automatically yet.

## 3. Guardrails and tool scoping

Diagram: [architecture.md](../architecture.md#guardrails-and-tool-scoping)

**Like I'm 5.** Picture a mailroom in front of a very clever robot. Before any letter reaches the robot, a guard checks whether the letter is secretly bossing the robot around, like "forget your rules". If it is, the letter goes straight to a person and the robot never sees it. Then someone paints over private things such as phone numbers and bank numbers. The robot also only gets three tools in its toolbox, and the dangerous one, paying money, is locked away. The robot can ask for things, but the grown-up rules decide what really happens.

**For an interviewer.** Governance is layered, and each layer assumes the one before it can fail. First, a heuristic injection detector screens the claim, and a hit returns an escalated result with no model call at all (ADR-0014). Second, PII is redacted before the model sees the text, again in tool-call arguments through a guarded dispatcher, and again in the answer, explanation and escalation reason (ADR-0013). Third, tool scoping offers the agent only search_kb, check_eligibility and log_claim, and overwrites any claim identifier the model supplies with the server-issued one. issue_payment is never offered to the agent. Fourth, log_claim recomputes eligibility with the rules engine and only submits an approval request. The point is that the model's authority ends at the tool boundary. Trade-offs: regex detection will miss paraphrases and unseen languages, and PII redaction is pattern-based. Honest gaps: tool results are not filtered, and no policy engine sits before the approval request yet.

**Likely follow-up.** If injection detection is bypassed, what is the blast radius? Small, because the model has no payment tool, cannot pick the claim id, and any action still needs a human approval.

## 4. RAG and evals

Diagram: [architecture.md](../architecture.md#rag-and-evals)

**Like I'm 5.** Imagine a library with a helpful librarian. First, someone cuts the rule books into small pieces, one for each topic, and gives each piece a special number code that describes what it is about. When you ask a question, the librarian turns your question into a code too and finds the pieces with the closest codes. If nothing is close enough, the librarian says "I do not know" instead of guessing. To check the librarian is good, we keep a list of practice questions with the right answers and test different "close enough" levels until we find the best one.

**For an interviewer.** The knowledge base is three airline policy markdown files. Ingest chunks them by heading with a maximum of 1000 characters, embeds the chunks in batches with an OpenAI embedding model (1536 dimensions), and replaces each source's rows in pgvector in one transaction, so re-running ingest is safe. At query time the retriever embeds the question, orders by cosine distance with an HNSW index, and drops anything scoring under 0.35, so an off-topic question returns nothing and the agent cannot cite what it did not find. The 0.35 floor is not a guess. The eval harness retrieves once per question for 30 gold questions, then sweeps eleven floors over the saved scores without re-embedding, reporting hit at 1, 3 and 5, mean reciprocal rank and off-topic rejection (ADR-0012). Trade-off: one database for vectors and relational data keeps operations simple but is not built for huge corpora. Honest gap: there is no end-to-end agent or prompt eval yet. The airline_claims dataset is empty, so only retrieval is measured.

**Likely follow-up.** Why not Chroma? pgvector keeps claims, approvals and embeddings in one transactional store (ADR-0010).

## 5. MCP process boundary

Diagram: [architecture.md](../architecture.md#mcp-process-boundary)

**Like I'm 5.** Imagine the helper robot lives in one room and the toolbox lives in another room. They cannot walk to each other, so they pass notes through a small slot in the wall. The robot writes what it wants on a note, the toolbox reads it, does the job, and passes the answer back through the slot. The nice part is that other robots, from other companies, can also use the same slot and the same toolbox. And a guard at the slot covers up private things on every note.

**For an interviewer.** MCP, the Model Context Protocol, lets the same tools be used by our agent and by external clients such as Claude Desktop. The server lives inside the platform package, a subpackage and not a separate service (ADR-0003). It is started with python -m ombuds.platform.mcp.server and talks over stdio. When run_triage is called with use_mcp set, it spawns that server as a subprocess. Because graph nodes are synchronous and the MCP session is async, the client runs the session on a background thread through an anyio blocking portal. The graph does not care which dispatcher it has, because both satisfy the same protocol. The server builds the same Postgres-backed runtime as the API, so an approval submitted over MCP appears in the approvals API, and arguments are redacted at the boundary. Trade-off: a subprocess adds startup cost and a failure mode, but keeps one codebase and one deploy. Honest gap: the HTTP routes do not use MCP, and external clients can reach issue_payment, still behind a human approval.

**Likely follow-up.** Why not run MCP as its own microservice? It would add a deployment and network hop with no benefit for a single repository.

## 6. Data model

Diagram: [architecture.md](../architecture.md#data-model)

**Like I'm 5.** Think of a filing cabinet with five drawers. One drawer holds requests waiting for a grown-up to say yes. One holds claims that were written down. One holds payments, and each payment must be stuck to a claim, so you can never have a payment for a claim nobody wrote down. One holds little notes about each person, and one holds the pieces of the rule book with their number codes. Each drawer has a clear label, and some drawers have a rule like "no two folders may be the same".

**For an interviewer.** Everything lives in one Postgres database with pgvector. approval_requests holds the action, a JSON payload, a payload key and a status constrained to pending, approved, denied or executed. Uniqueness on action plus payload key is the dedupe: a retried submit is an insert that does nothing on conflict, not a read-then-write race. claims stores the facts and the rules-engine decision, with a server-issued identifier. payments has the only foreign keys: one payment per claim, only for a logged claim, linked to the approval that authorised it, with an amount above zero. long_term_memory and kb_chunks stand alone, and kb_chunks has a 1536-dimension vector with an HNSW cosine index. The claim identifier inside an approval payload is a logical link, not a foreign key. Migrations are numbered SQL files applied under an advisory lock, so the API and the MCP server can start together. Trade-off: one store is simpler, but vector search scale is limited. Honest gap: there is no audit table yet, because the audit repository is a stub.

**Likely follow-up.** How do you stop a double payment? The primary key on claim id in payments, plus an insert that ignores conflicts, makes retries a no-op.

## 7. Layering and composition roots

Diagram: [architecture.md](../architecture.md#layering)

**Like I'm 5.** Imagine building with LEGO and one rule: bricks on top can lean on bricks below, but the bricks below must never need the ones on top. The bottom layer holds the simple facts about the world. The middle layer holds the general tools anyone could use, like a locksmith kit. The top layer holds the special things for this one job, like handling flight claims. Two special spots, the front door and the side door, are allowed to connect the top and the middle, and that is the only place where they are glued together.

**For an interviewer.** The code is feature-sliced (ADR-0002). Imports run features to platform to domain, never the reverse. The platform has no airline or triage knowledge, so a second vertical would add a folder next to claims_triage rather than touch the platform. Only the composition roots wire a feature into the platform: the FastAPI app and the MCP server entrypoint. Both call build_runtime with a Postgres pool, which assembles the approval store, the executors and the tool registry, so the API and the MCP subprocess share one wiring. create_app also accepts an injected store and registry, so tests can pass in-memory fakes. The alternative was classic clean layers, which scatter one feature across many folders. Trade-off: more folders for a small codebase today. Honest gap: the rule is only a convention. Nothing in lint or tests checks import direction, and the one platform file that imports from features is the MCP server, a root by design. An import-linter check would enforce it.

**Likely follow-up.** How would you enforce the rule automatically? Add import-linter contracts to CI and fail on a reverse import.

## 8. Approval lifecycle

Diagram: [ADR-0009](../decisions/0009-approval-request-is-the-pending-action.md#lifecycle-of-an-approval-request)

**Like I'm 5.** Think of a permission slip for a school trip. It starts as "waiting". A teacher can say yes, then the slip is "approved", or no, then it is "denied" and the story ends. After a yes, the trip happens and the slip is stamped "used". A used slip cannot be used again, and a denied slip cannot be turned into a yes. If the bus breaks down before the stamp, the slip stays "approved" and the trip can be tried again, but it still only happens once.

**For an interviewer.** An approval request has four states: pending, approved, denied and executed. Submitting dedupes on action plus payload, so the same payload returns the existing request and changed facts create a new one. Every transition is a compare-and-set update that only succeeds if the row is still in the expected status, so two concurrent approvals cannot both win, and a second approve, or a deny after approval, raises a state error that the API returns as 409. Approving wins pending to approved, runs the executor registered for the action, then wins approved to executed. The executor write is idempotent, using insert on conflict do nothing, and runs before the final transition. The transaction model is idempotent write, then claim, instead of one database transaction, which keeps the store protocol free of connection handling and works for effects outside Postgres. Trade-off: a crash in between leaves the request approved, and execute_approved is the recovery path. Honest gap: nothing calls that recovery automatically yet, so a failed execution surfaces as an error from approve.

**Likely follow-up.** Why not one transaction for the write and the status change? It would couple the store to the executor and break for non-Postgres effects.
