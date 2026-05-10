## 7. Risks & Mitigations

We believe the following risks could potentially impact delivery. To be determined: severity weighting once the steering committee meets.

- **Vendor lock-in to AWS**: heavy use of RDS, S3, KMS, and ElastiCache creates switching cost. Mitigation: keep persistence abstractions thin; budget 4 weeks for portability spike in Q3.
- **Postgres upgrade gap**: client currently runs PostgreSQL 11; jumping to 15 may require 2 weeks of compatibility work. Mitigation: stage on 13 first.
- **Auth0 cost ramp**: at 50,000 monthly active users, Auth0 enterprise tier runs $42,000/yr. Mitigation: revisit at 30,000 MAU.
- **Datadog log spend**: projected $18,000/yr at full ingestion. Mitigation: drop debug-level logs in prod.

risk_level: high
impact_if_wrong: 6–8 weeks of replatforming work and ~$220,000 in unplanned spend.

[needs validation by infra lead]
