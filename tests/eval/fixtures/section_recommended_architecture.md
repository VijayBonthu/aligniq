### 4.2 Recommended Architecture (Deep Technical Breakdown)

We believe PostgreSQL on AWS RDS is the right relational store. The architecture may use multi-AZ replication with read replicas in 2 regions (us-east-1, us-west-2). To be confirmed: whether Aurora Serverless v2 is acceptable as a fallback.

- Primary store: PostgreSQL 15 on RDS, db.r6g.2xlarge.
- Caching: Redis 7 on ElastiCache, 3 nodes.
- Object storage: AWS S3 with KMS-managed keys.
- Identity: Auth0 with SAML federation to Okta.
- Observability: Datadog APM + CloudWatch metrics.

risk_level: med
impact_if_wrong: regional outage costs ~$120,000/hr in lost throughput.

Estimated capacity: 12,000 QPS sustained, 35,000 QPS burst. Storage growth projected at 4 TB/year.
[needs validation]
