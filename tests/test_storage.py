import csv
import json
from pathlib import Path
import pytest
from wealthathon.engine import ASSETS, MAX_ROUNDS, INITIAL_NAV_CENTS, parse_wan
from wealthathon.storage import Store


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / 'test.db') as db:
        yield db


def allocation_from_draft(state):
    return {a: parse_wan(state['draft'][a]) for a in ASSETS}


def settle(db, sid):
    db.draw_event(sid)
    return db.submit(sid, allocation_from_draft(db.session(sid)))


def test_new_session_auto_saved_and_recovered(tmp_path):
    path = tmp_path / 'session.db'
    with Store(path) as db:
        s = db.create_session('训练A', seed=123)
        sid = s['id']
        assert s['phase'] == 'awaiting_event'
        db.draw_event(sid)
        draft = s['draft'].copy()
        draft['现金'] = '18.333333'
        db.save_draft(sid, draft)
    with Store(path) as db:
        assert db.session(sid)['current_event_id'] is not None
        assert db.session(sid)['draft']['现金'] == '18.333333'
        assert db.integrity_check() == 'ok'


def test_submit_is_durable_and_repeated_submit_rejected(tmp_path):
    path = tmp_path / 'durable.db'
    with Store(path) as db:
        sid = db.create_session(seed=42)['id']
        db.draw_event(sid)
        valid = allocation_from_draft(db.session(sid))
        result = db.submit(sid, valid)
        assert len(db.rounds(sid)) == 1
        with pytest.raises(ValueError, match='不能重复提交'):
            db.submit(sid, valid)
        assert len(db.rounds(sid)) == 1
    with Store(path) as db:
        assert db.rounds(sid)[0]['end_nav_cents'] == result['end_nav_cents']
        assert db.session(sid)['phase'] == 'settled'


def test_invalid_allocation_rolls_back_everything(store):
    sid = store.create_session(seed=11)['id']
    store.draw_event(sid)
    nav = store.session(sid)['nav_cents']
    bad = allocation_from_draft(store.session(sid))
    bad['科技股'] += 1
    with pytest.raises(ValueError):
        store.submit(sid, bad)
    assert store.session(sid)['nav_cents'] == nav
    assert store.session(sid)['phase'] == 'decision'
    assert store.rounds(sid) == []


def test_all_five_rounds_and_mark_to_market_carry_forward(store):
    sid = store.create_session(seed=2026)['id']
    for i in range(1, MAX_ROUNDS+1):
        result = settle(store, sid)
        assert result['end_nav_cents'] == sum(result['end_holdings'].values())
        if i < MAX_ROUNDS:
            assert store.session(sid)['phase'] == 'settled'
            state = store.next_round(sid)
            assert state['round_no'] == i+1
            assert state['current_event_id'] is None
            assert allocation_from_draft(state) == result['end_holdings']
        else:
            assert store.session(sid)['phase'] == 'completed'
            with pytest.raises(ValueError):
                store.next_round(sid)
    assert len(store.rounds(sid)) == MAX_ROUNDS
    assert store.session(sid)['nav_cents'] == result['end_nav_cents']
    assert store.integrity_check() == 'ok'


def test_sessions_never_overwrite_each_other(store):
    a = store.create_session('防御型', seed=3)['id']
    b = store.create_session('均衡型', seed=3)['id']
    settle(store, a)
    assert store.rounds(b) == []
    assert store.session(b)['nav_cents'] == INITIAL_NAV_CENTS
    assert len(store.list_sessions()) == 2


def test_restart_after_settlement_and_next_round(tmp_path):
    path = tmp_path / 'restart.db'
    with Store(path) as db:
        sid = db.create_session(seed=36)['id']
        settle(db, sid)
    with Store(path) as db:
        assert db.session(sid)['phase'] == 'settled'
        db.next_round(sid)
        assert db.session(sid)['round_no'] == 2
        db.draw_event(sid)
    with Store(path) as db:
        assert db.session(sid)['phase'] == 'decision'
        db.submit(sid, allocation_from_draft(db.session(sid)))
        assert len(db.rounds(sid)) == 2


def test_export_import_full_validation(store, tmp_path):
    sid = store.create_session('original', seed=234)['id']
    for n in range(3):
        settle(store, sid)
        if n < 2:
            store.next_round(sid)
    out = tmp_path / 'whole.json'
    store.export_session(sid, out)
    imported = store.import_session(out)
    assert imported['id'] != sid
    assert imported['seed'] == 234
    assert imported['nav_cents'] == store.session(sid)['nav_cents']
    assert store.rounds(imported['id']) == store.rounds(sid)
    assert len(store.list_sessions()) == 2
    store.next_round(imported['id'])
    assert store.session(imported['id'])['round_no'] == 4
    assert store.session(sid)['round_no'] == 3


def test_import_can_resume_mid_decision(store, tmp_path):
    sid = store.create_session(seed=7)['id']
    store.draw_event(sid)
    path = tmp_path / 'live.json'
    store.export_session(sid, path)
    new = store.import_session(path)
    assert new['phase'] == 'decision'
    assert new['current_event_id'] == store.session(sid)['current_event_id']
    store.submit(new['id'], allocation_from_draft(new))
    assert len(store.rounds(new['id'])) == 1


def test_tampered_file_does_not_modify_database(store, tmp_path):
    sid = store.create_session(seed=123)['id']
    settle(store, sid)
    path = tmp_path / 'export.json'
    store.export_session(sid, path)
    payload = json.loads(path.read_text(encoding='utf-8'))
    payload['rounds'][0]['pnl_cents'] += 2000
    path.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(ValueError, match='校验失败'):
        store.import_session(path)
    assert len(store.list_sessions()) == 1


def test_csv_encoding_and_columns(store, tmp_path):
    sid = store.create_session(seed=1)['id']
    settle(store, sid)
    path = tmp_path / 'rounds.csv'
    store.export_csv(sid, path)
    assert path.read_bytes().startswith(b'\xef\xbb\xbf')
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        rows = list(csv.reader(f))
    assert len(rows) == 2
    assert len(rows[0]) == 18
    assert '科技股' in rows[0][8]


def test_sqlite_backup_is_consistent(store, tmp_path):
    a = store.create_session(seed=1)['id']
    b = store.create_session(seed=2)['id']
    settle(store, b)
    backup = tmp_path / 'backup.db'
    store.backup_database(backup)
    with Store(backup) as recovered:
        assert recovered.integrity_check() == 'ok'
        assert {s['id'] for s in recovered.list_sessions()} == {a, b}
        assert len(recovered.rounds(b)) == 1


def test_100_complete_simulations_with_preserved_history(store):
    ids = []
    for i in range(100):
        sid = store.create_session(f'Test {i}', seed=i)['id']
        ids.append(sid)
        for step in range(MAX_ROUNDS):
            settle(store, sid)
            if step + 1 < MAX_ROUNDS:
                store.next_round(sid)
    assert len(store.list_sessions()) == 100
    assert all(len(store.rounds(sid)) == MAX_ROUNDS for sid in ids)
    assert store.integrity_check() == 'ok'


def test_multiple_store_instances_cannot_submit_twice(tmp_path):
    path = tmp_path / 'shared.db'
    with Store(path) as one, Store(path) as two:
        sid = one.create_session(seed=1)['id']
        one.draw_event(sid)
        alloc = allocation_from_draft(one.session(sid))
        one.submit(sid, alloc)
        with pytest.raises(ValueError):
            two.submit(sid, alloc)
        assert len(two.rounds(sid)) == 1


def test_transaction_rollback_when_post_insert_update_fails(store):
    sid = store.create_session(seed=88)['id']
    store.draw_event(sid)
    allocation = allocation_from_draft(store.session(sid))
    store.conn.execute("""
        CREATE TRIGGER deliberately_fail_update BEFORE UPDATE ON sessions
        WHEN NEW.phase='settled' BEGIN SELECT RAISE(ABORT, 'simulated disk/database error'); END;
    """)
    with pytest.raises(Exception, match='simulated disk/database error'):
        store.submit(sid, allocation)
    # The inserted round must roll back together with the failed session update.
    assert store.rounds(sid) == []
    assert store.session(sid)['phase'] == 'decision'
    store.conn.execute('DROP TRIGGER deliberately_fail_update')
    store.submit(sid, allocation)
    assert len(store.rounds(sid)) == 1


def test_can_export_and_import_completed_session(store, tmp_path):
    sid = store.create_session(seed=45)['id']
    for i in range(MAX_ROUNDS):
        settle(store, sid)
        if i < MAX_ROUNDS - 1:
            store.next_round(sid)
    path = tmp_path / 'completed.json'
    store.export_session(sid, path)
    copy = store.import_session(path)
    assert copy['phase'] == 'completed'
    assert len(store.rounds(copy['id'])) == MAX_ROUNDS
    assert copy['nav_cents'] == store.session(sid)['nav_cents']


def test_cannot_import_unrelated_json_or_oversized_file(store, tmp_path):
    path = tmp_path / 'unrelated.json'
    path.write_text('{"foo": 1}', encoding='utf-8')
    with pytest.raises(ValueError, match='不兼容'):
        store.import_session(path)
    path.write_bytes(b' ' * 3_000_001)
    with pytest.raises(ValueError, match='过大'):
        store.import_session(path)
