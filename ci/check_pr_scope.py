#!/usr/bin/env python3
"""Check that a PR stays within scope: ≤ 200 changed lines (excluding
ci/ and tests/) and touches at most one module under modules/.

Architect Directive (AD-6 amendment):
  ci/ and tests/ are excluded from the line count because CI scripts are
  infrastructure code and tests should never be penalized against a size
  limit.  This avoids the self-blocking paradox where the enforcement
  script itself would exceed the limit it enforces.

Exception Framework (CHANGE_CLASS):
  Set the CHANGE_CLASS environment variable to opt-in to one of these
  bypass modes:

    emergency_override — bypass ALL checks (module limit + line limit).
                         GOVERNANCE REQUIRED: PR title must start with
                         '[emergency]' OR the PR label 'emergency' must
                         be present (read from PR_TITLE / PR_LABELS env
                         vars).  Missing governance causes a hard FAIL.

    spec_sync          — bypass module limit only; line limit is still
                         enforced.  Use for cross-module spec updates.

    infra_change       — bypass line limit only; module limit is still
                         enforced.  Use for large infrastructure changes
                         that are confined to a single module.

  ALLOW_MULTI_MODULE (DEPRECATED):
    Setting ALLOW_MULTI_MODULE=true is treated as an alias for
    CHANGE_CLASS=spec_sync.  A deprecation warning is printed to stderr.
    This variable will be removed in a future release; migrate to
    CHANGE_CLASS=spec_sync.
"""

import os
import re
import subprocess
import sys

# ── configuration ──────────────────────────────────────────────────
MAX_CHANGED_LINES = 200
EXCLUDED_PREFIXES = ("tests/", "ci/")

# ── git helpers ────────────────────────────────────────────────────

REF_PATTERN = re.compile(r"^[A-Za-z0-9._/~-]+$")


def _sanitize_ref(ref: str) -> str:
    return ref.replace("\n", " ").replace("\r", " ").strip()


def _validate_ref(ref: str) -> tuple[str | None, str]:
    if not ref or ref.startswith("-"):
        return None, f"invalid git ref '{_sanitize_ref(ref)}'"
    if not REF_PATTERN.fullmatch(ref):
        return None, f"invalid git ref '{_sanitize_ref(ref)}'"
    if ".." in ref or "/." in ref or "./" in ref:
        return None, f"invalid git ref '{_sanitize_ref(ref)}'"
    if ref.startswith("/") or ref.endswith("/"):
        return None, f"invalid git ref '{_sanitize_ref(ref)}'"
    return ref, ""


def _verify_ref(ref: str) -> tuple[str | None, str]:
    safe, err = _validate_ref(ref)
    if safe is None:
        return None, err
    result = subprocess.run(
        ["git", "rev-parse", "--verify", safe],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        detail = (result.stderr.strip() or result.stdout.strip())
        msg = f"git rev-parse --verify {safe} failed"
        return None, f"{msg}: {detail}" if detail else msg
    return result.stdout.strip(), ""


def resolve_diff_range() -> str:
    base_raw = (os.getenv("GITHUB_BASE_REF") or "").strip()
    head_raw = (os.getenv("GITHUB_HEAD_SHA")
                or os.getenv("GITHUB_SHA") or "").strip()
    is_ci = os.getenv("GITHUB_ACTIONS") == "true"

    if base_raw and head_raw:
        # resolve base
        base_sha, _ = _verify_ref(base_raw)
        if base_sha is not None:
            base = base_raw
        else:
            origin = f"origin/{base_raw}"
            origin_sha, _ = _verify_ref(origin)
            if origin_sha is not None:
                base = origin
            else:
                print(f"check_pr_scope: cannot resolve base ref "
                      f"'{_sanitize_ref(base_raw)}'", file=sys.stderr)
                sys.exit(1)
        # resolve head
        head_sha, _ = _verify_ref(head_raw)
        if head_sha is None:
            print(f"check_pr_scope: cannot resolve head SHA "
                  f"'{_sanitize_ref(head_raw)}'", file=sys.stderr)
            sys.exit(1)
        return f"{base}...{head_raw}"

    if is_ci:
        print("check_pr_scope: missing GITHUB_BASE_REF or "
              "GITHUB_HEAD_SHA/GITHUB_SHA", file=sys.stderr)
        sys.exit(1)

    # local fallback
    for candidate in ("origin/main", "main", "origin/develop", "develop"):
        sha, _ = _verify_ref(candidate)
        if sha is not None:
            return f"{candidate}...HEAD"

    parent, _ = _verify_ref("HEAD~1")
    if parent is not None:
        return "HEAD~1...HEAD"

    print("check_pr_scope: unable to determine diff range",
          file=sys.stderr)
    sys.exit(1)


# ── diff analysis ──────────────────────────────────────────────────

def _normalize(path: str) -> str:
    p = path.replace("\\", "/")
    return p[2:] if p.startswith("./") else p


def _is_excluded(path: str) -> bool:
    norm = _normalize(path)
    return any(norm.startswith(prefix) for prefix in EXCLUDED_PREFIXES)


def get_numstat(diff_range: str) -> list[tuple[int, int, str]]:
    """Return list of (added, deleted, filepath) from git diff --numstat."""
    result = subprocess.run(
        ["git", "diff", "--numstat", diff_range],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        print("check_pr_scope: git diff --numstat failed", file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        sys.exit(1)

    entries: list[tuple[int, int, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added_s, deleted_s, filepath = parts[0], parts[1], parts[2]
        if added_s == "-" or deleted_s == "-":
            # binary file
            continue
        entries.append((int(added_s), int(deleted_s), filepath))
    return entries


def module_from_path(path: str) -> str | None:
    norm = _normalize(path)
    if not norm.startswith("modules/"):
        return None
    parts = norm.split("/")
    return parts[1] if len(parts) >= 2 and parts[1] else None


# ── main ───────────────────────────────────────────────────────────

def check(diff_range: str) -> int:
    """Run scope checks.  Returns 0 on PASS, 1 on FAIL."""
    entries = get_numstat(diff_range)
    total_lines = 0
    modules_touched: set[str] = set()
    excluded_lines = 0

    for added, deleted, filepath in entries:
        changed = added + deleted
        mod = module_from_path(filepath)
        if mod:
            modules_touched.add(mod)
        if _is_excluded(filepath):
            excluded_lines += changed
        else:
            total_lines += changed

    errors: list[str] = []
    if total_lines > MAX_CHANGED_LINES:
        errors.append(
            f"total lines changed ({total_lines}) exceeds "
            f"{MAX_CHANGED_LINES} (excluding {', '.join(EXCLUDED_PREFIXES)})"
        )
    if len(modules_touched) > 1:
        errors.append(
            f"PR touches {len(modules_touched)} modules "
            f"({', '.join(sorted(modules_touched))}); max 1 allowed"
        )

    if errors:
        print("check_pr_scope: FAIL")
        for err in errors:
            print(f"  {err}")
        if excluded_lines:
            print(f"  (excluded {excluded_lines} lines in "
                  f"{', '.join(EXCLUDED_PREFIXES)})")
        return 1

    print(f"check_pr_scope: PASS ({total_lines} lines changed"
          + (f", {excluded_lines} excluded" if excluded_lines else "")
          + ")")
    return 0


def _resolve_change_class() -> str:
    """Return the effective CHANGE_CLASS value (lowercase, stripped).

    ALLOW_MULTI_MODULE=true is accepted as a deprecated alias for
    'spec_sync'; a deprecation warning is emitted in that case.
    """
    change_class = os.environ.get("CHANGE_CLASS", "").strip().lower()
    allow_multi = os.environ.get("ALLOW_MULTI_MODULE", "").strip().lower()

    if allow_multi == "true":
        print(
            "DEPRECATED: ALLOW_MULTI_MODULE is deprecated and will be "
            "removed in a future release.  Use CHANGE_CLASS=spec_sync "
            "instead.",
            file=sys.stderr,
        )
        if not change_class:
            change_class = "spec_sync"

    return change_class


def _enforce_emergency_governance() -> bool:
    """Return True if emergency governance requirements are satisfied.

    Governance passes when:
      - PR_TITLE env var starts with '[emergency]' (case-insensitive), OR
      - PR_LABELS env var contains the word 'emergency' (case-insensitive).

    Prints an error message and returns False if governance fails.
    """
    pr_title = os.environ.get("PR_TITLE", "").strip()
    pr_labels = os.environ.get("PR_LABELS", "").strip().lower()

    title_ok = pr_title.lower().startswith("[emergency]")
    labels_ok = "emergency" in [lbl.strip() for lbl in pr_labels.split(",") if lbl.strip()]

    if title_ok or labels_ok:
        return True

    print(
        "check_pr_scope: FAIL\n"
        "  CHANGE_CLASS=emergency_override requires governance:\n"
        "  PR title must start with '[emergency]' OR label "
        "'emergency' must be set (via PR_LABELS env var).",
        file=sys.stderr,
    )
    return False


def main() -> int:
    change_class = _resolve_change_class()

    if change_class == "emergency_override":
        if not _enforce_emergency_governance():
            return 1
        # bypass all checks
        print("check_pr_scope: PASS (emergency_override — all checks bypassed)")
        return 0

    diff_range = resolve_diff_range()

    if change_class == "spec_sync":
        # bypass module limit; still enforce line limit
        entries = get_numstat(diff_range)
        total_lines = 0
        excluded_lines = 0
        for added, deleted, filepath in entries:
            changed = added + deleted
            if _is_excluded(filepath):
                excluded_lines += changed
            else:
                total_lines += changed
        if total_lines > MAX_CHANGED_LINES:
            print("check_pr_scope: FAIL")
            print(
                f"  total lines changed ({total_lines}) exceeds "
                f"{MAX_CHANGED_LINES} (excluding "
                f"{', '.join(EXCLUDED_PREFIXES)})"
            )
            return 1
        print(
            f"check_pr_scope: PASS ({total_lines} lines changed"
            + (f", {excluded_lines} excluded" if excluded_lines else "")
            + ", multi-module allowed via spec_sync)"
        )
        return 0

    if change_class == "infra_change":
        # bypass line limit; still enforce single-module rule
        entries = get_numstat(diff_range)
        modules_touched: set[str] = set()
        for added, deleted, filepath in entries:
            mod = module_from_path(filepath)
            if mod:
                modules_touched.add(mod)
        if len(modules_touched) > 1:
            print("check_pr_scope: FAIL")
            print(
                f"  PR touches {len(modules_touched)} modules "
                f"({', '.join(sorted(modules_touched))}); max 1 allowed"
            )
            return 1
        print("check_pr_scope: PASS (line limit bypassed via infra_change)")
        return 0

    if change_class and change_class not in ("emergency_override", "spec_sync", "infra_change"):
        print(
            f"check_pr_scope: unknown CHANGE_CLASS value '{change_class}'; "
            "valid values: emergency_override, spec_sync, infra_change",
            file=sys.stderr,
        )
        return 1

    return check(diff_range)


if __name__ == "__main__":
    sys.exit(main())
