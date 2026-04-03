"""CLI entrypoint for the weekly invoice automation job."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from collections.abc import Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.feishu_notifier import FeishuNotifier
from automation.mail_fetcher import MailFetcher
from automation.state_store import AutomationStateStore
from config.manager import ConfigManager
from config.schema import AppConfig
from services.invoice_service import InvoiceService
from services.weekly_invoice_job_service import WeeklyInvoiceJobService
from utils.paths import RuntimePaths
from utils.windows import resolve_desktop_directory


def build_weekly_job_service(
    *,
    config: AppConfig,
    runtime_paths: RuntimePaths,
    environ: Mapping[str, str],
) -> WeeklyInvoiceJobService:
    """Construct the weekly job service with required runtime dependencies."""
    mail_password_env = config.automation.mail_password_env_var
    feishu_webhook_env = config.automation.feishu_webhook_env_var

    if not environ.get(mail_password_env, "").strip():
        raise RuntimeError(f"Missing required environment variable: {mail_password_env}")

    webhook_url = environ.get(feishu_webhook_env, "").strip()
    if not webhook_url:
        raise RuntimeError(
            f"Missing required environment variable: {feishu_webhook_env}"
        )

    if not config.invoice.root_dir.strip():
        config.invoice.root_dir = str(resolve_desktop_directory() / "发票管理")

    runtime_paths.ensure_dirs()

    return WeeklyInvoiceJobService(
        runtime_paths=runtime_paths,
        config=config,
        mail_fetcher=MailFetcher(),
        invoice_service=InvoiceService(runtime_paths),
        notifier=FeishuNotifier(webhook_url),
        state_store=AutomationStateStore(runtime_paths.automation_state_file),
        environ=environ,
    )


def main() -> int:
    """Run the weekly invoice automation job."""
    environ = os.environ

    try:
        config_manager = ConfigManager.for_app()
        runtime_paths = config_manager.paths
        config = config_manager.load()
        job_service = build_weekly_job_service(
            config=config,
            runtime_paths=runtime_paths,
            environ=environ,
        )
        result = job_service.run()
    except Exception:
        return 1

    return 0 if result.status in {"success", "partial_success"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
