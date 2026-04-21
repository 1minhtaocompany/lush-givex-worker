# Lush Givex worker — Make targets
#
# The E2E suite (P2-4) lives under tests/integration/e2e/ and is executed
# separately from the unit/integration suites because the acceptance criterion
# requires: "CI job mới: make test-e2e (tách khỏi unit test)".

.PHONY: test test-unit test-integration test-e2e test-all

# Default target — unit suite (fast path used by most contributors).
test: test-unit

test-unit:
	python -m unittest discover tests

# L3 harness + L4 smoke (existing integration suite).
test-integration:
	python -m unittest discover tests/integration -v

# P2-4 — 14 E2E tests (T-01 … T-14).  Kept separate from the unit suite
# because they exercise the full FSM + orchestrator loop and stub the CDP
# driver in ways that mutate shared idempotency state.
test-e2e:
	python -m unittest discover -s tests/integration/e2e -t . -v

# Convenience: run everything locally.
test-all: test-unit test-integration test-e2e
