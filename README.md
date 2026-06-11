# Advanced Developing on AWS

A 3-day, **advanced**, lab-heavy workshop that takes a real-world scenario —
**Cloud Air**, a legacy on-premises **monolithic** airline-booking application —
and refactors it into a **serverless microservices** architecture on AWS. Across
**15 hands-on labs** students apply the **6 Rs of migration**, the
**Twelve-Factor App** methodology, and the **Strangler Fig** pattern, then make
the result resilient, secure, and observable. Every lab runs inside **AWS Cloud9**.

## Audience

Full-stack, cloud, and software developers who already have:

- **Developing on AWS** (the introductory course) or equivalent working knowledge
- In-depth knowledge of at least one high-level programming language
- Working knowledge of core AWS services and public-cloud implementation

> This is the **advanced** follow-on to *Developing on AWS*. Lab 1 (developer
> environment) is shared with that course so returning students are productive in
> minutes; everything after it is new, advanced material.

## Course Objectives

- Analyze a monolithic application to find logical/programmatic break points for decomposition across AWS services
- Apply **Twelve-Factor App** concepts while migrating off a monolith
- Recommend the right AWS services for a microservices-based, cloud-native application
- Use the AWS API, CLI, and SDKs to monitor and manage AWS services
- Migrate a monolith using the **6 Rs of migration**
- Explain the SysOps/DevOps interdependencies needed to deploy microservices on AWS

## Format

- **15 Reveal.js teaching decks** (`presentations/*.html`) — paced for 15–20 min delivery
- **15 Markdown lab guides** (`labs/*.md`) — each ≤ ~50 min of keyboard time
- **~72% lab / ~28% lecture** by schedule clock
- **Every lab runs inside AWS Cloud9** — no local install on student laptops
- For each major service, the **first sub-lab is Console-driven**; follow-ups use SDK / CLI / SAM
- Shared class AWS account — each student gets an IAM user (`user1`, `user2`, …)
- Region for all labs: **`us-east-1`**
- **7 hours per day** (09:00 – 16:00), 1-hour lunch, two 15-min breaks

## The Cloud Air Scenario

Every lab advances one refactor of the same application:

```
Legacy monolith (Flask on Elastic Beanstalk)        ← Lab 2b: the "before" state
        │   strangle, factor by factor
        ▼
IaC baseline  ── S3 + DynamoDB + SSM via CloudFormation   ← Lab 2a
12-Factor config & secrets  ── Parameter Store + Secrets Manager  ← Lab 3
First microservice  ── Lambda + API Gateway via SAM, fronted by a facade  ← Lab 4
Polyglot data  ── DynamoDB single-table + Step Functions saga  ← Lab 5
Event-driven resilience  ── SQS + SNS + EventBridge + DLQs  ← Lab 6
Secure & observable  ── Cognito JWT authorizer + X-Ray tracing  ← Lab 7
```

## Lab Environment

- **Console URL:** `https://kiddcorp.signin.aws.amazon.com/console`
- **Usernames:** `user1`, `user2`, … — handed out at class start
- **Cloud9 environment:** students **create their own** in Lab 1a — new EC2, **m5.large**, **SSH**, Amazon Linux 2023, 30-min idle timeout
- **Pre-seeded per student:** the IAM user `userN` (member of the `students` group) and a shared **`LabRole`** the Cloud9 EC2 assumes. *Everything else* — Cloud9, CloudFormation/SAM stacks, DynamoDB tables, Lambda roles, S3 buckets, Cognito pools, API Gateway, SQS/SNS/EventBridge — students create in the labs.
- **Access level:** each `userN` is a **full administrator, scoped to `us-east-1`** (`AdministratorAccess` + the `RestrictToUsEast1` deny). Students are admins by design and are **not** IAM-isolated from each other — the `USER_ID` prefix convention prevents name collisions but is not a security boundary. Use throwaway training accounts.
- **Instructor pre-class setup:** run **`admin/setup-account.sh --apply`** once per account (creates `LabRole`, the `RestrictToUsEast1` region-lock policy, and the region-locked `students` group). Idempotent; dry-run by default. See [admin/README.md](admin/README.md).
- **Prefix convention:** every resource a student creates embeds their user ID — `cloudair-user1-*`, `Bookings-user1`, `CloudAir-user1`. A naming convention, not IAM-enforced.
- **Credentials:** in **Lab 1a** students attach **`LabRole`** to the Cloud9 EC2 and **turn AMTC off** so the SDK/CLI pick up the role via IMDS — no `aws configure`, no access keys on laptops.

## Module → Lab Map

Which teaching module sets up each lab. Modules without labs are concept / recap. Labs follow their paired module on the schedule (same day).

| #  | Module | Lab(s) it sets up | Day |
| -- | ------ | ----------------- | --- |
| 1  | Course Overview                                  | — (kickoff)        | 1 |
| 2  | The Cloud Journey: Monolith & Migration          | **1a, 1b, 1c**     | 1 |
| 3  | The Twelve-Factor App & Architectural Patterns   | — (concept)        | 1 |
| 4  | AWS Services, Interfacing & Infrastructure as Code | **2a, 2b**       | 1 |
| 5  | Gaining Agility: DevOps & CI/CD                   | — (concept)        | 1 |
| 6  | Application Configuration & Secrets Management    | **3a, 3b**         | 2 |
| 7  | Microservices & Serverless                       | — (concept)        | 2 |
| 8  | Microservices with Lambda, API Gateway & SAM     | **4a**             | 2 |
| 9  | Strangling the Monolith                          | **4b**             | 2 |
| 10 | Polyglot Persistence & DynamoDB Best Practices   | **5a**             | 2 |
| 11 | Distributed Complexity & Step Functions          | **5b**             | 3 |
| 12 | Decentralized Data & Messaging                   | **6a**             | 3 |
| 13 | Event Sourcing, CQRS & Designing for Resilience  | **6b**             | 3 |
| 14 | Security & Observability                         | **7a, 7b**         | 3 |
| 15 | Course Wrap-up                                   | —                  | 3 |

## Console vs. SDK Labs

| Service                | Console lab | SDK / CLI / SAM lab(s)                          |
| ---------------------- | ----------- | ----------------------------------------------- |
| Cloud9 / IAM           | Lab 1a, 1c  | Lab 1b (SDK smoke)                              |
| CloudFormation / EB    | **Lab 2a**  | Lab 2b (`eb` CLI deploy of the monolith)        |
| SSM / Secrets Manager  | —           | Lab 3a, 3b (CLI + boto3)                         |
| Lambda + API Gateway   | —           | Lab 4a (SAM), Lab 4b (strangler facade routing) |
| DynamoDB               | **Lab 5a**  | Lab 5a (single-table via boto3)                 |
| Step Functions         | **Lab 5b**  | Lab 5b (ASL + SAM deploy)                        |
| SQS / SNS              | —           | Lab 6a (CLI + boto3, DLQ)                        |
| EventBridge            | **Lab 6b**  | Lab 6b (custom bus + rule)                      |
| Cognito                | **Lab 7a**  | Lab 7a (JWT authorizer via CLI + SAM)           |
| X-Ray / SAM            | —           | Lab 7b (instrument + service map + cleanup)     |

## Three-Day Schedule

Class runs **09:00 – 16:00** each day (7 h). Lunch 60 min, two 15-min breaks.

### Day 1 — The Cloud Journey & Foundations

| Time          | Block                                            | Duration |
| ------------- | ------------------------------------------------ | -------- |
| 09:00 – 09:15 | [M1 — Course Overview](presentations/01-course-overview.html) | 15 min |
| 09:15 – 09:35 | [M2 — The Cloud Journey: Monolith & Migration](presentations/02-cloud-journey.html) | 20 min |
| 09:35 – 10:05 | **[Lab 1a — Sign In & Create Your Cloud9 Environment](labs/lab1a-signin-orientation.md)** | 30 min |
| 10:05 – 10:20 | *Break*                                          | 15 min |
| 10:20 – 10:50 | **[Lab 1b — First SDK Call in Cloud9](labs/lab1b-cli-sdk-profile.md)** | 30 min |
| 10:50 – 11:35 | **[Lab 1c — Test Permissions & Author IAM Policy](labs/lab1c-iam-policy.md)** | 45 min |
| 11:35 – 11:55 | [M3 — The Twelve-Factor App & Architectural Patterns](presentations/03-twelve-factor.html) | 20 min |
| 11:55 – 12:55 | *Lunch*                                          | 60 min |
| 12:55 – 13:15 | [M4 — AWS Services, Interfacing & Infrastructure as Code](presentations/04-services-and-iac.html) | 20 min |
| 13:15 – 14:00 | **[Lab 2a — Infrastructure as Code: the Cloud Air Baseline](labs/lab2a-iac-cloudformation.md)** | 45 min |
| 14:00 – 14:15 | *Break*                                          | 15 min |
| 14:15 – 14:30 | [M5 — Gaining Agility: DevOps & CI/CD](presentations/05-devops-cicd.html) | 15 min |
| 14:30 – 15:15 | **[Lab 2b — Deploy the Cloud Air Monolith on Elastic Beanstalk](labs/lab2b-elastic-beanstalk.md)** | 45 min |
| 15:15 – 16:00 | *Day-1 wrap / Q&A*                                | 45 min |

**Day 1 totals:** lecture 90 min · lab 195 min · **lab share 68%**

### Day 2 — Agility, Config & Microservices

| Time          | Block                                            | Duration |
| ------------- | ------------------------------------------------ | -------- |
| 09:00 – 09:20 | [M6 — Application Configuration & Secrets Management](presentations/06-config-secrets.html) | 20 min |
| 09:20 – 10:05 | **[Lab 3a — Twelve-Factor Config with SSM Parameter Store](labs/lab3a-parameter-store.md)** | 45 min |
| 10:05 – 10:20 | *Break*                                          | 15 min |
| 10:20 – 11:05 | **[Lab 3b — Secrets Management & Rotation](labs/lab3b-secrets-manager.md)** | 45 min |
| 11:05 – 11:20 | [M7 — Microservices & Serverless](presentations/07-microservices-serverless.html) | 15 min |
| 11:20 – 11:40 | [M8 — Microservices with Lambda, API Gateway & SAM](presentations/08-lambda-apigw-sam.html) | 20 min |
| 11:40 – 12:40 | *Lunch*                                          | 60 min |
| 12:40 – 13:30 | **[Lab 4a — Strangle the Monolith: First Microservice with SAM](labs/lab4a-sam-microservice.md)** | 50 min |
| 13:30 – 13:50 | [M9 — Strangling the Monolith](presentations/09-strangling-monolith.html) | 20 min |
| 13:50 – 14:35 | **[Lab 4b — Strangler Routing: Proxy the Monolith](labs/lab4b-strangler-routing.md)** | 45 min |
| 14:35 – 14:50 | *Break*                                          | 15 min |
| 14:50 – 15:05 | [M10 — Polyglot Persistence & DynamoDB Best Practices](presentations/10-polyglot-dynamodb.html) | 15 min |
| 15:05 – 15:55 | **[Lab 5a — Polyglot Persistence: DynamoDB Single-Table Design](labs/lab5a-dynamodb-singletable.md)** | 50 min |
| 15:55 – 16:00 | *Day-2 wrap*                                      | 5 min |

**Day 2 totals:** lecture 90 min · lab 235 min · **lab share 72%**

### Day 3 — Resilience, Security & Observability

| Time          | Block                                            | Duration |
| ------------- | ------------------------------------------------ | -------- |
| 09:00 – 09:15 | [M11 — Distributed Complexity & Step Functions](presentations/11-distributed-stepfunctions.html) | 15 min |
| 09:15 – 10:05 | **[Lab 5b — Orchestrating the Booking Saga with Step Functions](labs/lab5b-step-functions.md)** | 50 min |
| 10:05 – 10:20 | *Break*                                          | 15 min |
| 10:20 – 10:35 | [M12 — Decentralized Data & Messaging](presentations/12-messaging-decoupling.html) | 15 min |
| 10:35 – 11:25 | **[Lab 6a — Resilience & Scale: Decouple with SQS + SNS](labs/lab6a-sqs-sns.md)** | 50 min |
| 11:25 – 11:40 | [M13 — Event Sourcing, CQRS & Designing for Resilience](presentations/13-eventsourcing-resilience.html) | 15 min |
| 11:40 – 12:40 | *Lunch*                                          | 60 min |
| 12:40 – 13:30 | **[Lab 6b — Event-Driven Cloud Air with EventBridge](labs/lab6b-eventbridge.md)** | 50 min |
| 13:30 – 13:50 | [M14 — Security & Observability](presentations/14-security-observability.html) | 20 min |
| 13:50 – 14:40 | **[Lab 7a — Secure the API: Cognito JWT Authorizer](labs/lab7a-cognito-authorizer.md)** | 50 min |
| 14:40 – 14:55 | *Break*                                          | 15 min |
| 14:55 – 15:45 | **[Lab 7b — Observe Cloud Air with AWS X-Ray (+ cleanup)](labs/lab7b-xray-tracing.md)** | 50 min |
| 15:45 – 16:00 | [M15 — Course Wrap-up](presentations/15-course-wrap-up.html) | 15 min |

**Day 3 totals:** lecture 80 min · lab 250 min · **lab share 76%**

### Course totals

| Metric                     | Time           |
| -------------------------- | -------------- |
| Lecture (15 modules)       | 4h 20m         |
| **Hands-on lab (15 labs)** | **11h 20m**    |
| Total working time         | 15h 40m        |
| **Lab share**              | **~72%** ✓     |

## Resetting & Catching Up Students

Because every lab builds on the previous one, two scripts let an instructor drop a
student into **any** point of the course — or recycle a `userN` between cohorts.

### `bootstrap.sh <labId>` — fast-forward into any lab

On the student's Cloud9: `bash ~/environment/aws-adv-dev/bootstrap.sh <labId>`. It
idempotently provisions the **prerequisites** that lab needs (create-or-reuse each
resource) and writes the expected variables to `~/.aws-adv-dev.env`. Re-running is
safe, and it **hard-refuses** if `USER_ID` is empty or `LabRole` so a forgotten ID
fails loudly instead of colliding with the class.

| `bootstrap.sh` | Provisions |
| -------------- | ---------- |
| `1b` `1c` | env vars only (`USER_ID` / `ACCT` / region) |
| `2b` `3a` `4a` `5a` `6a` | base CloudFormation stack (S3 + `Bookings-` table + SSM) |
| `3b` | + Lab 3a SSM config params |
| `4b` | + **EB monolith** + **Flights SAM stack** |
| `5b` | + `CloudAir-` single table (created and loaded) |
| `6b` | + SQS queue/DLQ + SNS topic + subscription + queue policy |
| `7a` | + **Flights SAM stack** |
| `7b` | + Flights SAM stack + **Cognito** pool/client/user (and an `ID_TOKEN`) |

It provisions **prerequisites, not a full replay** of every prior lab — leaf
resources nothing downstream depends on (the Lab 3b secret, the Lab 5b saga) are
what the student creates *in* that lab. For a near-complete footprint, bootstrap the
heavy labs: `4b 5b 6b 7b`.

> **Timing:** deep bootstraps create real resources — EB env ~5 min, each SAM stack
> ~2–3 min — so `bootstrap.sh 4b` or `7b` from a clean slate is ~10–15 min, hands-off.

### `admin/reset-student.sh <userN> [--apply]` — wipe one student clean

Tears down a single student's **entire** footprint in dependency order: SAM stacks
(flights, saga), Cognito pool, EventBridge bus/rule/archive, SQS/SNS, worker Lambda
+ role, `CloudAir-`/`ProcessedBookings-` tables, secret, `/cloudair/<user>/` SSM
params, EB env + app, and the base stack (it empties the S3 bucket first). **Dry-run
by default**; pass `--apply` to delete. Best-effort/idempotent — absent resources are
skipped — and names derive deterministically from `userN`, so nothing else is touched.

```bash
admin/reset-student.sh user12              # preview what would be deleted
admin/reset-student.sh user12 --apply      # clean slate (EB teardown ~3 min)
bash ~/environment/aws-adv-dev/bootstrap.sh 6a   # then fast-forward that student to Lab 6a
```

The only hard dependency neither script provisions is **Lab 1a** itself (Cloud9 env +
`LabRole` attached + AMTC off + course repo cloned) — that's the one-time student setup.

## Repository Layout

```
aws_adv_dev/
├── README.md                          ← this file
├── AWS Advanced Developing on AWS.docx ← source outline
├── admin/                             ← instructor account + per-student ops
│   ├── setup-account.sh               ← one-time account setup (LabRole + region lock + EB roles)
│   ├── reset-student.sh               ← wipe ONE student's resources clean
│   ├── restrict-region-us-east-1.json
│   └── README.md
├── presentations/                     ← 15 teaching decks (Reveal.js)
│   ├── 01-course-overview.html
│   └── … 14 more …
├── labs/                              ← 15 hands-on lab guides (Markdown)
│   ├── lab1a-signin-orientation.md
│   └── … 14 more …
└── labs/files/                        ← source files students clone in Lab 1a
    ├── bootstrap.sh                    ← fast-forward a student into any lab (see "Resetting & Catching Up Students")
    ├── lab1/  (smoke_test.py)
    ├── lab2/  (base-stack.yaml, monolith/ Flask app + EB config)
    ├── lab3/  (load_config.py, get_secret.py, params.json)
    ├── lab4/  (template.yaml SAM, src/app.py Flights handler)
    ├── lab5/  (create_table.py, items.json, bulk_load.py, queries.py,
    │           booking-saga.asl.json, handlers.py, template.yaml)
    ├── lab6/  (publish_booking.py, worker.py, put_event.py, event-pattern.json)
    └── lab7/  (xray_handler.py, requirements.txt)
```

## Course-Files Distribution

Course materials live in the public GitHub repo
[**jwkidd3/aws_adv_dev**](https://github.com/jwkidd3/aws_adv_dev). Lab 1a has
students clone it and copy the supporting files into their workspace:

```
cd ~/environment
git clone https://github.com/jwkidd3/aws_adv_dev
cp -r aws_adv_dev/labs/files ./aws-adv-dev
```

From then on, every lab opens files already on disk under
`~/environment/aws-adv-dev/`. No copy-paste of large blocks into a terminal.

## Prerequisites Students Should Bring

- A laptop with a modern browser (Chrome, Firefox, Safari, or Edge)
- Reliable internet connection
- That's it — Cloud9 provides the IDE, AWS CLI, Python + `boto3`, `git`, `jq`, Docker, and SAM CLI
