"""Weekly invoice orchestration for mailbox downloads and invoice processing."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Mapping

from automation.feishu_notifier import (
    FeishuNotifier,
    build_failure_payload,
    build_success_payload,
)
from automation.mail_fetcher import MailFetcher, MailFetchResult
from automation.state_store import AutomationState, AutomationStateStore
from config.schema import AppConfig
from core.conflict_resolver import resolve_conflict_path
from services.invoice_service import InvoiceService
from utils.paths import RuntimePaths


@dataclass(slots=True)
class WeeklyInvoiceJobResult:
    """Summary of one weekly invoice automation run."""

    status: str
    message_count: int = 0
    downloaded_count: int = 0
    moved_count: int = 0
    duplicate_count: int = 0
    review_required_count: int = 0
    error_count: int = 0
    report_paths: list[str] = field(default_factory=list)
    task_summary: dict[str, object] = field(default_factory=dict)
    mail_summary: dict[str, int] = field(default_factory=dict)
    error_message: str = ""


class WeeklyInvoiceJobService:
    """Run the mailbox-to-invoice weekly automation pipeline."""

    def __init__(
        self,
        *,
        runtime_paths: RuntimePaths,
        config: AppConfig,
        mail_fetcher: MailFetcher,
        invoice_service: InvoiceService,
        notifier: FeishuNotifier | object,
        state_store: AutomationStateStore | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.runtime_paths = runtime_paths
        self.config = config
        self.mail_fetcher = mail_fetcher
        self.invoice_service = invoice_service
        self.notifier = notifier
        self.state_store = state_store or AutomationStateStore(
            runtime_paths.automation_state_file
        )
        self._environ = os.environ if environ is None else environ

    def run(self) -> WeeklyInvoiceJobResult:
        """Execute the weekly mailbox and invoice workflow."""
        started_at = datetime.now().isoformat(timespec="seconds")
        state = self.state_store.load()
        mail_result: MailFetchResult | None = None
        preview_items = []
        task = None
        report_paths: list[str] = []

        try:
            password = self._load_mail_password()
            mail_result = self.mail_fetcher.fetch_new_attachments(
                mailbox_address=self.config.automation.mailbox_address,
                password=password,
                host=self.config.automation.imap_host,
                port=self.config.automation.imap_port,
                folder=self.config.automation.imap_folder,
                last_success_at=state.last_success_at or None,
                download_dir=self.runtime_paths.mail_inbox_dir,
                allowed_extensions=list(self.config.automation.attachment_extensions),
                known_attachment_hashes=set(state.downloaded_attachment_hashes),
                size_limit_mb=self.config.automation.attachment_size_limit_mb,
                lookback_days=self.config.automation.lookback_days,
            )
            self._stage_downloads(mail_result)

            pending_files = self.invoice_service.scan_pending(self.config.invoice)
            preview_items = self.invoice_service.build_preview(
                pending_files, self.config.invoice
            )
            task = self.invoice_service.execute_preview(
                preview_items, self.config.invoice
            )
            report_paths = self._collect_report_paths(preview_items)

            return self._finalize_success(
                started_at=started_at,
                state=state,
                mail_result=mail_result,
                preview_items=preview_items,
                task=task,
                report_paths=report_paths,
            )
        except Exception as exc:
            return self._finalize_failure(
                started_at=started_at,
                state=state,
                mail_result=mail_result,
                preview_items=preview_items,
                task=task,
                report_paths=report_paths,
                error_message=str(exc),
            )

    def _load_mail_password(self) -> str:
        env_name = self.config.automation.mail_password_env_var
        password = self._environ.get(env_name, "")
        if not password:
            raise RuntimeError(f"Missing mailbox password env var: {env_name}")
        return password

    def _stage_downloads(self, mail_result: MailFetchResult) -> None:
        pending_dir = Path(self.config.invoice.root_dir) / self.config.invoice.pending_dir_name
        pending_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_paths.mail_inbox_dir.mkdir(parents=True, exist_ok=True)

        for attachment in mail_result.downloaded_attachments:
            source = Path(attachment.path)
            target = resolve_conflict_path(pending_dir / source.name)
            shutil.move(str(source), str(target))
            attachment.path = target

    def _collect_report_paths(self, preview_items: list[object]) -> list[str]:
        paths: list[str] = []
        seen: set[str] = set()
        for item in preview_items:
            report_path = getattr(item, "report_path", "")
            if not report_path:
                continue
            text = str(report_path)
            if text in seen:
                continue
            seen.add(text)
            paths.append(text)
        return paths

    def _finalize_success(
        self,
        *,
        started_at: str,
        state: AutomationState,
        mail_result: MailFetchResult,
        preview_items: list[object],
        task: object,
        report_paths: list[str],
    ) -> WeeklyInvoiceJobResult:
        task_summary = dict(getattr(task, "summary", {}))
        message_count = mail_result.scanned_message_count
        downloaded_count = mail_result.downloaded_count
        invoice_duplicate_count = sum(
            1
            for item in preview_items
            if getattr(item, "skip_reason", "") == "strong_duplicate"
        )
        review_required_count = sum(
            1
            for item in preview_items
            if getattr(item, "skip_reason", "") == "review_required"
        )
        moved_count = int(task_summary.get("moved", 0))
        error_count = int(task_summary.get("errors", 0)) + mail_result.failed_attachment_count
        duplicate_count = mail_result.skipped_duplicate_count + invoice_duplicate_count
        status = str(getattr(task, "status", "success"))

        summary = {
            "message_count": message_count,
            "downloaded_count": downloaded_count,
            "moved_count": moved_count,
            "duplicate_count": duplicate_count,
            "review_required_count": review_required_count,
            "error_count": error_count,
            "invoice_status": status,
        }
        summary.update(task_summary)
        summary["mail_duplicates"] = mail_result.skipped_duplicate_count
        summary["mail_errors"] = mail_result.failed_attachment_count
        summary["mail_scanned"] = mail_result.scanned_message_count

        state.last_attempt_at = started_at
        state.last_success_at = started_at
        state.processed_message_ids = list(mail_result.processed_message_ids)
        state.downloaded_attachment_hashes = list(
            mail_result.downloaded_attachment_hashes
        )
        state.last_task_summary = summary
        self.state_store.save(state)

        payload = (
            build_success_payload(
                mailbox_address=self.config.automation.mailbox_address,
                message_count=message_count,
                downloaded_count=downloaded_count,
                moved_count=moved_count,
                duplicate_count=duplicate_count,
                review_required_count=review_required_count,
                error_count=error_count,
                report_paths=report_paths,
            )
            if status == "success"
            else build_failure_payload(
                mailbox_address=self.config.automation.mailbox_address,
                message_count=message_count,
                downloaded_count=downloaded_count,
                moved_count=moved_count,
                duplicate_count=duplicate_count,
                review_required_count=review_required_count,
                error_count=error_count,
                report_paths=report_paths,
                error_message="invoice task returned partial_success",
            )
        )
        self._send_notification(payload)

        return WeeklyInvoiceJobResult(
            status=status,
            message_count=message_count,
            downloaded_count=downloaded_count,
            moved_count=moved_count,
            duplicate_count=duplicate_count,
            review_required_count=review_required_count,
            error_count=error_count,
            report_paths=report_paths,
            task_summary=summary,
            mail_summary={
                "scanned": mail_result.scanned_message_count,
                "downloaded": mail_result.downloaded_count,
                "duplicates": mail_result.skipped_duplicate_count,
                "errors": mail_result.failed_attachment_count,
            },
        )

    def _finalize_failure(
        self,
        *,
        started_at: str,
        state: AutomationState,
        mail_result: MailFetchResult | None,
        preview_items: list[object],
        task: object | None,
        report_paths: list[str],
        error_message: str,
    ) -> WeeklyInvoiceJobResult:
        mail_result = mail_result or MailFetchResult()
        task_summary = dict(getattr(task, "summary", {}))
        message_count = mail_result.scanned_message_count
        downloaded_count = mail_result.downloaded_count
        invoice_duplicate_count = sum(
            1
            for item in preview_items
            if getattr(item, "skip_reason", "") == "strong_duplicate"
        )
        review_required_count = sum(
            1
            for item in preview_items
            if getattr(item, "skip_reason", "") == "review_required"
        )
        moved_count = int(task_summary.get("moved", 0))
        error_count = int(task_summary.get("errors", 0)) + mail_result.failed_attachment_count
        duplicate_count = mail_result.skipped_duplicate_count + invoice_duplicate_count

        summary = {
            "message_count": message_count,
            "downloaded_count": downloaded_count,
            "moved_count": moved_count,
            "duplicate_count": duplicate_count,
            "review_required_count": review_required_count,
            "error_count": error_count,
            "invoice_status": "failure",
            "error_message": error_message,
        }
        summary.update(task_summary)
        summary["mail_duplicates"] = mail_result.skipped_duplicate_count
        summary["mail_errors"] = mail_result.failed_attachment_count
        summary["mail_scanned"] = mail_result.scanned_message_count

        state.last_attempt_at = started_at
        state.processed_message_ids = list(mail_result.processed_message_ids)
        state.downloaded_attachment_hashes = list(
            mail_result.downloaded_attachment_hashes
        )
        state.last_task_summary = summary
        self.state_store.save(state)

        payload = build_failure_payload(
            mailbox_address=self.config.automation.mailbox_address,
            message_count=message_count,
            downloaded_count=downloaded_count,
            moved_count=moved_count,
            duplicate_count=duplicate_count,
            review_required_count=review_required_count,
            error_count=error_count,
            report_paths=report_paths,
            error_message=error_message,
        )
        self._send_notification(payload)

        return WeeklyInvoiceJobResult(
            status="failure",
            message_count=message_count,
            downloaded_count=downloaded_count,
            moved_count=moved_count,
            duplicate_count=duplicate_count,
            review_required_count=review_required_count,
            error_count=error_count,
            report_paths=report_paths,
            task_summary=summary,
            mail_summary={
                "scanned": mail_result.scanned_message_count,
                "downloaded": mail_result.downloaded_count,
                "duplicates": mail_result.skipped_duplicate_count,
                "errors": mail_result.failed_attachment_count,
            },
            error_message=error_message,
        )

    def _send_notification(self, payload: dict[str, object]) -> None:
        try:
            sender = getattr(self.notifier, "send", None)
            if sender is None:
                return
            sender(payload)
        except Exception:
            return
