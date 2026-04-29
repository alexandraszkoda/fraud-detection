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


def test_label_risk_thresholds():
    assert label_risk(10) == "low"
    assert label_risk(35) == "medium"
    assert label_risk(75) == "high"


def test_large_amount_adds_risk():
    assert score_transaction(baseline_tx(amount_usd=1200)) >= 25


def test_high_device_risk_increases_score():
    low = score_transaction(baseline_tx(device_risk_score=10))
    high = score_transaction(baseline_tx(device_risk_score=80))
    assert high > low
    assert high >= 25


def test_international_increases_score():
    domestic = score_transaction(baseline_tx(is_international=0))
    international = score_transaction(baseline_tx(is_international=1))
    assert international > domestic


def test_high_velocity_increases_score():
    calm = score_transaction(baseline_tx(velocity_24h=1))
    rapid = score_transaction(baseline_tx(velocity_24h=8))
    assert rapid > calm
    assert rapid >= 20


def test_prior_chargebacks_increase_score():
    clean = score_transaction(baseline_tx(prior_chargebacks=0))
    one = score_transaction(baseline_tx(prior_chargebacks=1))
    repeat = score_transaction(baseline_tx(prior_chargebacks=3))
    assert one > clean
    assert repeat > one


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


def test_clean_transaction_scores_low():
    tx = baseline_tx(amount_usd=50, velocity_24h=1)
    assert label_risk(score_transaction(tx)) == "low"
