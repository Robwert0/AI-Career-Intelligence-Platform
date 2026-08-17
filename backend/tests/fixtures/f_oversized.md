# Grace Hopper

## Summary

Distributed systems engineer with a decade of experience on high-throughput ingestion
pipelines and the operational work that keeps them honest.

## Work Experience

### Principal Engineer — Univac Systems (2020–present)

Owned the ingestion tier that processes roughly forty million events an hour across three
regions. Replaced a bespoke sharding scheme with consistent hashing, which cut rebalancing
downtime from around ninety minutes per node replacement to under thirty seconds, and removed
the manual runbook that had previously guarded the operation.

Led the migration from a single Postgres primary to a partitioned topology with logical
replication. The cutover ran with dual writes and a shadow-read comparison over six weeks,
which caught two serialisation bugs that integration tests had not, both in code paths that
only appear under concurrent updates to the same aggregate.

Introduced structured tracing across eleven services, then spent an unglamorous quarter
deleting the log statements it made redundant. Median incident diagnosis time fell from about
forty minutes to under ten, mostly because engineers stopped guessing which service was at
fault before opening a dashboard.

Rewrote the retry layer after a cascading failure took the pipeline down for two hours. The
new design uses exponential backoff with jitter, per-dependency circuit breakers, and a dead
letter queue with a replay tool, so a downstream outage degrades throughput instead of losing
events outright.

Ran the on-call rotation for two years and wrote the postmortem template the organisation
still uses. Reduced pages per week from twenty-two to four, largely by deleting alerts nobody
had ever acted on and by fixing the three underlying causes behind most of the rest.

Mentored six engineers through promotion, three of whom now lead teams of their own. Built
the internal onboarding track for the data platform, which cut time-to-first-production-change
for new joiners from about five weeks to eight days.

### Senior Engineer — Remington Data (2016–2020)

Built the batch reconciliation system that compared upstream ledgers against internal state
nightly, surfacing roughly two hundred discrepancies a month that had previously gone unnoticed
until quarter end. Wrote the tooling that let finance resolve them without engineering help.

Maintained the company's first Kubernetes deployment, including the parts nobody wanted to
own: certificate rotation, node upgrades, and the admission controllers that stopped teams
deploying containers without resource limits.

Wrote the schema migration tooling after a hand-run ALTER locked the primary table for eleven
minutes during business hours. The replacement runs migrations in shadow tables with backfill
in batches, verifies row counts before the swap, and refuses to run a lock-taking statement
against a table above a configured row count without an explicit override flag.

Owned the data retention work required for regulatory compliance, which meant reconstructing
which of forty-one tables actually contained personal data. Roughly a third of the answers
contradicted the documentation, and two tables nobody could name an owner for turned out to
hold six years of customer support transcripts.

Built the query analysis dashboard that surfaced the twelve slowest queries by total time
rather than by mean latency, which reordered the optimisation backlog completely. The worst
offender ran in forty milliseconds and executed four million times an hour.

## Projects

Ledger Replay is a single long paragraph on purpose, because it exists to force the chunker past paragraph-level packing and into sentence-level splitting. It is a deterministic event-sourcing engine that rebuilds account state from an append-only log, and it was written to understand why replay is harder than it looks in the textbooks. The core problem is that events arrive out of order across partitions, so a naive fold over the log produces different answers depending on which partition the reader drains first. The engine solves this with vector clocks per aggregate and a bounded reorder buffer, which trades a small amount of latency for deterministic output. Reads are served from materialised snapshots taken every ten thousand events, and a background compaction process prunes the log behind the oldest live snapshot. The snapshot format is versioned, because the first version was wrong and migrating it taught more about schema evolution than any amount of reading had. Benchmarks replay about two hundred thousand events a second on a laptop, which is fast enough that the bottleneck is the disk rather than the fold. The test suite includes a property-based generator that produces random interleavings of a known event set and asserts that every interleaving converges on the same final state, which found four ordering bugs that example-based tests had missed entirely. There is also a chaos mode that drops and duplicates events at random to confirm the idempotency guarantees hold, because at-least-once delivery is the only guarantee the upstream broker actually provides. The whole thing is about four thousand lines of Rust with no dependencies outside the standard library and a serialisation crate, which was a deliberate constraint to keep the replay logic auditable by reading it. Documentation lives beside the code as executable examples, so a doc comment that stops being true fails the build rather than quietly misleading the next reader. The command line interface exposes replay, snapshot, compact and verify as separate subcommands, because conflating them in the first version made it impossible to reason about which operation had corrupted state when something went wrong. Observability was retrofitted rather than designed in, which was a mistake worth recording: adding span boundaries after the fact meant restructuring three functions that had been written as single long folds. There is a benchmark harness that pins CPU affinity and disables frequency scaling before measuring, because the first round of numbers varied by forty percent between runs and the variance turned out to be thermal rather than algorithmic. The reorder buffer size is configurable and defaults to eight thousand events, a number chosen by measuring the ninety-ninth percentile partition skew in production traffic rather than by intuition. Failure injection covers broker restarts, disk-full conditions and clock skew between partitions, the last of which exposed an assumption that timestamps were monotonic within a partition when they are only monotonic per producer.

## Technical Skills

Rust, Python, SQL, Go. PostgreSQL with logical replication, Kafka, Redis. Kubernetes,
Terraform, Prometheus.

## Education

BSc Mathematics, Yale (2012–2016).
