#!/usr/bin/env python3
import os
import re
import subprocess
import sys

MAX_LINES_CHANGED = 200

REF_PATTERN = re.compile(r"^[A-Za-z0-9._/~-]+$")
DIFF_RANGE_PATTERN = re.compile(r"^[A-Za-z0-9._/~-]+\.{3}[A-Za-z0-9._/~-]+$")


def sanitize_ref(ref):
    return ref.replace("\n", " ").replace("\r", " ").strip()


def validate_ref_format(ref):
    if not ref:
        return None, "invalid git ref"
    if ref.startswith("-"):
        return None, f"invalid git ref '{sanitize_ref(ref)}'"
    if not REF_PATTERN.fullmatch(ref):
        return None, f"invalid git ref '{sanitize_ref(ref)}'"
    if ".." in ref or "/." in ref or "./" in ref or ref.startswith("/") or ref.endswith("/"):
        return None, f"invalid git ref '{sanitize_ref(ref)}'"
    return ref, ""


def verify_ref(ref):
    safe_ref, safe_error = validate_ref_format(ref)
    if safe_ref is None:
        return None, safe_error
    result = subprocess.run(
        ["git", "rev-parse", "--verify", safe_ref],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip()
        if details:
            return None, f"git rev-parse --verify {safe_ref} failed: {details}"
        return None, f"git rev-parse --verify {safe_ref} failed"
    return result.stdout.strip(), ""


def resolve_base_ref(base_ref):
    base_sha, base_error = verify_ref(base_ref)
    if base_sha is not None:
        return base_ref, ""
    origin_ref = f"origin/{base_ref}"
    origin_sha, origin_error = verify_ref(origin_ref)
    if origin_sha is not None:
        return origin_ref, ""
    details = []
    if base_error:
        details.append(base_error)
    if origin_error:
        details.append(origin_error)
    return None, "\n".join(details)


def resolve_diff_range():
    base_ref_env = os.getenv("GITHUB_BASE_REF") or ""
    head_sha_env = os.getenv("GITHUB_HEAD_SHA") or os.getenv("GITHUB_SHA") or ""
    is_ci = os.getenv("GITHUB_ACTIONS") == "true"

    base_ref = base_ref_env.strip()
    head_sha = head_sha_env.strip()

    if base_ref and head_sha:
        base, base_error = resolve_base_ref(base_ref)
        if base is None:
            print(
                "check_pr_scope: unable to resolve base ref "
                f"'{sanitize_ref(base_ref)}'",
                file=sys.stderr,
            )
            if base_error:
                print(base_error, file=sys.stderr)
            sys.exit(1)

        head_sha_resolved, head_sha_error = verify_ref(head_sha)
        if head_sha_resolved is None:
            print(
                "check_pr_scope: head SHA "
                f"'{sanitize_ref(head_sha)}' could not be resolved",
                file=sys.stderr,
            )
            if head_sha_error:
                print(head_sha_error, file=sys.stderr)
            sys.exit(1)

        return f"{base}...{head_sha}"

    if is_ci:
        print(
            "check_pr_scope: missing GITHUB_BASE_REF or "
            "GITHUB_HEAD_SHA/GITHUB_SHA; cannot determine diff range in CI",
            file=sys.stderr,
        )
        sys.exit(1)

    for candidate in ("origin/develop", "develop"):
        candidate_sha, _ = verify_ref(candidate)
        if candidate_sha is not None:
            return f"{candidate}...HEAD"

    head_parent_sha, _ = verify_ref("HEAD~1")
    if head_parent_sha is not None:
        return "HEAD~1...HEAD"

    print(
        "check_pr_scope: unable to determine diff range; set "
        "GITHUB_BASE_REF and GITHUB_HEAD_SHA/GITHUB_SHA",
        file=sys.stderr,
    )
    sys.exit(1)


def validate_diff_range(diff_range):
    return bool(DIFF_RANGE_PATTERN.fullmatch(diff_range))


def normalize_path(path):
    normalized = path.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def get_changed_files(diff_range):
    if not validate_diff_range(diff_range):
        print(f"check_pr_scope: invalid diff range '{diff_range}'", file=sys.stderr)
        sys.exit(1)
    result = subprocess.run(
        ["git", "diff", "--name-only", diff_range],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        print("check_pr_scope: git diff --name-only failed", file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def is_tests_path(path):
    normalized = normalize_path(path)
    return normalized.startswith("tests/") or "/tests/" in normalized


def parse_numstat_value(value):
    """Return non-negative line counts; treat non-numeric or negative values as 0."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed >= 0 else 0


def get_total_changed_lines(diff_range):
    if not validate_diff_range(diff_range):
        print(f"check_pr_scope: invalid diff range '{diff_range}'", file=sys.stderr)
        sys.exit(1)
    result = subprocess.run(
        ["git", "diff", "--numstat", diff_range],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        print("check_pr_scope: git diff --numstat failed", file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        sys.exit(1)

    total = 0
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", maxsplit=2)
        if len(parts) < 3:
            continue
        added = parse_numstat_value(parts[0])
        deleted = parse_numstat_value(parts[1])
        path = parts[2]
        if is_tests_path(path):
            continue
        total += added + deleted
    return total


def module_from_path(path):
    normalized = normalize_path(path)
    if not normalized.startswith("modules/"):
        return None
    parts = normalized.split("/")
    if len(parts) < 2 or not parts[1]:
        return None
    return parts[1]


def main():
    diff_range = resolve_diff_range()
    changed_files = get_changed_files(diff_range)
    total_lines = get_total_changed_lines(diff_range)

    modules_changed = set()
    for path in changed_files:
        module_name = module_from_path(path)
        if module_name:
            modules_changed.add(module_name)

    errors = []
    if total_lines > MAX_LINES_CHANGED:
        errors.append(
            f"FAIL: total lines changed ({total_lines}) exceeds {MAX_LINES_CHANGED}"
        )
    if len(modules_changed) > 1:
        modules_list = ", ".join(sorted(modules_changed))
        errors.append(
            "FAIL: changes touch multiple modules under modules/: "
            f"{modules_list}"
        )

    if errors:
        print("check_pr_scope: FAIL")
        for message in errors:
            print(message)
        return 1

    print("check_pr_scope: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())