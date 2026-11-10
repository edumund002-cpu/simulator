from decimal import Decimal
import pytest
from wealthathon.engine import (ASSETS, BY_ID, SCENARIOS, INITIAL_NAV_CENTS, MAX_ROUNDS,
    choose_scenario, parse_wan, format_wan, validate_allocation, even_allocation, round_payload)


def test_original_training_data_shape():
    assert len(SCENARIOS) == 7
    assert set(BY_ID) == {s['id'] for s in SCENARIOS}
    assert all(set(s['returns']) == set(ASSETS) for s in SCENARIOS)
    assert len(ASSETS) == 5


def test_parse_money_is_exact_to_cent():
    assert parse_wan('1') == 1_000_000
    assert parse_wan('0.000001') == 1
    assert parse_wan('100.000000') == INITIAL_NAV_CENTS
    assert parse_wan(format_wan(123456789)) == 123456789
    assert parse_wan('  1.25 ') == 1_250_000


@pytest.mark.parametrize('text', ['-2', '1.1234567', 'NaN', 'Infinity', '1e3', '1,000', '', '.', '00.2', '1.2.3'])
def test_invalid_money_is_rejected(text):
    with pytest.raises(ValueError):
        parse_wan(text)


def test_total_must_match_to_last_cent():
    good = even_allocation(INITIAL_NAV_CENTS)
    validate_allocation(good, INITIAL_NAV_CENTS)
    bad = dict(good)
    bad['现金'] += 1
    with pytest.raises(ValueError):
        validate_allocation(bad, INITIAL_NAV_CENTS)
    with pytest.raises(ValueError):
        validate_allocation({a: float(v) for a, v in good.items()}, INITIAL_NAV_CENTS)


def test_event_sequence_is_reproducible():
    a = [choose_scenario(42, i)['id'] for i in range(1, MAX_ROUNDS+1)]
    b = [choose_scenario(42, i)['id'] for i in range(1, MAX_ROUNDS+1)]
    assert a == b
    with pytest.raises(ValueError):
        choose_scenario(42, 6)


def test_exact_financial_identity_all_scenarios():
    for scenario in SCENARIOS:
        allocation = even_allocation(INITIAL_NAV_CENTS)
        result = round_payload(allocation, scenario, INITIAL_NAV_CENTS, INITIAL_NAV_CENTS, '0.000000')
        assert result['end_nav_cents'] == result['start_nav_cents'] + result['pnl_cents']
        assert result['end_nav_cents'] == sum(result['end_holdings'].values())
        assert result['pnl_cents'] == sum(result['asset_pnl'].values())
        for a in ASSETS:
            assert result['end_holdings'][a] == allocation[a] + result['asset_pnl'][a]
        assert 0 <= result['score'] <= 100


def test_all_cash_is_stable_and_drawdown_zero():
    allocation = {a: 0 for a in ASSETS}
    allocation['现金'] = INITIAL_NAV_CENTS
    for scenario in SCENARIOS:
        result = round_payload(allocation, scenario, INITIAL_NAV_CENTS, INITIAL_NAV_CENTS, '0.000000')
        assert result['pnl_cents'] == 0
        assert result['end_nav_cents'] == INITIAL_NAV_CENTS
        assert result['max_drawdown_pct'] == '0.000000'


def test_known_inflation_example():
    result = round_payload(even_allocation(INITIAL_NAV_CENTS), BY_ID['inflation'], INITIAL_NAV_CENTS, INITIAL_NAV_CENTS, '0')
    assert result['pnl_cents'] == -4_300_000
    assert result['end_nav_cents'] == 95_700_000
    assert result['return_pct'] == '-4.300000'
    assert result['max_drawdown_pct'] == '4.300000'


def test_previous_max_drawdown_is_not_erased():
    cash = {a: 0 for a in ASSETS}
    cash['现金'] = INITIAL_NAV_CENTS
    result = round_payload(cash, BY_ID['recovery'], INITIAL_NAV_CENTS, INITIAL_NAV_CENTS, '11.200000')
    assert result['max_drawdown_pct'] == '11.200000'


def test_fractional_cents_round_half_up():
    allocation = {a: 0 for a in ASSETS}
    allocation['科技股'] = 1
    allocation['现金'] = INITIAL_NAV_CENTS - 1
    scenario = dict(BY_ID['recovery'])
    scenario['returns'] = {a: '0' for a in ASSETS}
    scenario['returns']['科技股'] = '0.5'
    r = round_payload(allocation, scenario, INITIAL_NAV_CENTS, INITIAL_NAV_CENTS, '0')
    assert r['asset_pnl']['科技股'] == 1
