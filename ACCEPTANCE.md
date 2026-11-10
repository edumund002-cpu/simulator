# 验收清单 · v1.0

## 验收判定标准

| 条目 | 自动测试 | 当前证据与状态 |
| --- | --- | --- |
| 7 种情景、5 种资产、5 轮 | `test_engine.py`、`test_storage.py` | **通过**：原文件情景已完整保留 |
| 金额按分精确计算、总额校验 | `test_parse_money_is_exact_to_cent`、`test_total_must_match_to_last_cent` | **通过** |
| 已提交轮次断点恢复 | `test_submit_is_durable_and_repeated_submit_rejected`、`test_restart_after_settlement_and_next_round` | **通过** |
| 重复提交与非法操作拦截 | `test_submit_is_durable_and_repeated_submit_rejected`、`test_invalid_allocation_rolls_back_everything` | **通过** |
| 下一轮持仓与资金守恒 | `test_all_five_rounds_and_mark_to_market_carry_forward` | **通过** |
| 多场训练互不覆盖 | `test_sessions_never_overwrite_each_other` | **通过** |
| 导出→导入→继续模拟 | `test_export_import_full_validation`、`test_import_can_resume_mid_decision` | **通过** |
| 篡改过的历史 JSON 拒绝导入 | `test_tampered_file_does_not_modify_database` | **通过** |
| Excel 兼容 CSV | `test_csv_encoding_and_columns` | **通过** |
| SQLite 全量一致性备份 | `test_sqlite_backup_is_consistent` | **通过** |
| 连续 100 场 × 5 轮模拟 | `test_100_complete_simulations_with_preserved_history` | **通过** |
| 双进程拒绝重复提交 | `test_multiple_store_instances_cannot_submit_twice` | **通过** |
| GUI 冒烟测试 | `test_gui_smoke.py` | **当前环境缺 PySide6，仅可在安装依赖的工作流中验证** |
| Windows x64 打包启动 | GitHub Actions + `--self-test` | **待 Windows 构建运行** |
| macOS Intel 打包启动 | GitHub Actions + `--self-test` | **待 Intel 构建运行** |
| macOS Apple Silicon 打包启动 | GitHub Actions + `--self-test` | **待 ARM 构建运行** |
| 真机 UI 视觉与操作验收 | 人工测试 | **待 Windows/Mac 真机验证** |
| macOS 签名/公证 | Developer ID + notarization | **未完成** |
| 与真实 AmplifyME 规则一致 | 核对官方赛制文档 | **缺官方细则，尚不可验收** |

## 人工验收步骤（分别在 Windows 和 macOS 进行）

- [ ] 解压安装包后，不装 Python，直接双击运行。
- [ ] 新建场次，抽取事件，选择等权，提交轮次，核对收益与复盘。
- [ ] 修改金额到小数后6位，确认金额有分级精度。
- [ ] 配置合计多/少1分时，提交按钮应不可用。
- [ ] 输入非法文本、负数、超过精度时不得结算。
- [ ] 结算后强制结束进程再打开：已提交轮次完整，未重复结算。
- [ ] 在编辑草稿并停顿约1秒后强制退出重开：草稿可恢复。
- [ ] 结算后的“现金补齐”等预设按钮不可使用。
- [ ] 连续完成五轮，确认期末净值等于所有持仓市值之和。
- [ ] 建立另一场训练，之前的档案可随时打开且不被覆盖。
- [ ] 使用相同种子对比训练，市场情景顺序一致。
- [ ] 导出 JSON / CSV，导入 JSON 后可以继续剩余轮次。
- [ ] 备份全库到另一位置，在独立环境恢复并核对所有场次。
- [ ] 更改窗口大小，所有按钮和表格可访问，无文本遮挡。

## 已知产品边界

1. 训练内容是队友原型模型，不是港大/AmplifyME 正式比赛复制品。
2. 数据只存在本机；数据库事务降低异常退出造成的已提交数据丢失风险，但不能抵御磁盘损坏、用户删除和所有硬件故障。
3. 草稿是输入停止 350 ms 后自动保存，不是每按键同步落盘。
4. 原生 Windows/Mac 安装包尚未在当前运行环境中构建与验收，所以本次源码交付不应被宣称为“全部完成验收的开箱即用原生程序”。
5. 第三方开源项目仅作为架构参考；此仓库核心计算及数据库实现是重新编写的代码。
