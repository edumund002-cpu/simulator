# GitHub 发布和打包

本目录包含 `.github/workflows/build.yml`。一旦上传到 GitHub 的 `main` 分支，GitHub Actions 会运行 Python 测试，并分别尝试构建 Windows x64、macOS Intel、macOS Apple Silicon 三个无签名桌面程序。

## 最短发布方式（由 ChatGPT 继续上传）

1. 登录 https://github.com/new ，将仓库名称设为 `wealthathon-simulator`，选择 **Private（私有）**，勾选 **Add a README file**，然后点击 **Create repository**。
2. 把新仓库链接发回 ChatGPT。连接 GitHub 的 ChatGPT 可以在已有仓库里上传源码、工作流及文档；目前其 GitHub 连接器没有“创建新仓库”的能力。
3. 上传完毕后，在新仓库点击 **Actions**，进入 **Build and test Wealthathon desktop packages**，等待三个构建任务完成。
4. 在成功工作流的 **Artifacts** 下载 `WealthathonSimulator-windows-x64`、`WealthathonSimulator-macos-intel` 或 `WealthathonSimulator-macos-apple-silicon`，解压后使用。

## 本地自主发布（可选）

如果你已安装并登录 GitHub CLI (`gh`) 和 Git，可在源码目录执行：

```bash
git init -b main
git add .
git commit -m "Initial Wealthathon practice simulator"
gh repo create wealthathon-simulator --private --source=. --remote=origin --push
```

Windows PowerShell / macOS Terminal 均可用相同命令（确保安装 Git / GitHub CLI 且完成 `gh auth login`）。

> **验收边界**：已在 Linux 环境执行了计算和持久化测试；不能仅凭 YAML 文件保证 Windows/Mac 构建、启动及用户交互通过。没有官方比赛规则，所有训练数据和评分均是非官方模型。未签名的 Mac 应用可能遇到 Gatekeeper 阻止运行。
