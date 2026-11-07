"""Persistent phase reservations, race-safe caps, failures and true fresh inference."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from textbook_audit.assessment_budget import BudgetExceeded, CallLedger


def test_failures_crashes_and_restarts_do_not_restore_attempt_allowance(tmp_path) -> None:
    ledger = CallLedger(tmp_path / "ledger.db", "a" * 64)
    first = ledger.reserve("development-run", "development", "b" * 64)
    ledger.start(first)
    ledger.finish(first, {"raw_text": "invalid"}, error_code="invalid_output")
    ledger.reserve("development-run", "development", "c" * 64)
    restarted = CallLedger(ledger.path, "a" * 64)
    assert restarted.status()["reserved_or_attempted"] == 2
    assert restarted.status()["failed"] == 1
    assert restarted.status()["unfinished"] == 1
    with pytest.raises(RuntimeError):
        restarted.start(first)
    with pytest.raises(RuntimeError):
        restarted.finish(first, {"replacement": True})


def test_concurrent_development_requests_cannot_consume_final_and_rerun_reservations(tmp_path) -> None:
    ledger = CallLedger(tmp_path / "ledger.db", "a" * 64)
    def reserve(_number):
        try:
            return ledger.reserve("run", "development", "b" * 64)
        except BudgetExceeded:
            return None
    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(workers.map(reserve, range(70)))
    assert sum(result is not None for result in results) == 60
    assert ledger.status()["phase_remaining"]["final_evaluation"] == 180
    assert ledger.status()["phase_remaining"]["fresh_final_rerun"] == 180
    assert ledger.status()["phase_remaining"]["contingency"] == 80


def test_completed_identical_requests_reuse_only_within_the_same_run(tmp_path) -> None:
    ledger = CallLedger(tmp_path / "ledger.db", "a" * 64)
    attempt = ledger.reserve("final", "final_evaluation", "b" * 64)
    ledger.start(attempt)
    ledger.finish(attempt, {"raw_text": "original"})
    assert ledger.cached("final", "b" * 64)["result"]["raw_text"] == "original"
    assert ledger.cached("fresh-rerun", "b" * 64) is None
    assert ledger.status()["reserved_or_attempted"] == 1
    with pytest.raises(ValueError, match="cannot be reset"):
        CallLedger(ledger.path, "c" * 64)


def test_global_five_hundred_cap_includes_all_phases_and_reserved_attempts(tmp_path) -> None:
    ledger = CallLedger(tmp_path / "ledger.db", "a" * 64)
    for phase, count in (("development", 60), ("final_evaluation", 180), ("fresh_final_rerun", 180), ("contingency", 80)):
        for _number in range(count):
            ledger.reserve("run-" + phase, phase, "b" * 64)
    assert ledger.status()["remaining"] == 0
    with pytest.raises(BudgetExceeded):
        ledger.reserve("one-more", "contingency", "c" * 64)
