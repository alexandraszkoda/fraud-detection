import pytest

from risk_rules import label_risk, score_transaction


def baseline_tx(**overrides):
    tx = {
        "device_risk_score": 0,
        "is_international": 0,
        "amount_usd": 0,
        "velocity_24h": 0,
        "failed_logins_24h": 0,
        "prior_chargebacks": 0,
    }
    tx.update(overrides)
    return tx


def delta(**overrides):
    """Score contribution of a single rule, measured against the zero baseline."""
    return score_transaction(baseline_tx(**overrides)) - score_transaction(baseline_tx())


# ---------------------------------------------------------------------------
# label_risk: thresholds and boundaries
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("score,expected", [
    (0, "low"),
    (29, "low"),
    (30, "medium"),
    (31, "medium"),
    (59, "medium"),
    (60, "high"),
    (61, "high"),
    (100, "high"),
])
def test_label_risk_boundaries(score, expected):
    assert label_risk(score) == expected


# ---------------------------------------------------------------------------
# Output invariants
# ---------------------------------------------------------------------------

def test_zero_baseline_scores_zero():
    assert score_transaction(baseline_tx()) == 0


def test_score_is_integer():
    assert isinstance(score_transaction(baseline_tx(amount_usd=1500)), int)


def test_score_is_clamped_to_100():
    """Sum of all rule weights exceeds 100; output must clamp at 100."""
    tx = baseline_tx(
        device_risk_score=99,
        is_international=1,
        amount_usd=10_000,
        velocity_24h=20,
        failed_logins_24h=20,
        prior_chargebacks=10,
    )
    assert score_transaction(tx) == 100


def test_score_never_negative():
    """No rule should be able to push the score below zero."""
    tx = baseline_tx()
    assert score_transaction(tx) >= 0


# ---------------------------------------------------------------------------
# Per-rule exact weights — pin the contribution of each tier.
# These tests catch silent weight changes during refactors.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("device_risk_score,expected", [
    (0, 0),
    (39, 0),
    (40, 10),
    (69, 10),
    (70, 25),
    (100, 25),
])
def test_device_risk_score_weights(device_risk_score, expected):
    assert delta(device_risk_score=device_risk_score) == expected


@pytest.mark.parametrize("is_international,expected", [
    (0, 0),
    (1, 15),
])
def test_international_weight(is_international, expected):
    assert delta(is_international=is_international) == expected


@pytest.mark.parametrize("amount_usd,expected", [
    (0, 0),
    (499.99, 0),
    (500, 10),
    (999.99, 10),
    (1000, 25),
    (50_000, 25),
])
def test_amount_weights(amount_usd, expected):
    assert delta(amount_usd=amount_usd) == expected


@pytest.mark.parametrize("velocity_24h,expected", [
    (0, 0),
    (2, 0),
    (3, 5),
    (5, 5),
    (6, 20),
    (50, 20),
])
def test_velocity_weights(velocity_24h, expected):
    assert delta(velocity_24h=velocity_24h) == expected


@pytest.mark.parametrize("failed_logins_24h,expected", [
    (0, 0),
    (1, 0),
    (2, 10),
    (4, 10),
    (5, 20),
    (50, 20),
])
def test_failed_logins_weights(failed_logins_24h, expected):
    assert delta(failed_logins_24h=failed_logins_24h) == expected


@pytest.mark.parametrize("prior_chargebacks,expected", [
    (0, 0),
    (1, 5),
    (2, 20),
    (10, 20),
])
def test_prior_chargebacks_weights(prior_chargebacks, expected):
    assert delta(prior_chargebacks=prior_chargebacks) == expected


# ---------------------------------------------------------------------------
# Monotonicity: increasing any individual risk signal must never reduce score.
# Guards against future sign-flip regressions like the one this branch fixed.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field,low,high", [
    ("device_risk_score", 0, 100),
    ("is_international", 0, 1),
    ("amount_usd", 0, 5000),
    ("velocity_24h", 0, 20),
    ("failed_logins_24h", 0, 10),
    ("prior_chargebacks", 0, 5),
])
def test_signal_is_monotonic_non_decreasing(field, low, high):
    low_score = score_transaction(baseline_tx(**{field: low}))
    high_score = score_transaction(baseline_tx(**{field: high}))
    assert high_score >= low_score, (
        f"Increasing {field} from {low} to {high} decreased the score "
        f"({low_score} -> {high_score}); a risk signal is inverted."
    )


# ---------------------------------------------------------------------------
# Composition: combinations are additive (within the [0, 100] clamp).
# ---------------------------------------------------------------------------

def test_signals_are_additive_below_clamp():
    a = delta(device_risk_score=80)            # +25
    b = delta(is_international=1)              # +15
    combined = score_transaction(
        baseline_tx(device_risk_score=80, is_international=1)
    )
    assert combined == a + b == 40


# ---------------------------------------------------------------------------
# End-to-end labels for realistic scenarios.
# ---------------------------------------------------------------------------

def test_textbook_fraud_pattern_scores_high():
    tx = baseline_tx(
        device_risk_score=85,
        is_international=1,
        amount_usd=1500,
        velocity_24h=8,
        failed_logins_24h=5,
        prior_chargebacks=2,
    )
    assert label_risk(score_transaction(tx)) == "high"


def test_small_domestic_purchase_scores_low():
    tx = baseline_tx(amount_usd=50, velocity_24h=1)
    assert label_risk(score_transaction(tx)) == "low"


def test_moderate_signals_score_medium():
    """Medium-risk device + moderate amount + some velocity + login pressure -> medium band."""
    # 10 + 10 + 5 + 10 = 35
    tx = baseline_tx(
        device_risk_score=45,
        amount_usd=750,
        velocity_24h=3,
        failed_logins_24h=2,
    )
    assert label_risk(score_transaction(tx)) == "medium"


def test_repeat_offender_with_large_purchase_is_high():
    """Prior chargebacks + high-risk device + large purchase + login pressure -> high."""
    # 20 + 25 + 25 + 10 = 80
    tx = baseline_tx(
        prior_chargebacks=2,
        device_risk_score=80,
        amount_usd=1500,
        failed_logins_24h=2,
    )
    assert label_risk(score_transaction(tx)) == "high"
