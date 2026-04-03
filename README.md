# Desktop Smart Organizer

Windows 桌面整理与发票管理工具。

## 功能概览

- 桌面文件扫描、预览、整理与撤销
- 基于规则的桌面文件分类
- 发票待处理目录扫描、PDF 文本提取、解析、去重和归档
- 按月份归档发票并导出 Excel 台账
- PySide6 图形界面，包含“桌面整理”和“发票管理”两个页面
- 每周发票自动化 runner，可从邮箱拉取 PDF 附件并复用现有发票流程

## 运行环境

- Windows
- Python 3.11+

## 安装依赖

```powershell
python -m pip install -r requirements.txt
```

## 启动桌面应用

```powershell
python main.py
```

## 运行测试

```powershell
pytest -q
```

## 打包

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

或直接运行：

```powershell
python -m PyInstaller --noconfirm --onefile --windowed main.py --name DesktopSmartOrganizer
```

默认输出：

```text
dist\DesktopSmartOrganizer.exe
```

## 运行时目录

应用优先把配置、日志、任务记录和自动化状态写入：

```text
%APPDATA%\DesktopSmartOrganizer\
```

如果 `%APPDATA%` 不可写，则自动回退到：

```text
<project_root>\.runtime\DesktopSmartOrganizer\
```

## 发票目录建议

建议将发票根目录放在桌面，例如：

```text
Desktop\发票管理\
```

目录下至少包含这些子目录：

```text
发票归档_待处理\
按月份归档\
重复发票\
导出报表\
```

## Weekly Invoice Automation

仓库包含一个非 GUI 的每周发票自动化入口：

```powershell
python .\scripts\run_weekly_invoice_job.py
```

运行前需要设置环境变量：

```powershell
$env:DSO_MAIL_APP_PASSWORD = "<163-app-password>"
$env:DSO_FEISHU_WEBHOOK = "<feishu-webhook-url>"
```

说明：

- runner 必须运行在拥有发票归档根目录的同一台 Windows 机器上
- 如果 `config.invoice.root_dir` 为空，runner 默认使用 `Desktop\发票管理`
- 自动化状态默认保存在 `%APPDATA%\DesktopSmartOrganizer\automation\`

推荐的 Windows 计划任务配置：

- Trigger: every Saturday
- Action: `python C:\path\to\project\scripts\run_weekly_invoice_job.py`
- Start in: project root
- Run as: the same Windows account that owns the invoice archive root

预期结果：

- 新 PDF 发票附件会进入待处理目录
- 现有发票流程会继续执行解析、去重、归档和台账导出
- 飞书 webhook 会收到执行摘要

## 项目结构

```text
.
├── app.py / main.py
├── automation/
├── gui/
├── services/
├── core/
├── invoice/
├── classifiers/
├── config/
├── models/
├── utils/
├── tests/
└── scripts/
```

## 当前限制

- 仅支持 Windows
- 桌面整理目前只处理桌面顶层内容
- 文件夹默认只做预览，不直接移动
- 发票处理当前优先支持 PDF
- OCR 相关流程保留扩展接口，但默认仍以可解析 PDF 为主
