from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from automation.state_store import AutomationState, AutomationStateStore
from config.schema import AppConfig, AutomationConfig, InvoiceConfig
from services.weekly_invoice_job_service import WeeklyInvoiceJobService
from utils.paths import RuntimePaths


def build_runtime_paths(tmp_path: Path) -> RuntimePaths:
    runtime_root = tmp_path / "runtime"
    paths = RuntimePaths(
        root=runtime_root,
        config_file=runtime_root / "config.json",
        logs_dir=runtime_root / "logs",
        tasks_dir=runtime_root / "tasks",
        invoice_metadata_dir=runtime_root / "invoice_metadata",
    )
    paths.ensure_dirs()
    return paths


def build_app_config(tmp_path: Path) -> AppConfig:
    invoice_root = tmp_path / "invoice_root"
    return AppConfig(
        invoice=InvoiceConfig(
            root_dir=str(invoice_root),
            pending_dir_name="pending",
            report_dir_name="reports",
        ),
        automation=AutomationConfig(
            mailbox_address="chenduanxiwei@163.com",
            mail_password_env_var="DSO_MAIL_APP_PASSWORD",
            feishu_webhook_env_var="DSO_FEISHU_WEBHOOK",
            lookback_days=3,
        ),
    )


@dataclass
class FakeMailFetcher:
    downloaded_count: int = 2
    message_count: int = 2
    raise_error: Exception | None = None

    def fetch_new_attachments(self, **kwargs):
        if self.raise_error is not None:
            raise self.raise_error

        download_dir: Path = kwargs["download_dir"]
        download_dir.mkdir(parents=True, exist_ok=True)
        attachments = []
        for index in range(self.downloaded_count):
            path = download_dir / f"mail-{index + 1}.pdf"
            path.write_text(f"pdf-{index + 1}", encoding="utf-8")
            attachments.append(
                SimpleNamespace(
                    message_id=f"100{index + 1}",
                    filename=path.name,
                    path=path,
                    attachment_hash=f"hash-{index + 1}",
                    size_bytes=10,
                )
            )

        return SimpleNamespace(
            scanned_message_count=self.message_count,
            downloaded_count=self.downloaded_count,
            skipped_duplicate_count=0,
            failed_attachment_count=0,
            processed_message_ids=[f"100{index + 1}" for index in range(self.message_count)],
            downloaded_attachments=attachments,
            downloaded_attachment_hashes=[f"hash-{index + 1}" for index in range(self.downloaded_count)],
        )


@dataclass
class FakeInvoiceService:
    task_status: str = "success"
    task_errors: int = 0

    def scan_pending(self, config):
        pending_dir = Path(config.root_dir) / config.pending_dir_name
        return sorted(pending_dir.glob("*.pdf"))

    def build_preview(self, pending_files, config):
        preview = []
        for path in pending_files:
            preview.append(
                SimpleNamespace(
                    source_path=str(path),
                    target_path=str(Path(config.root_dir) / "monthly" / path.name),
                    is_skipped=False,
                    skip_reason="",
                    duplicate_status="新发票",
                    report_path=str(Path(config.root_dir) / config.report_dir_name / "invoice.xlsx"),
                    month_key="202604",
                )
            )
        return preview

    def execute_preview(self, preview, config):
        moved = len([item for item in preview if not item.is_skipped])
        return SimpleNamespace(
            status=self.task_status,
            summary={"moved": moved, "skipped": 0, "errors": self.task_errors},
        )


@dataclass
class FakeNotifier:
    payloads: list[dict[str, object]]

    def __init__(self) -> None:
        self.payloads = []

    def send(self, payload: dict[str, object]) -> None:
        self.payloads.append(payload)


def test_weekly_job_service_runs_mail_to_invoice_pipeline(tmp_path: Path) -> None:
    runtime_paths = build_runtime_paths(tmp_path)
    config = build_app_config(tmp_path)
    state_store = AutomationStateStore(runtime_paths.automation_state_file)
    state_store.save(
        AutomationState(
            last_success_at="2026-04-02T09:05:00",
            downloaded_attachment_hashes=["existing-hash"],
        )
    )

    service = WeeklyInvoiceJobService(
        runtime_paths=runtime_paths,
        config=config,
        mail_fetcher=FakeMailFetcher(downloaded_count=2, message_count=2),
        invoice_service=FakeInvoiceService(task_status="success"),
        notifier=FakeNotifier(),
        state_store=state_store,
        environ={
            "DSO_MAIL_APP_PASSWORD": "secret",
            "DSO_FEISHU_WEBHOOK": "https://example.invalid/webhook",
        },
    )

    result = service.run()

    assert result.status == "success"
    assert result.downloaded_count == 2
    assert result.task_summary["moved"] == 2
    assert result.task_summary["errors"] == 0
    assert len(service.notifier.payloads) == 1
    assert state_store.load().last_success_at != ""


def test_weekly_job_service_leaves_last_success_at_unchanged_on_mail_failure(
    tmp_path: Path,
) -> None:
    runtime_paths = build_runtime_paths(tmp_path)
    config = build_app_config(tmp_path)
    state_store = AutomationStateStore(runtime_paths.automation_state_file)
    state_store.save(
        AutomationState(last_success_at="2026-04-02T09:05:00")
    )

    service = WeeklyInvoiceJobService(
        runtime_paths=runtime_paths,
        config=config,
        mail_fetcher=FakeMailFetcher(raise_error=RuntimeError("imap down")),
        invoice_service=FakeInvoiceService(),
        notifier=FakeNotifier(),
        state_store=state_store,
        environ={
            "DSO_MAIL_APP_PASSWORD": "secret",
            "DSO_FEISHU_WEBHOOK": "https://example.invalid/webhook",
        },
    )

    result = service.run()

    assert result.status == "failure"
    assert state_store.load().last_success_at == "2026-04-02T09:05:00"
    assert len(service.notifier.payloads) == 1


def test_weekly_job_service_reports_partial_success_summary(
    tmp_path: Path,
) -> None:
    runtime_paths = build_runtime_paths(tmp_path)
    config = build_app_config(tmp_path)

    service = WeeklyInvoiceJobService(
        runtime_paths=runtime_paths,
        config=config,
        mail_fetcher=FakeMailFetcher(downloaded_count=1, message_count=1),
        invoice_service=FakeInvoiceService(task_status="partial_success", task_errors=1),
        notifier=FakeNotifier(),
        state_store=AutomationStateStore(runtime_paths.automation_state_file),
        environ={
            "DSO_MAIL_APP_PASSWORD": "secret",
            "DSO_FEISHU_WEBHOOK": "https://example.invalid/webhook",
        },
    )

    result = service.run()

    assert result.status == "partial_success"
    assert result.task_summary["moved"] == 1
    assert result.task_summary["errors"] == 1
    assert len(service.notifier.payloads) == 1
