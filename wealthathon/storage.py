"""SQLite storage, per-round ACID transactions, restart recovery and verified exports."""
from __future__ import annotations

import csv
import json
import os
import secrets
import sqlite3
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .engine import (
    ASSETS, INITIAL_NAV_CENTS, MAX_ROUNDS, RULESET, VERSION, BY_ID,
    choose_scenario, even_allocation, format_wan, round_payload, validate_allocation,
)

DB_SCHEMA_VERSION = 1
EXPORT_FORMAT = "wealthathon-unofficial-session"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def data_directory() -> Path:
    override = os.getenv("WEALTHATHON_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    import sys
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "WealthathonSimulator"
    if os.name == "nt":
        return Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "WealthathonSimulator"
    return Path(os.getenv("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "wealthathon-simulator"


def jdump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def jload(s: str) -> Any:
    return json.loads(s)


def _write_atomic(path: Path, payload: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding=encoding, newline="", delete=False, dir=path.parent, prefix=f".{path.name}.") as f:
            temporary = Path(f.name)
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


class Store:
    def __init__(self, db_path: Path | None = None):
        self.path = Path(db_path) if db_path is not None else data_directory() / "wealthathon.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=15000")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=FULL")
        self._init_schema()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise

    def _init_schema(self):
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version > DB_SCHEMA_VERSION:
            raise ValueError("数据库由更新版本的软件创建，请升级程序。")
        if version == 0:
            with self.transaction():
                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        id TEXT PRIMARY KEY, name TEXT NOT NULL,
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                        version TEXT NOT NULL, ruleset TEXT NOT NULL,
                        seed INTEGER NOT NULL, initial_nav_cents INTEGER NOT NULL,
                        round_no INTEGER NOT NULL, max_rounds INTEGER NOT NULL,
                        phase TEXT NOT NULL, current_event_id TEXT,
                        nav_cents INTEGER NOT NULL, peak_cents INTEGER NOT NULL,
                        max_drawdown_pct TEXT NOT NULL, draft_json TEXT NOT NULL
                    )
                """)
                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS rounds (
                        session_id TEXT NOT NULL, round_no INTEGER NOT NULL,
                        event_id TEXT NOT NULL, payload_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY(session_id, round_no),
                        FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE RESTRICT
                    )
                """)
                self.conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC)")
                self.conn.execute(f"PRAGMA user_version={DB_SCHEMA_VERSION}")

    def integrity_check(self) -> str:
        return self.conn.execute("PRAGMA integrity_check").fetchone()[0]

    def session(self, session_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise KeyError("找不到训练记录")
        item = dict(row)
        item["draft"] = jload(item.pop("draft_json"))
        return item

    def list_sessions(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute("""
            SELECT s.*, (SELECT count(*) FROM rounds r WHERE r.session_id=s.id) AS settled_rounds
            FROM sessions s ORDER BY updated_at DESC, created_at DESC, id DESC
        """)]

    def rounds(self, session_id: str) -> list[dict[str, Any]]:
        return [jload(r["payload_json"]) for r in self.conn.execute(
            "SELECT payload_json FROM rounds WHERE session_id=? ORDER BY round_no", (session_id,)
        )]

    def create_session(self, name: str = "", seed: int | None = None) -> dict[str, Any]:
        seed = secrets.randbelow(2**63) if seed is None else seed
        if type(seed) is not int or not 0 <= seed < 2**63:
            raise ValueError("随机种子需为0到2^63-1之间的整数")
        name = name.strip() or f"模拟训练 {datetime.now():%Y-%m-%d %H:%M}"
        if len(name) > 80:
            raise ValueError("训练名称最长80个字符")
        draft = {a: format_wan(v) for a, v in even_allocation(INITIAL_NAV_CENTS).items()}
        identity, stamp = str(uuid.uuid4()), now_utc()
        with self.transaction():
            self.conn.execute("""
                INSERT INTO sessions (id,name,created_at,updated_at,version,ruleset,seed,initial_nav_cents,
                   round_no,max_rounds,phase,current_event_id,nav_cents,peak_cents,max_drawdown_pct,draft_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (identity, name, stamp, stamp, VERSION, RULESET, seed, INITIAL_NAV_CENTS,
                  1, MAX_ROUNDS, "awaiting_event", None, INITIAL_NAV_CENTS,
                  INITIAL_NAV_CENTS, "0.000000", jdump(draft)))
        return self.session(identity)

    def draw_event(self, session_id: str) -> dict[str, Any]:
        with self.transaction():
            state = self.session(session_id)
            if state["phase"] != "awaiting_event":
                raise ValueError("当前状态不能抽取新事件")
            scenario = choose_scenario(state["seed"], state["round_no"])
            self.conn.execute("UPDATE sessions SET phase='decision', current_event_id=?, updated_at=? WHERE id=?",
                              (scenario["id"], now_utc(), session_id))
        return scenario

    def save_draft(self, session_id: str, texts: dict[str, str]) -> None:
        if set(texts) != set(ASSETS) or any(not isinstance(v, str) or len(v) > 40 for v in texts.values()):
            raise ValueError("配置草稿格式无效")
        with self.transaction():
            state = self.session(session_id)
            if state["phase"] not in ("awaiting_event", "decision"):
                raise ValueError("该轮已经结算，不能再编辑")
            self.conn.execute("UPDATE sessions SET draft_json=?, updated_at=? WHERE id=?",
                              (jdump(texts), now_utc(), session_id))

    def submit(self, session_id: str, allocation: dict[str, int]) -> dict[str, Any]:
        with self.transaction():
            state = self.session(session_id)
            if state["phase"] != "decision" or not state["current_event_id"]:
                raise ValueError("本轮尚未抽取事件，或已经结算；不能重复提交")
            validate_allocation(allocation, state["nav_cents"])
            scenario = choose_scenario(state["seed"], state["round_no"])
            if scenario["id"] != state["current_event_id"]:
                raise ValueError("存储的市场情景与随机序列不一致")
            result = round_payload(allocation, scenario, state["nav_cents"], state["peak_cents"], state["max_drawdown_pct"])
            result.update({"round_no": state["round_no"], "event_id": scenario["id"], "scenario": scenario, "settled_at": now_utc()})
            self.conn.execute("INSERT INTO rounds(session_id,round_no,event_id,payload_json,created_at) VALUES (?,?,?,?,?)",
                              (session_id, state["round_no"], scenario["id"], jdump(result), result["settled_at"]))
            phase = "completed" if state["round_no"] >= state["max_rounds"] else "settled"
            self.conn.execute("""
                UPDATE sessions SET phase=?, nav_cents=?, peak_cents=?, max_drawdown_pct=?,
                    updated_at=?, draft_json=? WHERE id=?
            """, (phase, result["end_nav_cents"], result["peak_cents"], result["max_drawdown_pct"],
                  now_utc(), jdump({a: format_wan(v) for a, v in allocation.items()}), session_id))
        return result

    def next_round(self, session_id: str) -> dict[str, Any]:
        with self.transaction():
            state = self.session(session_id)
            if state["phase"] != "settled" or state["round_no"] >= state["max_rounds"]:
                raise ValueError("不能进入下一轮")
            last = self.rounds(session_id)[-1]
            # Financially consistent: previous period's marked-to-market holdings become next draft.
            if last["end_nav_cents"] != state["nav_cents"]:
                raise ValueError("历史记录与当前净值不一致")
            draft = {a: format_wan(last["end_holdings"][a]) for a in ASSETS}
            self.conn.execute("""
                UPDATE sessions SET phase='awaiting_event', round_no=round_no+1,
                    current_event_id=NULL, draft_json=?, updated_at=? WHERE id=?
            """, (jdump(draft), now_utc(), session_id))
        return self.session(session_id)

    def export_session(self, session_id: str, path: Path) -> Path:
        data = {"format": EXPORT_FORMAT, "schema": DB_SCHEMA_VERSION,
                "disclaimer": "教学模拟，非港大或AmplifyME官方赛制/评分。",
                "session": self.session(session_id), "rounds": self.rounds(session_id)}
        path = Path(path)
        _write_atomic(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        return path

    def export_csv(self, session_id: str, path: Path) -> Path:
        import io
        buf = io.StringIO(newline="")
        writer = csv.writer(buf)
        writer.writerow(["轮次", "情景", "起始净值(元)", "期末净值(元)", "本轮盈亏(元)", "本轮收益率(%)", "最大回撤(%)", "训练分(非官方)"]
                        + [f"{a}配置(元)" for a in ASSETS] + [f"{a}损益(元)" for a in ASSETS])
        for r in self.rounds(session_id):
            yuan = lambda c: f"{c / 100:.2f}"
            writer.writerow([r["round_no"], r["scenario"]["name"], yuan(r["start_nav_cents"]),
                             yuan(r["end_nav_cents"]), yuan(r["pnl_cents"]), r["return_pct"],
                             r["max_drawdown_pct"], r["score"]]
                            + [yuan(r["allocation"][a]) for a in ASSETS]
                            + [yuan(r["asset_pnl"][a]) for a in ASSETS])
        path = Path(path)
        _write_atomic(path, buf.getvalue(), encoding="utf-8-sig")
        return path

    def import_session(self, path: Path) -> dict[str, Any]:
        # Only accept exports produced by this ruleset and schema. Replay checks prevent
        # inconsistent histories from entering the database.
        path = Path(path)
        if path.stat().st_size > 3_000_000:
            raise ValueError("导入文件过大")
        data = json.loads(path.read_text("utf-8"))
        if not isinstance(data, dict) or data.get("format") != EXPORT_FORMAT or data.get("schema") != DB_SCHEMA_VERSION:
            raise ValueError("不兼容的训练记录格式")
        state, history = data.get("session"), data.get("rounds")
        if not isinstance(state, dict) or not isinstance(history, list) or len(history) > MAX_ROUNDS:
            raise ValueError("记录结构不完整")
        if (state.get("ruleset") != RULESET or state.get("initial_nav_cents") != INITIAL_NAV_CENTS
                or state.get("max_rounds") != MAX_ROUNDS):
            raise ValueError("记录来自不兼容的训练规则")
        seed = state.get("seed")
        if type(seed) is not int or not 0 <= seed < 2**63:
            raise ValueError("随机种子无效")
        peak, nav, max_dd = INITIAL_NAV_CENTS, INITIAL_NAV_CENTS, "0.000000"
        for index, r in enumerate(history, 1):
            if not isinstance(r, dict) or r.get("round_no") != index:
                raise ValueError("轮次不连续")
            event = choose_scenario(seed, index)
            if r.get("event_id") != event["id"] or r.get("scenario") != event:
                raise ValueError("历史市场情景不匹配")
            alloc = r.get("allocation")
            calculated = round_payload(alloc, event, nav, peak, max_dd)
            for key, value in calculated.items():
                if r.get(key) != value:
                    raise ValueError(f"第{index}轮数据校验失败：{key}")
            peak, nav, max_dd = calculated["peak_cents"], calculated["end_nav_cents"], calculated["max_drawdown_pct"]
        phase, round_no, current_event = state.get("phase"), state.get("round_no"), state.get("current_event_id")
        n = len(history)
        valid = (
            (phase == "awaiting_event" and round_no == n + 1 and n < MAX_ROUNDS and current_event is None)
            or (phase == "decision" and round_no == n + 1 and n < MAX_ROUNDS and current_event == choose_scenario(seed, round_no)["id"])
            or (phase == "settled" and n >= 1 and n < MAX_ROUNDS and round_no == n and current_event == choose_scenario(seed, n)["id"])
            or (phase == "completed" and n == MAX_ROUNDS and round_no == n and current_event == choose_scenario(seed, n)["id"])
        )
        if not valid or state.get("nav_cents") != nav or state.get("peak_cents") != peak or state.get("max_drawdown_pct") != max_dd:
            raise ValueError("记录状态或净值不一致")
        draft = state.get("draft")
        if not isinstance(draft, dict) or set(draft) != set(ASSETS) or any(not isinstance(v, str) or len(v) > 40 for v in draft.values()):
            raise ValueError("配置草稿损坏")
        identity, stamp = str(uuid.uuid4()), now_utc()
        name = ("导入 · " + str(state.get("name", "历史训练")))[:80]
        with self.transaction():
            self.conn.execute("""
                INSERT INTO sessions (id,name,created_at,updated_at,version,ruleset,seed,initial_nav_cents,
                   round_no,max_rounds,phase,current_event_id,nav_cents,peak_cents,max_drawdown_pct,draft_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (identity, name, stamp, stamp, VERSION, RULESET, seed, INITIAL_NAV_CENTS,
                  round_no, MAX_ROUNDS, phase, current_event, nav, peak, max_dd, jdump(draft)))
            for r in history:
                self.conn.execute("INSERT INTO rounds(session_id,round_no,event_id,payload_json,created_at) VALUES (?,?,?,?,?)",
                                  (identity, r["round_no"], r["event_id"], jdump(r), str(r.get("settled_at", stamp))[:100]))
        return self.session(identity)

    def backup_database(self, path: Path) -> Path:
        path = Path(path)
        if path.resolve() == self.path.resolve():
            raise ValueError("不能覆盖当前正在使用的数据库")
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with sqlite3.connect(temp_path) as backup:
                self.conn.backup(backup)
                if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise IOError("数据库备份一致性校验失败")
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink()
        return path
