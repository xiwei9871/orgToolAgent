"""Tests for the invoice workflow service."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from config.schema import InvoiceConfig
from invoice.pdf_text_extractor import PdfTextExtractor
from services.invoice_service import InvoiceService
from utils.paths import RuntimePaths


class _StaticReader:
    def __init__(self, path: str) -> None:
        name = Path(path).name
        if "partial" in name:
            self.pages = [_Page("")]
        else:
            self.pages = [
                _Page(
                    "\n".join(
                        [
                            "发票号码：12345678",
                            "开票日期：2026-03-05",
                            "发票内容：办公用品",
                            "价税合计：88.50",
                        ]
                    )
                )
            ]


class _Page:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text


def test_invoice_service_processes_new_invoice_and_updates_outputs(
    tmp_path: Path,
) -> None:
    """The invoice service should scan, preview, archive, and export a report."""
    invoice_root = tmp_path / "invoice_root"
    pending_dir = invoice_root / InvoiceConfig().pending_dir_name
    pending_dir.mkdir(parents=True)
    (pending_dir / "京东发票.pdf").write_text("fake-pdf", encoding="utf-8")

    runtime_root = tmp_path / "runtime"
    paths = RuntimePaths(
        root=runtime_root,
        config_file=runtime_root / "config.json",
        logs_dir=runtime_root / "logs",
        tasks_dir=runtime_root / "tasks",
        invoice_metadata_dir=runtime_root / "invoice_metadata",
    )
    paths.ensure_dirs()

    service = InvoiceService(
        runtime_paths=paths,
        pdf_extractor=PdfTextExtractor(reader_factory=_StaticReader),
    )
    config = InvoiceConfig(root_dir=str(invoice_root))

    scanned = service.scan_pending(config)
    preview = service.build_preview(scanned, config)
    task = service.execute_preview(preview, config)

    assert len(scanned) == 1
    assert len(preview) == 1
    assert preview[0].duplicate_status == "新发票"
    assert task.status == "success"
    assert (
        invoice_root
        / InvoiceConfig().monthly_dir_name
        / InvoiceConfig().month_folder_pattern.format(yyyymm="202603")
        / "京东发票.pdf"
    ).exists()
    assert (
        invoice_root
        / InvoiceConfig().report_dir_name
        / InvoiceConfig().excel_name_pattern.format(yyyymm="202603")
    ).exists()
    assert (paths.invoice_metadata_dir / "invoice_index.json").exists()


def test_invoice_service_skips_partial_recognition_items(tmp_path: Path) -> None:
    """Recognition-incomplete invoices should be held for review instead of moved."""
    invoice_root = tmp_path / "invoice_root"
    pending_dir = invoice_root / InvoiceConfig().pending_dir_name
    pending_dir.mkdir(parents=True)
    partial_pdf = pending_dir / "partial.pdf"
    partial_pdf.write_text("fake-pdf", encoding="utf-8")

    runtime_root = tmp_path / "runtime"
    paths = RuntimePaths(
        root=runtime_root,
        config_file=runtime_root / "config.json",
        logs_dir=runtime_root / "logs",
        tasks_dir=runtime_root / "tasks",
        invoice_metadata_dir=runtime_root / "invoice_metadata",
    )
    paths.ensure_dirs()

    service = InvoiceService(
        runtime_paths=paths,
        pdf_extractor=PdfTextExtractor(reader_factory=_StaticReader),
    )
    config = InvoiceConfig(root_dir=str(invoice_root))

    preview = service.build_preview(service.scan_pending(config), config)

    assert preview[0].is_skipped is True
    assert preview[0].duplicate_status == "待确认"
    assert partial_pdf.exists() is True


class _WeeklyJobMailFetcher:
    def fetch_new_attachments(self, **kwargs):
        download_dir: Path = kwargs["download_dir"]
        download_dir.mkdir(parents=True, exist_ok=True)

        attachment_specs = [
            ("mail-1.pdf", "alpha"),
            ("mail-2.pdf", "bravo"),
        ]
        attachments = []
        for index, (filename, content) in enumerate(attachment_specs, start=1):
            path = download_dir / filename
            path.write_text(content, encoding="utf-8")
            attachments.append(
                SimpleNamespace(
                    message_id=f"100{index}",
                    filename=filename,
                    path=path,
                    attachment_hash=f"hash-{index}",
                    size_bytes=path.stat().st_size,
                )
            )

        return SimpleNamespace(
            scanned_message_count=2,
            downloaded_count=2,
            skipped_duplicate_count=0,
            failed_attachment_count=0,
            processed_message_ids=["1001", "1002"],
            downloaded_attachments=attachments,
            downloaded_attachment_hashes=["hash-1", "hash-2"],
        )


class _WeeklyJobNotifier:
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url
        self.payloads: list[dict[str, object]] = []

    def send(self, payload: dict[str, object]) -> None:
        self.payloads.append(payload)


def test_weekly_job_runner_returns_zero_on_success(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("DSO_MAIL_APP_PASSWORD", "secret")
    monkeypatch.setenv("DSO_FEISHU_WEBHOOK", "https://example.test/webhook")

    import scripts.run_weekly_invoice_job as runner

    desktop_root = tmp_path / "Desktop"

    class _RunnerInvoiceServiceFactory:
        def __call__(self, runtime_paths: RuntimePaths) -> InvoiceService:
            return InvoiceService(
                runtime_paths,
                pdf_extractor=PdfTextExtractor(reader_factory=_StaticReader),
            )

    monkeypatch.setattr(runner, "resolve_desktop_directory", lambda: desktop_root)
    monkeypatch.setattr(runner, "MailFetcher", _WeeklyJobMailFetcher)
    monkeypatch.setattr(runner, "FeishuNotifier", _WeeklyJobNotifier)
    monkeypatch.setattr(runner, "InvoiceService", _RunnerInvoiceServiceFactory())

    exit_code = runner.main()

    invoice_root = desktop_root / "发票管理"
    invoice_config = InvoiceConfig()

    assert exit_code == 0
    assert (
        invoice_root
        / invoice_config.monthly_dir_name
        / invoice_config.month_folder_pattern.format(yyyymm="202603")
        / "mail-1.pdf"
    ).exists()
    assert (
        invoice_root
        / invoice_config.monthly_dir_name
        / invoice_config.month_folder_pattern.format(yyyymm="202603")
        / "mail-2.pdf"
    ).exists()
    assert (
        invoice_root
        / invoice_config.report_dir_name
        / invoice_config.excel_name_pattern.format(yyyymm="202603")
    ).exists()
