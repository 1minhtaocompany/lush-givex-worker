# Spec Versioning Rules

All spec interface files (`spec/interface.md`, `spec/core/interface.md`,
`spec/integration/interface.md`) carry a `spec-version: MAJOR.MINOR` header
in their YAML front-matter block.

## Version Semantics

| Change type | Version bump | CHANGE_CLASS required |
|-------------|--------------|----------------------|
| Breaking change (remove/rename function or parameter) | MAJOR | `spec_sync` |
| Additive change (new function, new optional parameter) | MINOR | normal PR |
| Documentation / formatting only | none | normal PR |

## Rules

1. **MAJOR** bump (`X.y → X+1.0`) signals a breaking change.  A `spec_sync`
   (or `emergency_override`) `CHANGE_CLASS` is required in CI to acknowledge
   the breaking nature of the change.

2. **MINOR** bump (`x.Y → x.Y+1`) signals an additive, backward-compatible
   change.  No special `CHANGE_CLASS` is needed.

3. All three spec files (aggregated + both segmented) **must** carry the same
   `spec-version` value at all times.  `check_signature.py` warns via stderr
   if versions diverge.

4. The aggregated file (`spec/interface.md`) **must not diverge** from the
   union of the segmented files (`spec/core/interface.md` +
   `spec/integration/interface.md`).  `check_signature.py` warns via stderr
   if a divergence is detected.

## Current version

`1.0` — initial segmentation release.
