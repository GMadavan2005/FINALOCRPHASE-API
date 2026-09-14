# TMS to PostgreSQL Sync

This connects your TMS API to your Freight_Audit_System database.

## Setup (one-time)

1. Install Python packages:
   ```
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env`:
   ```
   copy .env.example .env
   ```

3. Open `.env` and fill in your real values:
   - Database password
   - TMS API base URL
   - TMS API key
   - Each endpoint path (confirm these in Postman first)

## Before running: confirm endpoints in Postman

For each endpoint, test it in Postman first and confirm the JSON
response matches the field names expected in `sync_tables.py`.
If your TMS uses different field names, update the corresponding
function in `sync_tables.py` to match.

## Running the sync

Run everything, in the correct order:
```
python main_sync.py
```

Or run a single table's sync (useful for testing one at a time):
```python
from sync_tables import sync_carriers
sync_carriers()
```

## Files

- `.env` - your real credentials (never share this file)
- `.env.example` - template showing what's needed
- `db.py` - handles the Postgres connection
- `api_client.py` - handles calling the TMS API
- `sync_tables.py` - one function per table, with correct field mapping
- `main_sync.py` - runs everything in the right order

## Automating this (run it on a schedule)

Once this works correctly when run manually, set it up in
Windows Task Scheduler to run `python main_sync.py` automatically
(e.g. nightly).
