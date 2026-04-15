# Scripts

## `seed_billing_pool.py`

Seed billing profiles from CSV/TSV into batched `.txt` files.

```bash
python scripts/seed_billing_pool.py --input profiles.csv --output billing_pool/
```

Input: `first_name,last_name,address,city,state,zip[,phone][,email]` (min 6 fields).
Output: `first|last|address|city|state|zip|phone|email` — 1000 profiles per file.

## `download_maxmind.py`

Download `GeoLite2-City.mmdb` from MaxMind. Requires env var `MAXMIND_LICENSE_KEY`.

```bash
MAXMIND_LICENSE_KEY=your_key python scripts/download_maxmind.py
```

Downloads, verifies SHA256, extracts `.mmdb`, and saves to `data/GeoLite2-City.mmdb`.
