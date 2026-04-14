# Scripts

## `seed_billing_pool.py`

Seed billing profiles from a CSV/TSV file into batched text files.

### Usage

```bash
python scripts/seed_billing_pool.py --input profiles.csv --output billing_pool/
```

### Input format

`first_name,last_name,address,city,state,zip[,phone][,email]`

- At least 6 fields are required.
- Rows with fewer than 6 fields are skipped.
- CSV and TSV inputs are supported.

### Output format

- Output directory defaults to `billing_pool/`.
- Every 1000 accepted profiles are written to one `.txt` file.
- Output line format:

`first|last|address|city|state|zip|phone|email`

---

## `download_maxmind.py`

Download and install `GeoLite2-City.mmdb` from the MaxMind API.

### Requirements

- Environment variable `MAXMIND_LICENSE_KEY` must be set.

### Usage

```bash
MAXMIND_LICENSE_KEY=your_key python scripts/download_maxmind.py
```

### Behavior

- Downloads archive from:
  `https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City&license_key={key}&suffix=tar.gz`
- Downloads checksum from same URL with `suffix=tar.gz.sha256`
- Verifies SHA256 checksum
- Extracts `.mmdb` from archive
- Writes file to `data/GeoLite2-City.mmdb` (creates `data/` if needed)
