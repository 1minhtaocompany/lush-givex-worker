# Spec Versioning Rules

spec-version: 1.0

## Overview

All spec interface files carry a `spec-version: MAJOR.MINOR` header on the
first non-blank line.  The version follows Semantic Versioning semantics
adapted for interface contracts.

## Version Format

```
spec-version: MAJOR.MINOR
```

- **MAJOR** – incremented for breaking changes (renamed/removed/reordered
  parameters, removed functions, changed return types).
- **MINOR** – incremented for additive, backward-compatible changes (new
  optional parameters, new functions).

## Rules

### MAJOR bump
- Requires `CHANGE_CLASS=spec_sync` in the PR.
- The PR author must update **both** the segmented file
  (`spec/core/interface.md` or `spec/integration/interface.md`) **and** the
  aggregated fallback (`spec/interface.md`) in the same PR.
- CI will warn if the aggregated file diverges from segmented files via
  `_check_aggregated_consistency()` in `ci/check_signature.py`.

### MINOR bump
- No special CI gate required.
- Still requires both segmented and aggregated files to be updated together
  to prevent divergence.

### Divergence policy
The aggregated file `spec/interface.md` **MUST NOT** diverge from the
segmented files.  `ci/check_signature.py` prints a non-fatal `WARNING` when
divergence is detected.  Treat any divergence warning as a blocking issue
before the next MAJOR release.

## Current Versions

| File                              | Version |
|-----------------------------------|---------|
| spec/core/interface.md            | 1.0     |
| spec/integration/interface.md     | 1.0     |
| spec/interface.md                 | 1.0     |
