# Feishu Invoice Automation Design

**Date:** 2026-04-02

**Status:** Approved for planning

## Goal

Build a Windows-hosted weekly invoice automation flow that:

1. Connects to `chenduanxiwei@163.com`
2. Pulls new PDF invoice attachments every Saturday
3. Places attachments into the existing invoice pending directory
4. Reuses the current invoice parsing, deduplication, archive, and Excel ledger pipeline
5. Sends success or failure summaries to a Feishu bot

The first version is intentionally local-first. The Feishu bot is used for notification and optional future triggering, while the actual job runs on a fixed Windows machine through Task Scheduler.

## Why This Approach

The current repository already contains a usable invoice processing core:

- `services/invoice_service.py` orchestrates scanning, parsing, deduplication, archive execution, metadata updates, and report export.
- `invoice/` contains the domain modules for PDF extraction, parsing, deduplication, and monthly archive planning.
- `config/schema.py` and `utils/paths.py` already define the application's runtime and configuration model.

Because the user still needs to manually submit monthly invoices, keeping source files, archive folders, and ledgers on the local Windows machine is the most practical first step. This avoids premature server deployment while preserving a future upgrade path.

## Scope

### In scope

- Windows scheduled execution
- IMAP-based mailbox access for `163.com`
- Pulling new PDF attachments from `INBOX`
- Temporary attachment download and deduplicated movement into the existing pending directory
- Reuse of the current invoice pipeline
- Feishu bot summary and alert messages
- Lightweight local state tracking for idempotency
- Automated tests for the mail and orchestration flow

### Out of scope for v1

- Exchange or POP3 support
- Non-PDF invoice formats
- Cloud deployment
- Complex workflow states such as submitted or reimbursed
- Manual duplicate review inside Feishu
- Chat-driven reconfiguration from the Feishu bot

## Target Architecture

The solution should extend the current desktop tool with four backend-oriented components:

1. `mail_fetcher`
   Connect to IMAP, list candidate messages, download PDF attachments, and record message and attachment identity for deduplication.

2. `job_runner`
   Provide a non-GUI entrypoint for the weekly job. This module coordinates state loading, mailbox fetch, pending-file staging, invoice pipeline execution, and notification.

3. `feishu_notifier`
   Send compact success and failure messages to a Feishu bot webhook.

4. `automation_state`
   Persist lightweight execution state such as last successful run time, processed message IDs, and downloaded attachment hashes.

The existing `InvoiceService` remains the business core for invoice management. New automation code sits around it rather than inside the GUI flow.

## Execution Flow

1. Windows Task Scheduler launches the weekly runner on Saturday.
2. The runner loads runtime config and automation state.
3. The mail fetcher connects to the mailbox with IMAP SSL.
4. The fetcher lists messages received after `last_success_at`.
5. The fetcher downloads PDF attachments into a temporary inbox directory.
6. Downloaded files are renamed safely if needed and moved into the configured pending directory.
7. The runner calls the existing invoice pipeline to scan pending files and build a preview.
8. The runner executes the preview through `InvoiceService.execute_preview`.
9. The runner updates automation state only after the job reaches a successful or intentionally partial-success terminal state.
10. A Feishu summary or alert is sent with counts, output paths, and any review-required items.

## Idempotency Strategy

Two layers are required.

### Mail-level idempotency

The automation layer records:

- IMAP UID when available
- `Message-ID` when available
- attachment file name
- attachment size
- attachment content hash

Rules:

- Previously completed message UIDs are skipped.
- If the same attachment content hash appears again, it is not staged into pending a second time.
- State is advanced only after the current run reaches a completed state. A failed run must not move the success cursor forward.

### Invoice-level idempotency

The existing invoice flow already provides:

- file-hash duplicate detection
- business duplicate detection using invoice fields
- separate handling for strong duplicates and review-required items

This means even if the mailbox layer encounters overlap, the invoice layer still protects the ledger and archive.

## Runtime Storage

The existing runtime root from `RuntimePaths` should be extended with automation-specific locations:

- automation logs
- automation state JSON
- temporary mail inbox directory

All runtime writes should continue under `%APPDATA%/DesktopSmartOrganizer/` with fallback to the existing workspace runtime strategy.

## Configuration Design

The current app config should be extended with an automation or mail section that includes:

- mailbox address
- IMAP host and port
- mailbox folder name, default `INBOX`
- attachment suffix allowlist, default `[".pdf"]`
- attachment size limit
- environment variable name for the mailbox app password
- Feishu webhook URL or environment variable name
- job lookback behavior and optional safety buffer

Secrets must not be stored in repository defaults. The first version should read them from environment variables on the Windows machine.

## Error Handling

The workflow should be resilient and restartable.

### Mail login failure

- mark the run as failed
- keep state unchanged
- send a Feishu alert if possible

### Attachment download failure

- record the failed message and attachment
- continue processing other attachments
- report failure count in the summary

### Invoice parse or archive failure

- preserve the pending file for manual inspection
- allow the rest of the batch to continue
- report per-file failure counts

### Excel export failure

- return `partial_success`
- avoid rolling back successful file moves
- notify the user that ledger output needs attention

### Feishu notification failure

- do not fail the main invoice job
- log the notification error locally

## Feishu Bot Responsibilities

For v1 the Feishu bot is intentionally narrow:

- send a success summary after each run
- send an alert when the run fails or partially fails

The bot does not manage files, manual duplicate review, or reimbursement workflow state in v1.

Recommended success message fields:

- scanned message count
- downloaded attachment count
- newly archived invoice count
- strong duplicate count
- review-required count
- failure count
- monthly report path
- archive root path

## Testing Strategy

The repository should add tests for:

- IMAP message and attachment filtering
- mail-layer idempotency
- state-file update behavior on success vs failure
- orchestration from downloaded attachment to invoice service execution
- Feishu payload formatting

The design should preserve the current unit-testable structure by introducing adapter-style services instead of embedding network code in GUI modules.

## Rollout Plan

Implementation should happen in four phases:

1. Add a non-GUI weekly runner that can execute the existing invoice pipeline locally.
2. Add IMAP attachment download and local automation state.
3. Add Feishu summary and alert delivery.
4. Wire the runner into Windows Task Scheduler and document deployment steps.

## Future Evolution

This design intentionally keeps the automation code separable from the desktop GUI so it can later migrate to a server or NAS. If the workflow is later moved off the local machine, the reusable units should remain:

- mail fetcher
- orchestration runner
- invoice pipeline
- notifier
- state store

That keeps v1 pragmatic without blocking a future service deployment.
