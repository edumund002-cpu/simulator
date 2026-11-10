# Wealthathon 初赛财富管理训练器 v1.0

> **非官方教学模拟。** 基于队友提供的 `wealthathon_simulator_fixed.py` 重构，不是香港大学或 AmplifyME 的官方比赛客户端，也不声称复制比赛规则、实时市场行情或正式排名公式。

## 目前已实现

- Windows 和 macOS 的 PySide6 桌面界面（源代码 + 对应系统的自动构建配置）。
- 五类资产：科技股、医药股、政府债券、企业债券、现金。
- 七种市场情景，五轮训练，默认初始资金人民币 1,000,000 元，训练评分保留队友原型的自定义逻辑。
- 金额使用**整数分**与 Decimal 计算；配置总额必须精确等于净值。
- 每场训练独立档案、每轮提交同步写入 SQLite、未完成场次恢复、训练记录永久留存（除非主动删除数据库）。
- 草稿编辑停止 350 ms 自动保存；正常退出前额外保存。注意：编辑刚发生就异常断电，未提交草稿仍可能丢失；已成功提交的轮次使用数据库事务。
- 市场事件随机序列由种子决定：相同种子可对比相同情景下的不同策略。
- 完整 JSON 导出/校验导入（不会覆盖原数据）、Excel 兼容 CSV 导出、全库一致性备份。
- 单场净值曲线、逐轮收益、损益归因、最大回撤、自定义训练评分、同情景场次对比。

## 如何取得可双击运行的程序

此交付包含完整项目和自动打包流程，但**未附经 Windows/macOS 实机验证的已签名二进制文件**。不要将源码 ZIP 当作可直接双击的 EXE/APP。

**自动构建**：将本项目完整上传至你们的 GitHub 仓库（保留隐藏的 `.github/` 目录），在 `Actions > Build and test Wealthathon desktop packages > Run workflow` 启动。成功后从本次工作流的 Artifacts 下载：

1. `WealthathonSimulator-windows-x64`：解压，打开文件夹中的 `WealthathonSimulator.exe`，不要只移动 exe 文件。
2. `WealthathonSimulator-macos-intel`：解压，打开 `WealthathonSimulator.app`（Intel Mac）。
3. `WealthathonSimulator-macos-apple-silicon`：解压，打开 `WealthathonSimulator.app`（M 系列 Mac）。

macOS 安装包目前**未使用 Apple Developer ID 签名和公证**，系统可能阻止开启；要达到无需任何系统警告的正式发布标准，需要签名、公证并进行 Mac 实机验收。Windows 的未签名程序也可能出现 SmartScreen 提示。

**本地开发运行**（开发者需要 Python 3.12+、互联网下载安装依赖）：

```bash
python -m pip install -r requirements-dev.txt
python main.py
```

Windows 构建命令：`powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1`  
macOS 构建命令：`bash scripts/build_macos.sh`

两种脚本均会先跑自动化测试，再打包并运行已打包程序的 `--self-test`；只可以在对应系统构建该系统安装包，不能在 Linux 上直接产出可验收的 Windows/Mac 安装包。

## 训练操作

1. 启动软件，自动创建一个新的独立训练档案。
2. 点击“抽取本轮市场事件”，阅读新闻与提示。
3. 修改五种资产的配置金额，单位**万元**，最多六位小数（相当于精确到分）。配置和必须与净值精确相等。
4. 点击“确认配置并结算本轮”。确认后的交易决策立即写入数据库，不能撤销/重复提交。
5. 查看资产损益、评分、净值轨迹和风险指标，再点击“进入下一轮”。默认下轮配置继承上一轮**市场价格变化后的实际持仓**；可继续调仓。
6. 五轮完成后，数据自动保留；点击左侧场次可查看历史，或新建下一场独立训练。
7. 点击“相同情景再练一次”可沿用本场情景种子，并用“同情景策略对比”查看策略差别。建议只直接比较相同完成轮数的场次。

## 数据保存位置

| 系统 | 默认路径 |
| --- | --- |
| Windows | `%LOCALAPPDATA%\WealthathonSimulator\wealthathon.db` |
| macOS | `~/Library/Application Support/WealthathonSimulator/wealthathon.db` |
| Linux (仅开发) | `~/.local/share/wealthathon-simulator/wealthathon.db` |

可以用环境变量 `WEALTHATHON_DATA_DIR` 指定保存文件夹。数据库使用 SQLite WAL 和 FULL 同步、原子提交；无需联网。在不同系统之间交换数据，推荐使用 JSON 导出再导入；全库 `.db` 备份适合灾难恢复。

**重要提醒：** 数据是存在本机，不是云端。磁盘损坏、误删文件、用户配置文件删除都会造成数据丢失。建议每次大规模练习结束，点击“备份全部数据库”，把 `.db` 文件复制到另一块盘，或导出 JSON 留作备份。不要在正在运行时手动复制单个数据库文件，使用内置备份按钮。

**备份恢复：** 退出程序后，把备份文件复制回对应系统的数据目录，并重命名为 `wealthathon.db`。恢复前先对当前数据库及可能存在的 `wealthathon.db-wal`、`wealthathon.db-shm` 做整套备份；确保所有程序实例已关闭。随后把原数据库及旧的 `-wal` / `-shm` 文件**移出数据目录**，再放入备份并命名为 `wealthathon.db`；不要让旧的 WAL 日志搭配新的备份文件，也不要在程序运行中覆盖数据库。JSON 导入则支持运行中进行，不覆盖现有场次。

## 规则边界

**当前所有比赛参数均为队友训练原型的假设，而非官方确认：**

- 初始资金 100 万元、5 轮、5 类资产、7 种情景。
- 初赛采用读事件 → 配置 → 揭晓情景涨跌的简化方式，不处理实时订单簿、买卖价差、手续费、融资杠杆或真实历史行情。
- 风险分、纪律分、表现分采用队友原型自定义公式，并按 40% / 35% / 25% 合成训练分。
- 无论正式平台是否允许重复资产配置或提供更多工具，这里都不能代表真实比赛可行操作。
- 本版本以中文学习界面为主；英文正式比赛术语与评分对齐需等规则资料。

## 开发与测试

```bash
python -m pytest -q
python main.py --self-test
```

- `wealthathon/engine.py`：与界面无关的确定性金融计算。
- `wealthathon/scenarios.json`：从队友代码整理出的七种事件及资产情景收益。
- `wealthathon/storage.py`：SQLite 持久化、状态转换、事务、JSON/CSV 导出、验证导入和数据库备份。
- `wealthathon/gui.py`：跨系统桌面 UI。
- `tests/`：数据正确性与容错测试，并在安装 PySide6 的平台自动执行 GUI 冒烟测试。
- `.github/workflows/build.yml`：Windows x64、Mac Intel、Mac Apple Silicon 自动构建。

## 首次正式发布前待完成

- 在 GitHub 三类真实构建节点执行工作流并下载验证三种安装包。
- 在目标 Windows / Intel Mac / M 系列 Mac 上进行人工点击流程和异常退出测试。
- 正式发布建议完成数字签名（macOS 额外需要公证）。
- 如获得港大/AmplifyME 官方比赛说明，需要重新审定资产范围、行情机制、操作流程和评分规则。

详见 `ACCEPTANCE.md`。

## GitHub 仓库发布

参见 [`PUBLISH_GITHUB.md`](PUBLISH_GITHUB.md)（最短发布步骤和安装包下载位置）。
