# Windows Weekly Invoice Job

## Goal

Run the weekly invoice automation job on one fixed Windows machine so it can:

- read new PDF invoice attachments from the configured mailbox
- stage them into the local pending invoice directory
- reuse the existing invoice parsing, deduplication, archive, and Excel export flow
- send a summary to the configured Feishu webhook

## Prerequisites

- Windows machine that already owns the invoice archive root
- Python environment with project dependencies installed
- Access to the `chenduanxiwei@163.com` mailbox through a 163 app password
- A Feishu bot webhook URL

## Required Environment Variables

Set these before running the job manually or from Task Scheduler:

```powershell
$env:DSO_MAIL_APP_PASSWORD = "<163-app-password>"
$env:DSO_FEISHU_WEBHOOK = "<feishu-webhook-url>"
```

`APPDATA` is normally provided by Windows. The job uses it for runtime state, logs, and task records.

## First-Time Dry Run

From the project root:

```powershell
python .\scripts\run_weekly_invoice_job.py
```

Verify:

- the command exits with code `0`
- new PDF attachments arrive under the pending invoice directory
- processed invoices move into the monthly archive
- the Excel ledger is written under the report directory
- the Feishu webhook receives a summary

## Default Paths

If `config.invoice.root_dir` is empty, the runner defaults to:

```text
Desktop\发票管理\
```

Runtime state defaults to:

```text
%APPDATA%\DesktopSmartOrganizer\
```

Automation-specific state is stored at:

```text
%APPDATA%\DesktopSmartOrganizer\automation\
```

If `%APPDATA%` is unavailable, the application falls back to:

```text
<project_root>\.runtime\DesktopSmartOrganizer\
```

## Task Scheduler Setup

Recommended task configuration:

- Trigger: weekly, every Saturday
- Program/script: `python`
- Arguments: `C:\path\to\project\scripts\run_weekly_invoice_job.py`
- Start in: `C:\path\to\project`
- Run as: the same Windows account that owns the invoice archive root

Keep the project checkout, invoice archive root, and runtime state on the same machine.

## Failure Recovery

If the job fails:

- check the Feishu alert text first
- inspect `%APPDATA%\DesktopSmartOrganizer\` or the fallback `.runtime` directory
- inspect the pending invoice directory for files left for manual review
- rerun the command manually after fixing credentials, network access, or parsing issues

The state store preserves the previous `last_success_at` on failed runs, so retries do not silently advance the success cursor.

## Safe Reprocessing

If you must reprocess from scratch:

1. Stop the scheduled job.
2. Back up the invoice archive root and runtime state directory.
3. Review `%APPDATA%\DesktopSmartOrganizer\automation\mail_job_state.json`.
4. Reset or remove that file only if you intentionally want the mailbox fetch window to restart.
5. Run the job manually before re-enabling Task Scheduler.

## Duplicate Handling

- Mail-level duplicate attachment hashes are skipped before files reach the pending directory.
- Invoice-level duplicate rules still run inside the existing invoice pipeline.
- Review-required invoices remain visible for manual follow-up.
