# Advanced Developing on AWS — Build Spec (shared by all authoring agents)

This is the canonical design for the **Advanced Developing on AWS** 3-day course in
`/Users/jwkidd3/classes_in_development/aws_adv_dev/`. It is modeled on the sibling
intro course at `/Users/jwkidd3/classes_in_development/dev_on_aws/` (same delivery
model, same Reveal.js deck style, same lab-markdown style). Read a reference deck at
`/Users/jwkidd3/classes_in_development/dev_on_aws/presentations/03-getting-started-development.html`
and a reference lab at `/Users/jwkidd3/classes_in_development/dev_on_aws/labs/lab2a-s3-crud.md`
before writing.

## The narrative
Real-world scenario: **Cloud Air**, a legacy on-premises monolithic airline-booking
web app, is refactored into a serverless microservices architecture. Every lab
advances that refactor. Themes: the **6 Rs of migration**, the **Twelve-Factor App**,
the **Strangler Fig** pattern, polyglot persistence, event-driven resilience,
security & observability.

## Delivery model (identical to intro)
- Reveal.js single-file HTML decks, AWS-branded (orange #FF9900, navy #232F3E, blue #146EB4).
- Every lab runs in **AWS Cloud9** (m5.large, SSH, Amazon Linux 2023), `us-east-1` only.
- Shared class account; each student is `userN`, admin scoped to us-east-1 via `RestrictToUsEast1`.
- Resource prefix convention: `userN`-derived names (e.g. `cloudair-user1-*`).
- Workspace dir: `~/environment/aws-adv-dev`; env file `~/.aws-adv-dev.env` (USER_ID, AWS_REGION, ACCT).
- Course files repo: `https://github.com/jwkidd3/aws_adv_dev`, copied to `~/environment/aws-adv-dev` in Lab 1a.
- Python + boto3, AWS CLI, SAM CLI. 7 h/day (09:00–16:00), 1 h lunch, two 15-min breaks.
- NO "beginner" language anywhere — use "introductory"/"advanced" as appropriate.

## 15 teaching modules (decks live in presentations/NN-slug.html)
1.  `01-course-overview.html` — Course Overview (logistics, the Cloud Air scenario, 3-day agenda, objectives)
2.  `02-cloud-journey.html` — The Cloud Journey: Monolith & Migration (off-cloud architecture, Cloud Air monolith, migration to cloud, guardrails, the **6 Rs of migration**)
3.  `03-twelve-factor.html` — The Twelve-Factor App & Architectural Patterns (all 12 factors, architectural styles/patterns, why they matter for cloud-native)
4.  `04-services-and-iac.html` — AWS Services, Interfacing & Infrastructure as Code (service overview, CLI/SDK/API interfacing, authentication, IaC with CloudFormation, Elastic Beanstalk)
5.  `05-devops-cicd.html` — Gaining Agility: DevOps & CI/CD (DevOps culture, CI/CD pipeline stages, AWS CI/CD services: CodeCommit/CodeBuild/CodeDeploy/CodePipeline)
6.  `06-config-secrets.html` — Application Configuration & Secrets Management (12-factor config, SSM Parameter Store, Secrets Manager, rotation)
7.  `07-microservices-serverless.html` — Microservices & Serverless (monolith pain, microservice benefits/trade-offs, serverless model, Cloud Air target architecture)
8.  `08-lambda-apigw-sam.html` — Microservices with Lambda, API Gateway & SAM (Lambda deep dive, API Gateway integration, SAM templates & deploy)
9.  `09-strangling-monolith.html` — Strangling the Monolith (Strangler Fig pattern, routing/proxy, anti-corruption layer, incremental decomposition)
10. `10-polyglot-dynamodb.html` — Polyglot Persistence & DynamoDB Best Practices (right DB per job, single-table design, partition keys, GSIs, capacity modes, DAX)
11. `11-distributed-stepfunctions.html` — Distributed Complexity & Step Functions (distributed-systems pitfalls, saga pattern, Step Functions state machines, orchestration vs choreography)
12. `12-messaging-decoupling.html` — Decentralized Data & Messaging (decentralized data stores, SQS, SNS, Kinesis Streams, IoT message broker, EventBridge serverless event bus)
13. `13-eventsourcing-resilience.html` — Event Sourcing, CQRS & Designing for Resilience (event sourcing, CQRS, idempotency, retries/DLQ, designing for failure)
14. `14-security-observability.html` — Security & Observability (Lambda security, Cognito auth & JWT, debugging & traceability, X-Ray)
15. `15-course-wrap-up.html` — Course Wrap-up (what was built, the 6 Rs recap, where to go next)

## Deck content rules
- 9–12 `<section>` slides each: title slide, 7–10 content slides, a `data-background-color="#FF9900"` **lab callout** slide for the lab(s) the module sets up (omit on modules with no lab — M1, M3, M7, M15; M2 sets up Lab 1), and a `data-background-color="#146EB4"` "Coming Up" slide.
- Lab interlacing rule: **teaching content always precedes the lab callout slide.**
- Use real, correct code/CLI/YAML in `<pre><code>` blocks (boto3, AWS CLI, CloudFormation/SAM YAML, Step Functions ASL JSON). Keep snippets ≤ ~14 lines.
- `.small` notes under slides for nuance. Emoji-styled lab headers (🧪).
- Match the exact `<head>`/CSS/`<script>` boilerplate of the reference deck (reveal.js 5.1.0 CDN, same `:root` vars, same `Reveal.initialize` call). Title tag: `Module N — <Title>`.

## Lab → module map (labs live in labs/labNx-slug.md, files in labs/files/labN/)
- **Lab 1 (1a,1b,1c)** — Configure the Developer Environment — *REUSED from intro, already in repo. Do not recreate.* Set up by M2.
- **Lab 2 (2a,2b)** — Infrastructure as Code: the Cloud Air Baseline — set up by M4. 2a CloudFormation base stack (VPC/S3/DynamoDB via template); 2b Elastic Beanstalk deploy of the monolith.
- **Lab 3 (3a,3b)** — Twelve-Factor Config & Secrets — set up by M6. 3a SSM Parameter Store config; 3b Secrets Manager + rotation, read from app.
- **Lab 4 (4a,4b)** — Strangle the Monolith: First Microservice — set up by M8/M9. 4a Lambda+API Gateway microservice via SAM; 4b strangler routing (extract one endpoint, proxy the rest).
- **Lab 5 (5a,5b)** — Polyglot Persistence & Orchestration — set up by M10/M11. 5a DynamoDB single-table design + access patterns; 5b Step Functions state machine orchestrating the booking flow.
- **Lab 6 (6a,6b)** — Resilience & Scale: Event-Driven Decoupling — set up by M12/M13. 6a SQS + SNS fan-out; 6b EventBridge event bus + rule + DLQ.
- **Lab 7 (7a,7b)** — Secure & Observe — set up by M14. 7a Cognito user pool + API Gateway JWT authorizer; 7b X-Ray instrumentation + service map + cleanup.

## Lab markdown rules (match reference lab style exactly)
- Header: `# 🧪 Lab Nx — Title` then `*Hands-On Lab · NN min · Console|SDK · Day D — <theme>*`.
- Sections with per-section minute budgets: **Objectives**, **Prerequisites** (with a "Starting fresh?" `bootstrap.sh <labId>` fallback line), numbered **Steps**, optional **Discussion**, **Success Criteria** (✅ bullets).
- All resources use `$USER_ID` / `cloudair-$USER_ID-*` prefixes. Region `us-east-1`.
- Reference course files by path under `~/environment/aws-adv-dev/labN/...` (authored in Cloud9 editor; only short commands in terminal).
- Each lab ≤ ~45–55 min. First sub-lab of a service is Console-driven; follow-ups SDK/CLI/SAM.
- Provide real supporting files in `labs/files/labN/` (handlers, templates, policy JSON) and reference them.
