# Submission deliverables

One file per required item:

| Requirement | File |
| --- | --- |
| Machine-readable market registry | [`market-registry.json`](market-registry.json) (primary) · [`market-registry.csv`](market-registry.csv) (flat view) |
| Redacted run report | [`run-report.md`](run-report.md) (readable) · [`run-report.json`](run-report.json) (machine copy) |
| Architecture and safety note | [`architecture-and-safety.md`](architecture-and-safety.md) |
| Known limitations | [`known-limitations.md`](known-limitations.md) |
| Pre-existing materials and third-party licences | [`third-party-licences.md`](third-party-licences.md) |

The registry and run report are **generated from a live verification run** against all
twelve sources — statuses, personalisation bases and timestamps are measured, not
asserted — using the project's synthetic test profile, redacted to age band and postal
area. Regenerate them any time from the repo root:

```bash
.venv/bin/python submission/generate.py
```

`market-registry.json` also records the sixteen candidate sources that were probed and
excluded, each with the observed reason (bot-blocked, dead link, no published figures,
duplicate data, contact-details-gated funnel).
