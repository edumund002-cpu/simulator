"""Wealthathon launcher. --self-test also works inside a packaged executable."""
import sys


def self_test() -> int:
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from wealthathon.engine import ASSETS, parse_wan
    from wealthathon.storage import Store
    try:
        with TemporaryDirectory() as path:
            with Store(Path(path) / "verify.db") as db:
                game = db.create_session(seed=9)
                sid = game["id"]
                for round_no in range(1, 6):
                    db.draw_event(sid)
                    state = db.session(sid)
                    allocation = {a: parse_wan(state["draft"][a]) for a in ASSETS}
                    db.submit(sid, allocation)
                    if round_no < 5:
                        db.next_round(sid)
                assert db.session(sid)["phase"] == "completed"
                assert len(db.rounds(sid)) == 5
                assert db.integrity_check() == "ok"
        return 0
    except Exception:
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())
    from wealthathon.gui import main
    main()
