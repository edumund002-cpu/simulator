# -*- coding: utf-8 -*-
"""
Wealthathon Practice Simulator
本地 Windows Python/Tkinter 训练程序（教学模拟，不代表正式比赛规则）
运行：python wealthathon_simulator.py
"""
import tkinter as tk
from tkinter import ttk, messagebox
import random
import json
import os
from datetime import datetime

INITIAL_CAPITAL = 1_000_000.0

ASSETS = {
    "科技股": {"key": "tech", "group": "股票", "vol": 0.10},
    "医药股": {"key": "health", "group": "股票", "vol": 0.065},
    "政府债券": {"key": "gov", "group": "债券", "vol": 0.025},
    "企业债券": {"key": "corp", "group": "债券", "vol": 0.045},
    "现金": {"key": "cash", "group": "现金", "vol": 0.0},
}

SCENARIOS = [
    {
        "name": "通胀意外升温",
        "headline": "通胀数据高于市场预期，市场重新评估利率路径。",
        "detail": "利率上行预期可能压低股票估值和债券价格；企业融资成本也可能上升。",
        "returns": {"科技股": -0.085, "医药股": -0.035, "政府债券": -0.050, "企业债券": -0.045, "现金": 0.0},
        "question": "利率上行会怎样影响不同资产？你的组合是否有过高的利率敏感度？"
    },
    {
        "name": "经济衰退担忧",
        "headline": "就业与消费数据同步走弱，市场担忧经济增长放缓。",
        "detail": "企业盈利预期承压，资金可能转向高信用质量政府债；企业债信用风险也可能上升。",
        "returns": {"科技股": -0.105, "医药股": -0.045, "政府债券": 0.035, "企业债券": -0.075, "现金": 0.0},
        "question": "股票下跌风险、政府债避险作用和企业债信用风险应如何权衡？"
    },
    {
        "name": "科技盈利超预期",
        "headline": "大型科技企业上调盈利指引，板块风险偏好回升。",
        "detail": "科技股可能受益，但需考虑市场是否已提前计入利好，以及行业集中度。",
        "returns": {"科技股": 0.105, "医药股": 0.025, "政府债券": -0.012, "企业债券": 0.012, "现金": 0.0},
        "question": "是否应该增加股票仓位？如何避免过度集中于同一风险因子？"
    },
    {
        "name": "信用风险扩散",
        "headline": "多家企业债发行人信用指标恶化，信用利差扩大。",
        "detail": "投资者要求更高信用风险补偿。政府债可能受益于避险需求，但企业债价格承压。",
        "returns": {"科技股": -0.035, "医药股": -0.018, "政府债券": 0.025, "企业债券": -0.095, "现金": 0.0},
        "question": "请区分基准利率变化与信用利差变化，不要只看企业债收益率。"
    },
    {
        "name": "温和经济复苏",
        "headline": "经济数据改善，通胀保持温和，企业盈利预期上修。",
        "detail": "风险偏好改善，股票与企业债可能受益；债券收益率温和上行可能压低债券价格。",
        "returns": {"科技股": 0.065, "医药股": 0.040, "政府债券": -0.018, "企业债券": 0.035, "现金": 0.0},
        "question": "如何在增长机会与组合防御性之间寻找平衡？"
    },
    {
        "name": "流动性冲击",
        "headline": "市场流动性突然收紧，风险资产买卖价差扩大。",
        "detail": "部分风险资产遭遇抛售，现金的灵活性提升，企业债可能出现流动性折价。",
        "returns": {"科技股": -0.085, "医药股": -0.060, "政府债券": 0.012, "企业债券": -0.085, "现金": 0.0},
        "question": "现金缓冲是否充足？企业债的信用风险和流动性风险如何区分？"
    },
    {
        "name": "央行意外降息",
        "headline": "央行释放宽松政策信号，市场利率下行预期增强。",
        "detail": "固定票息债券价格通常受益，但仍需观察经济增长与信用利差的变化。",
        "returns": {"科技股": 0.035, "医药股": 0.025, "政府债券": 0.055, "企业债券": 0.025, "现金": 0.0},
        "question": "政府债和企业债是否都会上涨？信用利差可能怎样改变结果？"
    },
]

class Simulator:
    def __init__(self, root):
        self.root = root
        self.root.title("Wealthathon Practice Simulator")
        self.root.geometry("1120x850")
        self.root.minsize(920, 700)
        self.capital = INITIAL_CAPITAL
        self.nav = INITIAL_CAPITAL
        self.peak = INITIAL_CAPITAL
        self.max_dd = 0.0
        self.round_no = 1
        self.max_rounds = 5
        self.event = None
        self.locked = False
        self.history = []
        self.weights = {name: 0.20 for name in ASSETS}
        self.vars = {}
        self._build_ui()
        self._refresh_all()

    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("Head.TLabel", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Big.TLabel", font=("Microsoft YaHei UI", 15, "bold"))
        style.configure("TButton", padding=7)
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="Wealthathon Practice Simulator", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="本地教学模拟 · 非正式比赛平台", foreground="#777").pack(side="right")

        metrics = ttk.Frame(outer)
        metrics.pack(fill="x", pady=(0, 10))
        self.metric_labels = {}
        for title, key in [("组合净值", "nav"), ("累计收益率", "return"), ("累计盈亏", "pnl"), ("最大回撤", "mdd")]:
            box = ttk.LabelFrame(metrics, text=title, padding=10)
            box.pack(side="left", fill="x", expand=True, padx=(0, 7))
            label = ttk.Label(box, text="—", style="Big.TLabel")
            label.pack(anchor="w")
            self.metric_labels[key] = label

        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right = ttk.Frame(body)
        right.pack(side="right", fill="both", expand=True)

        event_box = ttk.LabelFrame(left, text="一、市场事件与决策任务", padding=10)
        event_box.pack(fill="x", pady=(0, 8))
        self.event_title = ttk.Label(event_box, text="准备开始第一轮训练", style="Head.TLabel", wraplength=480)
        self.event_title.pack(anchor="w")
        self.event_detail = ttk.Label(event_box, text="点击“抽取市场事件”，阅读信息后再决定资产配置。", wraplength=480, justify="left")
        self.event_detail.pack(anchor="w", pady=7)
        self.event_question = ttk.Label(event_box, text="本轮任务：先建立初始组合。", wraplength=480, foreground="#286090")
        self.event_question.pack(anchor="w")
        self.draw_btn = ttk.Button(event_box, text="抽取市场事件", command=self.draw_event)
        self.draw_btn.pack(anchor="w", pady=(9, 0))

        alloc_box = ttk.LabelFrame(left, text="二、投资组合配置（单位：万元）", padding=10)
        alloc_box.pack(fill="both", expand=True, pady=(0, 8))
        ttk.Label(alloc_box, text="总资金会随每轮结算变化；五类资产配置之和必须等于当前净值。", foreground="#777").pack(anchor="w", pady=(0, 8))
        self.total_label = ttk.Label(alloc_box, text="")
        self.total_label.pack(anchor="w")
        for name in ASSETS:
            row = ttk.Frame(alloc_box)
            row.pack(fill="x", pady=5)
            ttk.Label(row, text=name, width=12).pack(side="left")
            var = tk.StringVar(value="20.00")
            self.vars[name] = var
            entry = ttk.Entry(row, textvariable=var, width=12)
            entry.pack(side="left")
            entry.bind("<KeyRelease>", lambda e: self._allocation_changed())
            ttk.Label(row, text="万元").pack(side="left", padx=5)
            self.weights[name] = 0.20
        presets = ttk.Frame(alloc_box)
        presets.pack(fill="x", pady=8)
        ttk.Button(presets, text="平均配置", command=self.equal_weights).pack(side="left", padx=(0, 6))
        ttk.Button(presets, text="提高现金缓冲", command=self.more_cash).pack(side="left")
        self.alloc_status = ttk.Label(alloc_box, text="")
        self.alloc_status.pack(anchor="w", pady=5)
        self.submit_btn = ttk.Button(alloc_box, text="提交本轮决策并结算", command=self.submit, state="disabled")
        self.submit_btn.pack(anchor="w", pady=6)

        risk_box = ttk.LabelFrame(right, text="三、风险概览", padding=10)
        risk_box.pack(fill="x", pady=(0, 8))
        self.risk_text = tk.Text(risk_box, height=8, wrap="word", relief="flat", background="#f4f6f8")
        self.risk_text.pack(fill="x")
        self.risk_text.configure(state="disabled")

        result_box = ttk.LabelFrame(right, text="四、结算与复盘", padding=10)
        result_box.pack(fill="both", expand=True, pady=(0, 8))
        self.result_text = tk.Text(result_box, height=15, wrap="word")
        self.result_text.pack(fill="both", expand=True)
        self.result_text.insert("1.0", "完成本轮配置后，这里会显示各资产涨跌、组合盈亏与风险反馈。")
        self.result_text.configure(state="disabled")

        history_box = ttk.LabelFrame(outer, text="五、训练记录", padding=8)
        history_box.pack(fill="x")
        cols = ("round", "event", "ret", "nav", "score")
        self.tree = ttk.Treeview(history_box, columns=cols, show="headings", height=5)
        for col, text, width in [("round", "轮次", 65), ("event", "市场情境", 260), ("ret", "本轮收益", 120), ("nav", "期末净值（万）", 140), ("score", "训练分", 100)]:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor="center")
        self.tree.pack(fill="x")
        bottom = ttk.Frame(outer)
        bottom.pack(fill="x", pady=(8, 0))
        self.next_btn = ttk.Button(bottom, text="进入下一轮", command=self.next_round, state="disabled")
        self.next_btn.pack(side="left")
        ttk.Button(bottom, text="导出训练记录", command=self.export_history).pack(side="left", padx=7)
        ttk.Button(bottom, text="重新开始", command=self.reset).pack(side="right")

    def _read_allocations(self):
        vals = {}
        for name, var in self.vars.items():
            try:
                value = float(var.get())
            except ValueError:
                return None
            if value < 0:
                return None
            vals[name] = value * 10000
        return vals

    def _allocation_changed(self):
        self._refresh_all()

    def _refresh_all(self):
        vals = self._read_allocations()
        total = sum(vals.values()) if vals else 0
        self.total_label.config(text=f"当前组合净值：{self.nav/10000:.2f} 万")
        if vals is None:
            self.alloc_status.config(text="请输入非负数字。")
            valid = False
        else:
            diff = total - self.nav
            valid = abs(diff) < 0.5
            self.alloc_status.config(text=f"配置合计：{total/10000:.2f} 万 / {self.nav/10000:.2f} 万"
                                     + ("  ✓ 配置有效" if valid else f"  尚差 {diff/10000:+.2f} 万"))
        self.submit_btn.config(state="normal" if valid and self.event and not self.locked else "disabled")
        if vals:
            eq = (vals["科技股"] + vals["医药股"]) / self.nav if self.nav else 0
            bond = (vals["政府债券"] + vals["企业债券"]) / self.nav if self.nav else 0
            cash = vals["现金"] / self.nav if self.nav else 0
            concentration = max(vals.values()) / self.nav if self.nav else 0
            notes = [
                f"股票比例：{eq:.1%}",
                f"债券比例：{bond:.1%}",
                f"现金比例：{cash:.1%}",
                f"最大单项资产比例：{concentration:.1%}",
            ]
            if eq > .65: notes.append("风险提示：股票仓位较高。")
            if vals["企业债券"] / self.nav > .25: notes.append("风险提示：企业债集中度较高。")
            if cash < .05: notes.append("风险提示：现金缓冲较低。")
            if concentration > .5: notes.append("风险提示：单项资产集中度较高。")
            self.risk_text.config(state="normal")
            self.risk_text.delete("1.0", "end")
            self.risk_text.insert("1.0", "\n".join(notes))
            self.risk_text.config(state="disabled")
        self.metric_labels["nav"].config(text=f"{self.nav/10000:,.2f} 万")
        self.metric_labels["return"].config(text=f"{(self.nav/INITIAL_CAPITAL-1)*100:+.2f}%")
        self.metric_labels["pnl"].config(text=f"{(self.nav-INITIAL_CAPITAL)/10000:+.2f} 万")
        self.metric_labels["mdd"].config(text=f"{self.max_dd:.2f}%")

    def draw_event(self):
        if self.locked or self.round_no > self.max_rounds:
            return
        self.event = random.choice(SCENARIOS)
        self.event_title.config(text=f"第 {self.round_no}/{self.max_rounds} 轮｜{self.event['name']}：{self.event['headline']}")
        self.event_detail.config(text=self.event["detail"])
        self.event_question.config(text="本轮思考：" + self.event["question"])
        self.draw_btn.config(state="disabled")
        self._refresh_all()

    def equal_weights(self):
        amount = self.nav / 5 / 10000
        for var in self.vars.values():
            var.set(f"{amount:.2f}")
        self._refresh_all()

    def more_cash(self):
        vals = self._read_allocations()
        if not vals:
            return
        move = min(vals["科技股"], self.nav * .10)
        vals["科技股"] -= move
        vals["现金"] += move
        self._set_values(vals)

    def _set_values(self, vals):
        for name, var in self.vars.items():
            var.set(f"{vals[name]/10000:.2f}")
        self._refresh_all()

    def submit(self):
        vals = self._read_allocations()
        if not self.event or not vals or abs(sum(vals.values()) - self.nav) >= .5:
            return
        if not messagebox.askyesno("确认提交", "提交后将揭晓本轮市场冲击，不能修改本轮配置。确定吗？"):
            return
        start_nav = self.nav
        pnl_by_asset = {name: vals[name] * self.event["returns"][name] for name in ASSETS}
        pnl = sum(pnl_by_asset.values())
        self.nav += pnl
        self.peak = max(self.peak, self.nav)
        dd = (self.peak - self.nav) / self.peak * 100 if self.peak else 0
        self.max_dd = max(self.max_dd, dd)
        eq = (vals["科技股"] + vals["医药股"]) / start_nav
        corp = vals["企业债券"] / start_nav
        cash = vals["现金"] / start_nav
        concentration = max(vals.values()) / start_nav
        risk_score = max(0, min(100, 100 - 35*eq - 25*corp + 15*cash - 35*max(0, concentration-.35)*2))
        discipline_score = max(0, 100 - (15 if concentration > .5 else 0) - (10 if cash < .05 else 0))
        performance_score = max(0, min(100, 50 + pnl/start_nav*300))
        score = round(.4*risk_score + .35*discipline_score + .25*performance_score)
        ret = pnl / start_nav * 100
        self.history.append({
            "round": self.round_no, "event": self.event["name"], "return_pct": ret,
            "nav": self.nav, "pnl": pnl, "score": score, "weights": vals.copy(),
            "asset_pnl": pnl_by_asset.copy()
        })
        for item in self.tree.get_children():
            self.tree.delete(item)
        for h in self.history:
            self.tree.insert("", "end", values=(h["round"], h["event"], f'{h["return_pct"]:+.2f}%',
                                                  f'{h["nav"]/10000:.2f}', h["score"]))
        lines = [f"市场情境：{self.event['name']}", "", "各资产损益："]
        for name in ASSETS:
            lines.append(f"  {name}：{pnl_by_asset[name]/10000:+.2f} 万（情境涨跌 {self.event['returns'][name]*100:+.2f}%）")
        lines += ["", f"本轮盈亏：{pnl/10000:+.2f} 万", f"本轮收益率：{ret:+.2f}%",
                  f"期末净值：{self.nav/10000:.2f} 万", f"当前最大回撤：{self.max_dd:.2f}%",
                  "", f"风险控制分：{risk_score:.0f}/100",
                  f"纪律分：{discipline_score:.0f}/100",
                  f"收益表现分：{performance_score:.0f}/100",
                  f"综合训练分：{score}/100", "", "复盘提示："]
        tips = []
        if self.event["returns"]["企业债券"] <= -.05 and vals["企业债券"]/start_nav > .15:
            tips.append("企业债信用冲击较大，复核企业债仓位和发行人偿债能力。")
        if self.event["returns"]["政府债券"] < 0 and vals["政府债券"]/start_nav > .25:
            tips.append("政府债也会因利率变化而下跌，不应视为无风险资产。")
        if eq > .6 and min(self.event["returns"]["科技股"], self.event["returns"]["医药股"]) < -.04:
            tips.append("股票仓位较高，检查行业集中度和相关性。")
        if cash < .05:
            tips.append("现金缓冲偏低，注意后续应对市场冲击的灵活性。")
        if not tips:
            tips.append("检查收益来源是否与事前逻辑一致，并留意组合集中度。")
        lines.extend("• " + t for t in tips)
        self.result_text.config(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", "\n".join(lines))
        self.result_text.config(state="disabled")
        self.locked = True
        self.submit_btn.config(state="disabled")
        self.draw_btn.config(state="disabled")
        self.next_btn.config(state="normal")
        self._refresh_all()

    def next_round(self):
        if not self.locked:
            return
        if self.round_no >= self.max_rounds:
            avg = sum(h["score"] for h in self.history) / len(self.history)
            messagebox.showinfo("五轮训练完成",
                                f"最终净值：{self.nav/10000:.2f} 万\n"
                                f"累计收益：{(self.nav/INITIAL_CAPITAL-1)*100:+.2f}%\n"
                                f"最大回撤：{self.max_dd:.2f}%\n"
                                f"平均训练分：{avg:.1f}/100\n\n"
                                "请导出记录，并与教练一起复盘。")
            self.next_btn.config(state="disabled", text="训练完成")
            return
        self.round_no += 1
        # 新一轮资金等于上一轮期末净值。按上一轮资产权重同比例缩放，
        # 避免净值变化后，旧配置金额与新资金总额不一致，导致无法提交。
        old_values = self._read_allocations()
        if old_values and sum(old_values.values()) > 0:
            old_total = sum(old_values.values())
            scale = self.nav / old_total
            scaled_values = {name: value * scale for name, value in old_values.items()}
        else:
            scaled_values = {name: self.nav / len(ASSETS) for name in ASSETS}
        self.capital = self.nav
        self._set_values(scaled_values)
        self.root.title(f"Wealthathon Practice Simulator — 第 {self.round_no}/{self.max_rounds} 轮")
        self.event = None
        self.locked = False
        self.event_title.config(text=f"第 {self.round_no}/{self.max_rounds} 轮｜等待市场事件")
        self.event_detail.config(text="上一轮期末净值将作为本轮资金。请重新评估资产配置。")
        self.event_question.config(text="先抽取事件，再调整组合。")
        self.draw_btn.config(state="normal")
        self.next_btn.config(state="disabled")
        self.result_text.config(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", "等待下一轮结算。")
        self.result_text.config(state="disabled")
        self._refresh_all()

    def export_history(self):
        if not self.history:
            messagebox.showinfo("暂无记录", "完成至少一轮后才能导出。")
            return
        filename = f"wealthathon_history_{datetime.now():%Y%m%d_%H%M%S}.json"
        data = {"disclaimer": "教学模拟数据，不代表正式比赛规则或真实市场预测。", "history": self.history}
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("导出成功", f"记录已保存到程序当前目录：\n{os.path.abspath(filename)}")
        except OSError as exc:
            messagebox.showerror("导出失败", str(exc))

    def reset(self):
        if not messagebox.askyesno("重新开始", "确定清空当前训练并重新开始吗？"):
            return
        self.nav = INITIAL_CAPITAL
        self.capital = INITIAL_CAPITAL
        self.peak = INITIAL_CAPITAL
        self.max_dd = 0.0
        self.round_no = 1
        self.event = None
        self.locked = False
        self.history.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._set_values({name: INITIAL_CAPITAL/5 for name in ASSETS})
        self.event_title.config(text="准备开始第一轮训练")
        self.event_detail.config(text="点击“抽取市场事件”，阅读信息后再决定资产配置。")
        self.event_question.config(text="本轮任务：先建立初始组合。")
        self.draw_btn.config(state="normal")
        self.next_btn.config(state="disabled")
        self.result_text.config(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", "完成本轮配置后，这里会显示各资产涨跌、组合盈亏与风险反馈。")
        self.result_text.config(state="disabled")
        self._refresh_all()

if __name__ == "__main__":
    root = tk.Tk()
    app = Simulator(root)
    root.mainloop()
