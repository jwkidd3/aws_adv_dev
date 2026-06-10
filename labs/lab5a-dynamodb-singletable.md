# 🧪 Lab 5a — Polyglot Persistence: DynamoDB Single-Table Design

*Hands-On Lab · 50 min · SDK + CLI · Day 2 — Polyglot Persistence*

---

## Objectives (3 min)

- Design and create a single DynamoDB table (`CloudAir-$USER_ID`) with overloaded PK/SK keys and a GSI
- Understand the single-table pattern: multiple entity types co-residing in one table
- Bulk-load Flights, Bookings, and Customer items from a JSON file
- Execute three distinct access-pattern queries using the table key and GSI
- Contrast single-table design trade-offs against a normalized multi-table schema

---

## Prerequisites (3 min)

- Lab 4b complete — `~/.aws-adv-dev.env` exists and `$USER_ID` / `$AWS_REGION` are set
- Cloud9 terminal open; repo present at `~/environment/aws-adv-dev`

```bash
source ~/.aws-adv-dev.env
echo "USER_ID=$USER_ID  REGION=$AWS_REGION"
```

> **Starting fresh?** `bash ~/environment/aws-adv-dev/bootstrap.sh 5a` sets `$USER_ID`, `$ACCT`, and `$AWS_REGION` in `~/.aws-adv-dev.env` and verifies the repo is present.

---

## Background — Single-Table Design (5 min)

> Read this section before touching the terminal. Understanding the key-overloading model up front prevents confusion during the queries.

In a relational database, Flight, Booking, and Customer records live in separate tables joined by foreign keys. DynamoDB's strength is **single-digit millisecond latency at any scale** — but that requires all items accessed together to share the same partition. Single-table design achieves this by:

| Concept | Relational equivalent | DynamoDB single-table equivalent |
|---|---|---|
| Entity type | Table name | `type` attribute + PK/SK prefix (e.g. `FLIGHT#`, `BOOKING#`) |
| Row identity | Primary key | `PK` + `SK` compound key |
| Foreign key lookup | JOIN | GSI — project the foreign key as `GSI1PK` |
| Secondary index | CREATE INDEX | Pre-provisioned GSI at table-creation time |

**Cloud Air access patterns for this lab:**

| # | Description | Key used |
|---|---|---|
| AP-1 | Get a flight by flight ID + date | Table PK `FLIGHT#<id>` + SK `DATE#<date>` |
| AP-2 | List all bookings for a customer | GSI1 PK `CUSTOMER#<id>` + SK begins_with `BOOKING#` |
| AP-3 | Customer bookings within a date range | GSI1 PK `CUSTOMER#<id>` + SK BETWEEN `BOOKING#<start>` and `BOOKING#<end>` |

> Design the access patterns **before** creating the table — you cannot add a GSI after the fact without downtime, and changing the primary key requires creating a new table.

---

## Step 1 — Review the Item Model (5 min)

> Open `~/environment/aws-adv-dev/lab5/items.json` in the Cloud9 editor.

Observe how three entity types share the same table through key overloading:

**Flight item** — identified by flight ID and date:
```json
{
  "PK":     "FLIGHT#AA101",
  "SK":     "DATE#2024-09-15",
  "GSI1PK": "ROUTE#JFK#LAX",
  "GSI1SK": "DATE#2024-09-15#AA101",
  "type":   "Flight",
  "origin": "JFK",
  "destination": "LAX"
}
```

**Customer item** — `SK = "PROFILE"` collapses all profile fields into one item per customer:
```json
{
  "PK":     "CUSTOMER#CUST001",
  "SK":     "PROFILE",
  "GSI1PK": "EMAIL#alice@example.com",
  "GSI1SK": "CUSTOMER#CUST001",
  "type":   "Customer"
}
```

**Booking item** — the GSI keys point back to the customer, enabling AP-2 and AP-3:
```json
{
  "PK":     "BOOKING#BK10001",
  "SK":     "BOOKING#BK10001",
  "GSI1PK": "CUSTOMER#CUST001",
  "GSI1SK": "BOOKING#2024-09-15#BK10001",
  "type":   "Booking"
}
```

Key observations:
- `GSI1PK` / `GSI1SK` are **sparse** — only items that need to appear in the GSI carry these attributes
- The `type` attribute is a discriminator for application-level filtering; it is not used by DynamoDB
- Sort-key prefixes (`DATE#`, `BOOKING#`) enable `begins_with` and `BETWEEN` range queries

---

## Step 2 — Create the Table (10 min)

> Open `~/environment/aws-adv-dev/lab5/create_table.py` in the Cloud9 editor and review the `AttributeDefinitions` and `GlobalSecondaryIndexes` blocks before running.

```bash
source ~/.aws-adv-dev.env
cd ~/environment/aws-adv-dev/lab5
python3 create_table.py
```

Expected output:
```
Creating table: CloudAir-user1 in us-east-1 …
Waiting for ACTIVE status … done.  status=ACTIVE  GSIs=1
Table ready: CloudAir-user1
```

**Verify in the Console:**

1. Open **DynamoDB → Tables → CloudAir-$USER_ID**
2. **Overview** tab: confirm `BillingMode = PAY_PER_REQUEST`
3. **Indexes** tab: confirm `GSI1` on `GSI1PK` + `GSI1SK`, projection `ALL`

**Alternatively, create with the CLI** (skip if you used the script):

```bash
source ~/.aws-adv-dev.env
TABLE="CloudAir-$USER_ID"

aws dynamodb create-table \
  --table-name $TABLE \
  --billing-mode PAY_PER_REQUEST \
  --attribute-definitions \
      AttributeName=PK,AttributeType=S \
      AttributeName=SK,AttributeType=S \
      AttributeName=GSI1PK,AttributeType=S \
      AttributeName=GSI1SK,AttributeType=S \
  --key-schema \
      AttributeName=PK,KeyType=HASH \
      AttributeName=SK,KeyType=RANGE \
  --global-secondary-indexes \
      '[{"IndexName":"GSI1","KeySchema":[{"AttributeName":"GSI1PK","KeyType":"HASH"},{"AttributeName":"GSI1SK","KeyType":"RANGE"}],"Projection":{"ProjectionType":"ALL"}}]' \
  --region $AWS_REGION

aws dynamodb wait table-exists --table-name $TABLE --region $AWS_REGION
echo "Table active: $TABLE"
```

> Note: `AttributeDefinitions` only lists attributes that appear in a key (table or GSI). Attributes like `origin`, `email`, or `fareClass` are **not** declared here — DynamoDB is schema-less for non-key attributes.

---

## Step 3 — Bulk Load the Items (7 min)

> Open `~/environment/aws-adv-dev/lab5/bulk_load.py` in the Cloud9 editor.

The script uses `batch_writer()` which handles DynamoDB's 25-item-per-call limit and automatically retries `UnprocessedItems`:

```bash
cd ~/environment/aws-adv-dev/lab5
python3 bulk_load.py
# Done. 9 items written to CloudAir-user1.
```

**Confirm the load in the Console:**

1. **DynamoDB → Tables → CloudAir-$USER_ID → Explore items**
2. Change the scan limit to 25 — you should see all 9 items across three `type` values
3. Expand any Booking item and verify `GSI1PK` is populated

**Or via CLI:**

```bash
aws dynamodb scan \
  --table-name CloudAir-$USER_ID \
  --select COUNT \
  --region $AWS_REGION \
  --output text
# 9
```

---

## Step 4 — Run the Access-Pattern Queries (15 min)

> Open `~/environment/aws-adv-dev/lab5/queries.py` in the Cloud9 editor and read through each function before running.

```bash
python3 queries.py
```

Review the output for all three access patterns:

**AP-1 — GetItem on the table primary key:**
```
--- AP-1: Get flight AA101 on 2024-09-15 ---
  Route       : JFK -> LAX
  Departure   : 08:00  Arrival: 11:30
  Seats avail : 42 / 180
  Base price  : $299.00
```

> `get_item` is a direct key lookup — O(1), always consistent, costs 0.5 RCU for a strongly consistent read under 4 KB.

**AP-2 — GSI query (all bookings for a customer):**
```
--- AP-2: All bookings for customer CUST001 ---
  2 booking(s) found:
    BK10001  flight=AA101  date=2024-09-15  status=CONFIRMED  seat=14A
    BK10002  flight=DL305  date=2024-09-16  status=CANCELLED  seat=22C
```

> The query hits `GSI1` — it never touches the base table. GSI reads are eventually consistent by default; pass `ConsistentRead=True` only on the base table.

**AP-3 — GSI range query (bookings within a date window):**
```
--- AP-3: Bookings for CUST001 between 2024-09-15 and 2024-09-15 ---
  1 booking(s) in range:
    BK10001  date=2024-09-15  status=CONFIRMED
```

> The `GSI1SK` format `BOOKING#<date>#<bookingId>` enables lexicographic range queries. The trailing `~` in the upper bound sorts after all digits and letters — a common trick for inclusive date-prefix BETWEEN queries.

**Run an individual query from the CLI** (optional exploration):

```bash
aws dynamodb query \
  --table-name CloudAir-$USER_ID \
  --index-name GSI1 \
  --key-condition-expression "GSI1PK = :cpk AND begins_with(GSI1SK, :prefix)" \
  --expression-attribute-values '{":cpk":{"S":"CUSTOMER#CUST002"},":prefix":{"S":"BOOKING#"}}' \
  --region $AWS_REGION \
  --output json | python3 -c "import sys,json; [print(i['bookingId']['S'], i['status']['S']) for i in json.load(sys.stdin)['Items']]"
```

---

## Step 5 — Console Query Exploration (5 min)

1. **DynamoDB → Tables → CloudAir-$USER_ID → Explore items**
2. Switch from **Scan** to **Query**
3. Set partition key: `FLIGHT#AA101`, sort key: `begins_with DATE#`
4. Run and confirm the flight item is returned
5. Change the index dropdown to **GSI1** — set `GSI1PK = CUSTOMER#CUST001`
6. Run and confirm two booking items appear
7. Note the **Capacity** column — compare the GSI query cost vs a Scan of the same table

---

## Discussion

**Why single-table over multiple tables?**

In DynamoDB, a cross-table join does not exist — you make two separate requests and join in application code. If the booking workflow needs the customer record *and* the flight record *and* the booking record, that is three round trips. A single-table design with well-chosen keys can retrieve all three with one `Query` + a `BatchGetItem` of at most two additional items, reducing both latency and cost.

**When does single-table design *not* make sense?**

- Teams unfamiliar with DynamoDB often find the key-overloading model harder to maintain than a normalized schema in Aurora or RDS. Use single-table only when you have **well-defined, stable access patterns**.
- If your access patterns keep changing, the cost of re-loading data into a new key scheme is significant. Prefer Amazon RDS or Aurora for exploratory, ad-hoc query workloads.
- Monitoring is harder: `cloudwatch:ConsumedReadCapacityUnits` is per-table; you cannot easily attribute cost to a specific entity type without application-level metrics.

**GSI vs multiple tables:**

A GSI is effectively a separate, automatically-maintained projection of your table. It adds write cost (each item write fans out to every GSI that covers that item) but eliminates the need for a second `GetItem` call when querying by an alternate key.

---

## Success Criteria (2 min)

- ✅ Table `CloudAir-$USER_ID` is `ACTIVE` with GSI `GSI1` on `GSI1PK` + `GSI1SK`
- ✅ 9 items loaded (3 Flights, 2 Customers, 4 Bookings)
- ✅ AP-1 returns the correct flight details for `AA101` on `2024-09-15`
- ✅ AP-2 returns 2 bookings for `CUST001` and 2 bookings for `CUST002`
- ✅ AP-3 returns only the `2024-09-15` booking for `CUST001`
- ✅ You can explain why `GSI1SK` uses the `BOOKING#<date>#<id>` prefix format
