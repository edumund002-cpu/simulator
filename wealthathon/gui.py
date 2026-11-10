"""Single-computer PySide6 desktop interface. Finance and persistence are GUI-independent."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication, QFrame, QGroupBox, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QPlainTextEdit, QFileDialog, QScrollArea, QSplitter, QDialog,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QSizePolicy, QHeaderView,
)

from .engine import (
    ASSETS, BY_ID, INITIAL_NAV_CENTS, MAX_ROUNDS, allocation_risk,
    even_allocation, format_wan, parse_wan, validate_allocation,
)
from .storage import Store


STYLE = """
QWidget { background: #f4f6fb; color: #202c40; font-family: 'Arial','Microsoft YaHei','PingFang SC'; font-size: 13px; }
QMainWindow { background: #f4f6fb; }
QGroupBox { background: white; border: 1px solid #dde4f0; border-radius: 12px; margin-top: 17px; padding: 14px 13px 10px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 15px; padding: 0 6px; color: #243b62; }
QPushButton { background: #edf2fb; color: #214369; padding: 9px 12px; border: 1px solid #d4e0f4; border-radius: 8px; font-weight: 600; }
QPushButton:hover { background: #dfeaff; }
QPushButton:disabled { color: #9ea8b8; background: #eff1f5; border-color: #e4e7ee; }
QPushButton#primary { background: #275dde; color: white; border-color: #275dde; }
QPushButton#primary:hover { background: #1b49bd; }
QLineEdit { background: white; border: 1px solid #cfd8e5; border-radius: 7px; padding: 8px; selection-background-color: #99b8f4; }
QLineEdit:focus { border-color: #4c80ee; }
QLineEdit:read-only { background: #f0f3f8; color: #657082; }
QListWidget { background: white; border: 1px solid #dde4f0; border-radius: 9px; padding: 4px; outline: none; }
QListWidget::item { padding: 11px 7px; border-bottom: 1px solid #eef1f6; }
QListWidget::item:selected { background: #e8efff; color: #1e4187; border-radius: 7px; }
QTableWidget { background: white; gridline-color: #e7ebf3; border: 1px solid #e1e6f0; border-radius: 7px; alternate-background-color: #f6f8fc; }
QHeaderView::section { background: #ecf2fb; color: #334769; border: none; border-bottom: 1px solid #dfe5f0; padding: 8px; font-weight: 600; }
QPlainTextEdit { background: #f6f8fc; border: 1px solid #e5eaf3; border-radius: 8px; padding: 8px; line-height: 1.35; }
"""


def money_wan(cents: int) -> str:
    return f"{Decimal(cents) / 1_000_000:,.4f} 万元"


def pct(num: Decimal | str) -> str:
    return f"{Decimal(num):+.2f}%"


class NavChart(QWidget):
    """A lightweight nav line chart, without QtCharts dependencies."""
    def __init__(self):
        super().__init__()
        self.values = [INITIAL_NAV_CENTS]
        self.setMinimumHeight(155)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_values(self, values):
        self.values = list(values) or [INITIAL_NAV_CENTS]
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#f8faff"))
        left, right, top, bottom = 55, 18, 20, 30
        if w <= left + right or h <= top + bottom:
            return
        vals = self.values
        lo, hi = min(vals), max(vals)
        span = max(hi - lo, max(abs(hi), 1) * 0.03)
        center = (hi + lo) / 2
        lo, hi = center - span * 0.6, center + span * 0.6
        # The graphic is informative only; numerical figures remain in the table.
        p.setPen(QPen(QColor("#e3e9f2"), 1))
        for i in range(3):
            y = top + (h - top - bottom) * i / 2
            p.drawLine(left, int(y), w - right, int(y))
        p.setPen(QColor("#697a96"))
        p.setFont(QFont("Arial", 9))
        for i in range(3):
            val = hi - (hi - lo) * i / 2
            y = top + (h - top - bottom) * i / 2
            p.drawText(3, int(y + 4), f"{val / 1_000_000:.1f}万")
        pts = []
        for i, val in enumerate(vals):
            x = left + i * (w - left - right) / max(len(vals) - 1, 1)
            y = top + (hi - val) / max(hi - lo, 1) * (h - top - bottom)
            pts.append(QPointF(x, y))
        path = QPainterPath(pts[0])
        for point in pts[1:]:
            path.lineTo(point)
        p.setPen(QPen(QColor("#2c67de"), 2.8))
        p.drawPath(path)
        p.setBrush(QColor("#2c67de"))
        for point in pts:
            p.drawEllipse(point, 3, 3)
        p.setPen(QColor("#667894"))
        p.drawText(left, h - 9, "起始")
        p.drawText(w - right - 45, h - 9, f"第{len(vals)-1}轮")
        p.end()


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.store = Store()
        self.current_id: str | None = None
        self.current_state: dict | None = None
        self.current_rounds: list[dict] = []
        self.loading = False
        self.draft_timer = QTimer(self)
        self.draft_timer.setSingleShot(True)
        self.draft_timer.setInterval(350)
        self.draft_timer.timeout.connect(self._save_draft)
        self.setWindowTitle("Wealthathon · 初赛财富管理训练器（非官方）")
        self.resize(1310, 900)
        self.setMinimumSize(950, 640)
        self._build()
        self._reload_sessions()
        if self.sessions.count():
            self.sessions.setCurrentRow(0)
        else:
            self._create_session(initial=True)

    def _btn(self, text, slot, primary=False):
        button = QPushButton(text)
        if primary:
            button.setObjectName("primary")
        button.clicked.connect(slot)
        return button

    def _build(self):
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        self.setCentralWidget(split)

        side = QWidget()
        side.setMinimumWidth(242)
        side.setMaximumWidth(310)
        side_v = QVBoxLayout(side)
        side_v.setContentsMargins(14, 17, 10, 15)
        top = QLabel("WEALTHATHON")
        top.setStyleSheet("font-size: 21px; font-weight: 900; color: #1747a5;")
        side_v.addWidget(top)
        tag = QLabel("初赛财富管理训练 · 非官方")
        tag.setStyleSheet("color: #62738b; font-size: 11px;")
        side_v.addWidget(tag)
        side_v.addSpacing(18)
        side_v.addWidget(QLabel("训练档案（自动保存）"))
        self.sessions = QListWidget()
        self.sessions.currentItemChanged.connect(self._session_changed)
        side_v.addWidget(self.sessions, 1)
        side_v.addWidget(self._btn("＋ 新建随机训练", lambda: self._create_session()))
        side_v.addWidget(self._btn("＋ 相同情景再练一次", self._create_same_seed))
        side_v.addSpacing(10)
        side_v.addWidget(self._btn("导出本场 JSON", self._export_json))
        side_v.addWidget(self._btn("导出本场 CSV", self._export_csv))
        side_v.addWidget(self._btn("导入训练 JSON", self._import_json))
        side_v.addWidget(self._btn("同情景策略对比", self._compare_sessions))
        side_v.addWidget(self._btn("备份全部数据库", self._backup))
        side_v.addSpacing(10)
        self.database_label = QLabel(f"数据目录：\n{self.store.path.parent}")
        self.database_label.setWordWrap(True)
        self.database_label.setStyleSheet("color: #6d7a8e; font-size: 10px;")
        side_v.addWidget(self.database_label)
        split.addWidget(side)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        main = QVBoxLayout(content)
        main.setContentsMargins(15, 14, 20, 20)
        main.setSpacing(12)
        self.title_label = QLabel("资产配置模拟")
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)
        self.title_label.setStyleSheet("font-size: 23px; font-weight: 800; color: #142c54;")
        main.addWidget(self.title_label)
        self.subtitle = QLabel("基于队友原型的训练情景；非 AmplifyME 官方平台，也不代表正式评分。")
        self.subtitle.setWordWrap(True)
        self.subtitle.setStyleSheet("font-size: 11px; color: #67768b;")
        main.addWidget(self.subtitle)

        cards = QHBoxLayout()
        self.metrics: dict[str, QLabel] = {}
        for title, key in [("当前净值", "nav"), ("累计收益", "ret"), ("累计盈亏", "pnl"), ("最大回撤", "dd")]:
            box = QFrame()
            box.setStyleSheet("QFrame { background: white; border: 1px solid #e0e6f2; border-radius: 11px; }")
            bv = QVBoxLayout(box)
            l1 = QLabel(title)
            l1.setStyleSheet("border: none; color: #62738b; font-size: 12px;")
            l2 = QLabel("—")
            l2.setStyleSheet("border: none; font-size: 21px; font-weight: 800; color: #183a71;")
            bv.addWidget(l1)
            bv.addWidget(l2)
            cards.addWidget(box)
            self.metrics[key] = l2
        main.addLayout(cards)

        event_box = QGroupBox("01  市场事件与决策任务")
        ev = QVBoxLayout(event_box)
        self.round_state = QLabel("当前轮次")
        self.round_state.setStyleSheet("font-weight: 700; color: #2858a5;")
        ev.addWidget(self.round_state)
        self.event_title = QLabel("等待抽取市场事件")
        self.event_title.setStyleSheet("font-size: 16px; font-weight: 700;")
        self.event_title.setWordWrap(True)
        ev.addWidget(self.event_title)
        self.event_detail = QLabel("")
        self.event_detail.setWordWrap(True)
        ev.addWidget(self.event_detail)
        self.event_question = QLabel("")
        self.event_question.setWordWrap(True)
        self.event_question.setStyleSheet("color: #345e9d;")
        ev.addWidget(self.event_question)
        self.draw_btn = self._btn("抽取本轮市场事件", self._draw_event, primary=True)
        ev.addWidget(self.draw_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        main.addWidget(event_box)

        panels = QHBoxLayout()
        panels.setSpacing(11)
        alloc_box = QGroupBox("02  资产配置 · 单位：万元")
        alloc_v = QVBoxLayout(alloc_box)
        help_line = QLabel("金额最多6位小数（精确到分）；所有配置之和必须等于当前净值。")
        help_line.setWordWrap(True)
        help_line.setStyleSheet("color: #75839a; font-size: 11px;")
        alloc_v.addWidget(help_line)
        self.entries: dict[str, QLineEdit] = {}
        for asset in ASSETS:
            row = QHBoxLayout()
            lab = QLabel(asset)
            lab.setMinimumWidth(74)
            editor = QLineEdit()
            editor.setAlignment(Qt.AlignmentFlag.AlignRight)
            editor.setPlaceholderText("0.000000")
            editor.textChanged.connect(self._editor_changed)
            row.addWidget(lab)
            row.addWidget(editor, 1)
            row.addWidget(QLabel("万"))
            alloc_v.addLayout(row)
            self.entries[asset] = editor
        presets = QHBoxLayout()
        self.equal_btn = self._btn("平均配置", self._preset_equal)
        self.fill_btn = self._btn("现金补齐", self._fill_cash)
        self.cash_btn = self._btn("＋10%现金", self._add_cash)
        presets.addWidget(self.equal_btn)
        presets.addWidget(self.fill_btn)
        presets.addWidget(self.cash_btn)
        alloc_v.addLayout(presets)
        self.sum_label = QLabel("")
        self.sum_label.setWordWrap(True)
        alloc_v.addWidget(self.sum_label)
        self.risk_label = QLabel("")
        self.risk_label.setWordWrap(True)
        self.risk_label.setStyleSheet("color: #556781;")
        alloc_v.addWidget(self.risk_label)
        self.submit_btn = self._btn("确认配置并结算本轮", self._submit, primary=True)
        alloc_v.addWidget(self.submit_btn)
        self.next_btn = self._btn("进入下一轮", self._next_round)
        alloc_v.addWidget(self.next_btn)
        panels.addWidget(alloc_box, 3)

        review = QGroupBox("03  结算复盘（训练分非官方）")
        rv = QVBoxLayout(review)
        self.review_text = QPlainTextEdit()
        self.review_text.setReadOnly(True)
        self.review_text.setMinimumHeight(340)
        rv.addWidget(self.review_text)
        panels.addWidget(review, 4)
        main.addLayout(panels)

        graph_box = QGroupBox("04  净值轨迹")
        graph_v = QVBoxLayout(graph_box)
        self.nav_chart = NavChart()
        graph_v.addWidget(self.nav_chart)
        main.addWidget(graph_box)

        history_box = QGroupBox("05  本场逐轮历史 · 点击行查看复盘")
        hist_v = QVBoxLayout(history_box)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["轮次", "市场情景", "本轮收益", "期末净值", "训练分"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setMinimumHeight(165)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.cellClicked.connect(lambda row, _col: self._show_review(row))
        hist_v.addWidget(self.table)
        main.addWidget(history_box)
        bottom = QLabel("金额与收益为情景训练假设，不构成投资建议。历史记录独立归档；重新训练不会清空旧场次。")
        bottom.setWordWrap(True)
        bottom.setStyleSheet("color: #7d8a9b; font-size: 11px;")
        main.addWidget(bottom)
        scroll.setWidget(content)
        split.addWidget(scroll)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([265, 1030])
        self.statusBar().showMessage("准备就绪 · 自动保存已启用")

    def _error(self, title, exception):
        QMessageBox.critical(self, title, str(exception))
        self.statusBar().showMessage(f"操作失败：{exception}", 9000)

    def _reload_sessions(self, select_id=None):
        self.sessions.blockSignals(True)
        self.sessions.clear()
        selection = 0
        for index, row in enumerate(self.store.list_sessions()):
            phase = {"awaiting_event": "待抽取", "decision": "配置中", "settled": "本轮完成", "completed": "全部完成"}.get(row["phase"], row["phase"])
            item = QListWidgetItem(f"{row['name']}\n{row['settled_rounds']}/{row['max_rounds']}轮 · {phase}")
            item.setData(Qt.ItemDataRole.UserRole, row["id"])
            item.setToolTip(f"编号：{row['id']}\n种子：{row['seed']}")
            self.sessions.addItem(item)
            if row["id"] == select_id:
                selection = index
        self.sessions.blockSignals(False)
        if self.sessions.count():
            self.sessions.setCurrentRow(selection)
            if self.sessions.currentItem():
                self._session_changed(self.sessions.currentItem(), None)

    def _session_changed(self, current, _previous):
        if not current:
            return
        new_id = current.data(Qt.ItemDataRole.UserRole)
        if self.current_id and new_id != self.current_id:
            try:
                self._save_draft()
            except Exception as exc:
                self._error("保存配置草稿失败", exc)
                # Do not silently switch away from unsaved data.
                self._reload_sessions(select_id=self.current_id)
                return
        self.current_id = new_id
        self._refresh()

    def _create_session(self, initial=False, seed=None):
        name = ""
        if not initial:
            name, ok = QInputDialog.getText(self, "创建训练", "训练名称（可留空自动生成）：")
            if not ok:
                return
        try:
            if self.current_id:
                self._save_draft()
            state = self.store.create_session(name, seed=seed)
            self.current_id = state["id"]
            self._reload_sessions(select_id=self.current_id)
            self.statusBar().showMessage("已创建独立训练档案；数据自动保存在本机。", 6000)
        except Exception as exc:
            self._error("新建训练失败", exc)

    def _create_same_seed(self):
        if not self.current_state:
            return
        self._create_session(seed=self.current_state["seed"])

    def _save_draft(self):
        self.draft_timer.stop()
        if self.loading or not self.current_id:
            return
        state = self.store.session(self.current_id)
        if state["phase"] not in ("awaiting_event", "decision"):
            return
        texts = {a: entry.text() for a, entry in self.entries.items()}
        self.store.save_draft(self.current_id, texts)
        if self.current_state and self.current_state["id"] == self.current_id:
            self.current_state["draft"] = texts
        self.statusBar().showMessage("配置草稿已自动保存至本地数据库", 2500)

    def _editor_changed(self, _text):
        if not self.loading:
            self._update_risk_preview()
            self.draft_timer.start()

    def _values(self):
        return {a: parse_wan(editor.text()) for a, editor in self.entries.items()}

    def _set_values(self, cents):
        self.loading = True
        for asset, amount in cents.items():
            self.entries[asset].setText(format_wan(amount))
        self.loading = False
        self._update_risk_preview()
        self.draft_timer.start()

    def _update_risk_preview(self):
        if not self.current_state:
            return
        nav = self.current_state["nav_cents"]
        try:
            vals = self._values()
            diff = sum(vals.values()) - nav
            self.sum_label.setText(f"配置合计：{money_wan(sum(vals.values()))} / {money_wan(nav)}"
                                   + ("   ✓ 精确匹配" if diff == 0 else f"   差额：{diff / 100:+,.2f}元"))
            self.sum_label.setStyleSheet("color: #16805e;" if diff == 0 else "color: #c06b16;")
            self.risk_label.setText("\n".join(allocation_risk(vals, nav)))
            self.submit_btn.setEnabled(self.current_state["phase"] == "decision" and diff == 0)
        except Exception as exc:
            self.sum_label.setText(str(exc))
            self.sum_label.setStyleSheet("color: #c74747;")
            self.risk_label.setText("请输入非负、有效的金额。")
            self.submit_btn.setEnabled(False)

    def _preset_equal(self):
        if self.current_state["phase"] not in ("awaiting_event", "decision"):
            return
        self._set_values(even_allocation(self.current_state["nav_cents"]))

    def _fill_cash(self):
        if self.current_state["phase"] not in ("awaiting_event", "decision"):
            return
        try:
            val = {a: parse_wan(self.entries[a].text()) for a in ASSETS[:-1]}
            remaining = self.current_state["nav_cents"] - sum(val.values())
            if remaining < 0:
                raise ValueError("前四项超过了全部资金，无法用现金补齐")
            self.entries["现金"].setText(format_wan(remaining))
        except Exception as exc:
            self._error("现金补齐失败", exc)

    def _add_cash(self):
        if self.current_state["phase"] not in ("awaiting_event", "decision"):
            return
        try:
            vals = self._values()
            validate_allocation(vals, self.current_state["nav_cents"])
            move = min(vals["科技股"], self.current_state["nav_cents"] // 10)
            vals["科技股"] -= move
            vals["现金"] += move
            self._set_values(vals)
        except Exception as exc:
            self._error("调整现金失败", exc)

    def _draw_event(self):
        try:
            self._save_draft()
            self.store.draw_event(self.current_id)
            self._refresh()
        except Exception as exc:
            self._error("抽取市场事件失败", exc)

    def _submit(self):
        try:
            vals = self._values()
            validate_allocation(vals, self.current_state["nav_cents"])
            if QMessageBox.question(self, "确认本轮结算", "提交后将立即揭晓本轮情景涨跌，无法修改本轮配置。继续？") != QMessageBox.StandardButton.Yes:
                return
            self._save_draft()
            self.store.submit(self.current_id, vals)
            self._reload_sessions(select_id=self.current_id)
            self.statusBar().showMessage("本轮结算已完成并同步写入本地数据库。", 7000)
        except Exception as exc:
            self._error("结算失败", exc)

    def _next_round(self):
        try:
            self.store.next_round(self.current_id)
            self._reload_sessions(select_id=self.current_id)
        except Exception as exc:
            self._error("进入下一轮失败", exc)

    def _refresh(self):
        if not self.current_id:
            return
        self.draft_timer.stop()
        self.loading = True
        try:
            state = self.store.session(self.current_id)
            rows = self.store.rounds(self.current_id)
            self.current_state = state
            self.current_rounds = rows
            self.title_label.setText(state["name"])
            phase = state["phase"]
            status = {"awaiting_event": "等待市场事件", "decision": "资产配置中", "settled": "本轮结算完成", "completed": "五轮全部完成"}[phase]
            self.round_state.setText(f"第 {state['round_no']} / {state['max_rounds']} 轮 · {status}   |   情景种子 {state['seed']}")
            nav = state["nav_cents"]
            self.metrics["nav"].setText(money_wan(nav))
            self.metrics["ret"].setText(f"{(Decimal(nav) / INITIAL_NAV_CENTS - 1) * 100:+.2f}%")
            self.metrics["pnl"].setText(money_wan(nav - INITIAL_NAV_CENTS))
            self.metrics["dd"].setText(f"{Decimal(state['max_drawdown_pct']):.2f}%")
            if state["current_event_id"]:
                event = BY_ID[state["current_event_id"]]
                self.event_title.setText(event["name"] + " · " + event["headline"])
                self.event_detail.setText(event["detail"])
                self.event_question.setText("本轮思考：" + event["question"])
            else:
                self.event_title.setText("等待抽取市场事件")
                self.event_detail.setText("先抽取事件，再根据新闻和市场情景确定资产组合。")
                self.event_question.setText("模拟使用队友的七种固定训练情景，非官方实时行情。")
            self.draw_btn.setEnabled(phase == "awaiting_event")
            self.next_btn.setEnabled(phase == "settled")
            for button in (self.equal_btn, self.fill_btn, self.cash_btn):
                button.setEnabled(phase in ("awaiting_event", "decision"))
            for a in ASSETS:
                self.entries[a].setText(state["draft"].get(a, ""))
                self.entries[a].setReadOnly(phase not in ("awaiting_event", "decision"))
            self.table.setRowCount(0)
            for i, r in enumerate(rows):
                self.table.insertRow(i)
                for j, text in enumerate([
                    str(r["round_no"]), r["scenario"]["name"], pct(r["return_pct"]),
                    money_wan(r["end_nav_cents"]), f"{r['score']}/100",
                ]):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.table.setItem(i, j, item)
            self.nav_chart.set_values([INITIAL_NAV_CENTS] + [r["end_nav_cents"] for r in rows])
            self.review_text.setPlainText("已抽取市场事件。请调整资产配置并提交。" if phase == "decision" else
                                          "等待抽取新事件。" if phase == "awaiting_event" else "")
            if rows:
                self._show_review(len(rows) - 1)
            self.statusBar().showMessage(f"数据库：{self.store.path}")
        except Exception as exc:
            self._error("加载训练档案失败", exc)
        finally:
            self.loading = False
        self._update_risk_preview()

    def _show_review(self, index):
        if not 0 <= index < len(self.current_rounds):
            return
        r = self.current_rounds[index]
        sc = r["scenario"]
        lines = [f"第 {r['round_no']} 轮｜{sc['name']}", "", f"起始净值：{money_wan(r['start_nav_cents'])}",
                 f"本轮盈亏：{money_wan(r['pnl_cents'])}", f"本轮收益：{pct(r['return_pct'])}",
                 f"结算净值：{money_wan(r['end_nav_cents'])}", f"最大回撤：{r['max_drawdown_pct']}%",
                 "", "资产配置 / 情景涨跌 / 损益："]
        for asset in ASSETS:
            ret = Decimal(sc["returns"][asset]) * 100
            lines.append(f"{asset}：{money_wan(r['allocation'][asset])} / {ret:+.2f}% / {money_wan(r['asset_pnl'][asset])}")
        lines += ["", f"风险控制分：{Decimal(r['risk_score']):.1f}",
                  f"纪律分：{Decimal(r['discipline_score']):.1f}",
                  f"收益表现分：{Decimal(r['performance_score']):.1f}",
                  f"综合训练分：{r['score']}/100", "（以上评分为队友原型的自定义训练公式）", "", "复盘要点："]
        lines += ["• " + note for note in r["notes"]]
        self.review_text.setPlainText("\n".join(lines))

    def _export_json(self):
        if not self.current_id:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出本场完整训练档案", f"wealthathon_{self.current_id[:8]}.json", "JSON (*.json)")
        if path:
            try:
                self._save_draft()
                self.store.export_session(self.current_id, Path(path))
                QMessageBox.information(self, "导出完成", f"训练记录已保存至：\n{path}")
            except Exception as exc:
                self._error("导出失败", exc)

    def _export_csv(self):
        if not self.current_id:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出逐轮数据", f"wealthathon_{self.current_id[:8]}.csv", "CSV (*.csv)")
        if path:
            try:
                self._save_draft()
                self.store.export_csv(self.current_id, Path(path))
                QMessageBox.information(self, "导出完成", f"逐轮数据已保存至：\n{path}")
            except Exception as exc:
                self._error("导出失败", exc)

    def _import_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入本软件的训练档案", "", "JSON (*.json)")
        if path:
            try:
                self._save_draft()
                row = self.store.import_session(Path(path))
                self.current_id = row["id"]
                self._reload_sessions(select_id=self.current_id)
                QMessageBox.information(self, "导入完成", "完整校验通过；已作为独立训练档案导入，不覆盖现有记录。")
            except Exception as exc:
                self._error("导入失败（未改变现有记录）", exc)

    def _compare_sessions(self):
        if not self.current_state:
            return
        seed = self.current_state["seed"]
        related = [s for s in self.store.list_sessions() if s["seed"] == seed]
        dialog = QDialog(self)
        dialog.setWindowTitle(f"同市场序列策略对比 · 种子 {seed}")
        dialog.resize(840, 400)
        layout = QVBoxLayout(dialog)
        explanation = QLabel("相同种子使用相同五轮事件顺序。仅可直接比较已完成相同轮数的训练；评分为非官方。")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        table = QTableWidget(len(related), 6)
        table.setHorizontalHeaderLabels(["场次", "完成轮数", "期末净值", "累计收益", "最大回撤", "平均训练分"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i, session in enumerate(related):
            rows = self.store.rounds(session["id"])
            avg = sum(r["score"] for r in rows) / len(rows) if rows else 0
            cells = [session["name"], f"{len(rows)}/{MAX_ROUNDS}", money_wan(session["nav_cents"]),
                     f"{(Decimal(session['nav_cents']) / INITIAL_NAV_CENTS - 1) * 100:+.2f}%",
                     f"{Decimal(session['max_drawdown_pct']):.2f}%", f"{avg:.1f}" if rows else "—"]
            for j, value in enumerate(cells):
                table.setItem(i, j, QTableWidgetItem(value))
        layout.addWidget(table)
        dialog.exec()

    def _backup(self):
        path, _ = QFileDialog.getSaveFileName(self, "备份全部数据库", "wealthathon_backup.db", "SQLite (*.db)")
        if path:
            try:
                self._save_draft()
                self.store.backup_database(Path(path))
                QMessageBox.information(self, "备份完成", f"所有场次已备份到：\n{path}\n请将备份文件复制到其他磁盘保存。")
            except Exception as exc:
                self._error("备份失败", exc)

    def closeEvent(self, event):
        try:
            self._save_draft()
        except Exception as exc:
            if QMessageBox.warning(self, "数据尚未保存", f"保存草稿失败：{exc}\n仍要退出？",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.store.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Wealthathon Simulator")
    app.setOrganizationName("Wealthathon Training")
    app.setStyleSheet(STYLE)
    try:
        window = App()
    except Exception as exc:
        QMessageBox.critical(None, "启动失败", f"无法打开本地数据库：{exc}\n请检查数据目录权限或使用备份恢复。")
        raise SystemExit(1)
    window.show()
    raise SystemExit(app.exec())
