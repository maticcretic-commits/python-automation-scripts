# python-automation-scripts

A **practice/demo toolkit** of reusable Python automation scripts — API syncing,
CSV cleanup, scheduled job running, and webhook receiving — built for learning.
It is modeled on the skills listed in a real Upwork posting for a
"Technical Automation Specialist (n8n, Python, AI)": Python automation scripts,
API work with auth and JSON, webhooks, error handling, testing, and clean
project structure.

> This is a learning project. It is **not** client work and does not represent
> paid experience. All endpoints, keys, and data here are placeholders.

## What's inside

| Script | What it does | Key patterns shown |
|---|---|---|
| `scripts/api_sync.py` | Paginates a REST API (API-key auth) into a local JSON store | retry + exponential backoff, structured JSON logging, `--dry-run` |
| `scripts/csv_transform.py` | Normalizes messy CSVs using rules from JSON config | column mapping, date parsing, bad-row quarantine |
| `scripts/job_runner.py` | Runs scheduled jobs from config, keeps going on failures | subprocess management, failure isolation, JSON result logs |
| `scripts/webhook_receiver.py` | Stdlib HTTP server that verifies HMAC-signed webhooks | HMAC signature check, JSONL event log |

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in your values
cp config.example.json config.json
```

Run the CSV demo (works with zero setup):

```bash
python3 scripts/csv_transform.py data/sample_messy.csv \
  --rules config.example.json \
  --out data/sample_clean.csv \
  --quarantine data/sample_quarantine.csv
```

Run the tests (all offline, no network needed):

```bash
python3 -m pytest tests/ -q
```

Other scripts need config first — see below.

## Script reference

### api_sync.py — REST API → local JSON store

```bash
export API_BASE_URL="https://api.example.com"
export API_KEY="your-api-key"
python3 scripts/api_sync.py --endpoint /v1/records --out data/records.json
python3 scripts/api_sync.py --dry-run   # fetch pages, print count, write nothing
```

- Sends `Authorization: Bearer <API_KEY>`, follows `{"items": [...], "next_page": N}`
  pagination, and writes atomically (`*.tmp` + rename) so a crash never leaves a
  half-written file.
- Retries HTTP 429/5xx and connection errors with exponential backoff
  (`--max-retries`, `--backoff`); 4xx and malformed payloads fail fast.

### csv_transform.py — messy CSV → clean CSV + quarantine

```bash
python3 scripts/csv_transform.py data/sample_messy.csv \
  --rules config.example.json \
  --out data/sample_clean.csv \
  --quarantine data/sample_quarantine.csv
```

Rules live in the `csv_transform` section of `config.example.json`:

```json
{
  "column_mapping": {"Customer ID": "id", "E-mail": "email"},
  "normalize_headers": true,
  "date_columns": ["signup_date"],
  "email_columns": ["email"],
  "required_columns": ["email"],
  "output_columns": ["id", "name", "email", "signup_date"]
}
```

Rows missing required values, failing the email sanity check, or with
unparseable dates are written to the quarantine CSV with a `quarantine_reason`
column instead of being silently dropped.

### job_runner.py — tiny scheduled-job runner

```bash
python3 scripts/job_runner.py --config config.example.json --once     # run every job once
python3 scripts/job_runner.py --config config.example.json --loop --cycles 2
```

Jobs are declared in the `jobs` section of the config. Each result
(name, ok, return code, duration, captured output) is logged as one JSON line.
A job that crashes or times out is recorded as failed and **never stops the
other jobs** — failure isolation is covered by tests.

### webhook_receiver.py — HMAC-verified webhook endpoint

```bash
export WEBHOOK_SECRET="a-long-random-string"
python3 scripts/webhook_receiver.py --port 8000 --log-file data/webhooks.jsonl
```

Verifies the `X-Signature: sha256=<hex>` header with `hmac.compare_digest`
before accepting anything, then appends each event as one JSON line.
Uses only the standard library.

Test it locally:

```bash
SECRET="a-long-random-string"
BODY='{"event":"demo"}'
SIG=$(python3 -c "import hmac,hashlib,os;print(hmac.new(os.environ['SECRET'].encode(),os.environ['BODY'].encode(),hashlib.sha256).hexdigest())" )
curl -X POST localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Signature: sha256=$SIG" \
  -d "$BODY"
```

## Configuration

- `.env.example` → copy to `.env`: `API_BASE_URL`, `API_KEY`, `WEBHOOK_SECRET`.
- `config.example.json` → copy to `config.json`: per-script settings and the job list.

## Project layout

```
python-automation-scripts/
├── scripts/            # the four automation scripts
├── tests/              # pytest suite (offline, mocked I/O)
├── data/               # sample input CSV (git-ignored outputs live here too)
├── config.example.json
├── requirements.txt
├── .env.example
└── README.md
```

## Learning roadmap

1. **Run everything locally** — CSV demo, pytest suite, the webhook server with
   the curl example above.
2. **Break things on purpose** — point `api_sync.py` at `https://httpbin.org/status/503`
   (needs network) to watch backoff; feed `csv_transform.py` a CSV with new
   date formats and extend `parse_date`.
3. **Connect to a real n8n instance** (the posting's core skill):
   - Point an n8n **Webhook node** at `webhook_receiver.py` and verify signatures
     from n8n's side with the shared secret.
   - Replace `api_sync.py`'s fetch loop with n8n **HTTP Request nodes** for
     comparison, keeping this script as the fallback for APIs n8n can't reach.
   - Trigger `csv_transform.py` and `job_runner.py` from n8n **Execute Command**
     nodes so n8n handles scheduling while Python does the heavy lifting.
4. **Harden for production** — swap the JSON store for SQLite/Postgres, add a
   `--state` file to `api_sync.py` for incremental syncs, containerize with Docker.
5. **Next skill from the posting** — rebuild `webhook_receiver.py` on
   Flask or FastAPI (bonus skill in the posting) and compare.

## ❤️ Support My Work

> If you find this project useful, please consider supporting my work with a Bitcoin donation:
>
> **₿ `BC1Q6Q75K8ZJXVW7W02LMDPRPY6XX6QK4LZZ2RMVAY`**

## ☕ Support my work
If this project was useful, you can support it with Bitcoin: `bc1q6q75k8zjxvw7w02lmdprpy6xx6qk4lzz2rmvay`
