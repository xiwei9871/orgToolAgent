"""Typed application configuration models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from config.defaults import (
    DEFAULT_AUTOMATION_CONFIG,
    DEFAULT_DESKTOP_CONFIG,
    DEFAULT_GENERAL_CONFIG,
    DEFAULT_INVOICE_CONFIG,
)


@dataclass(slots=True)
class GeneralConfig:
    """General cross-module behavior flags."""

    archive_root_name: str = DEFAULT_GENERAL_CONFIG["archive_root_name"]
    desktop_path: str = DEFAULT_GENERAL_CONFIG["desktop_path"]
    process_shortcuts: bool = DEFAULT_GENERAL_CONFIG["process_shortcuts"]
    process_folders: bool = DEFAULT_GENERAL_CONFIG["process_folders"]
    move_folders: bool = DEFAULT_GENERAL_CONFIG["move_folders"]
    whitelist_names: list[str] = field(default_factory=list)
    whitelist_extensions: list[str] = field(default_factory=list)
    low_confidence_threshold: float = DEFAULT_GENERAL_CONFIG["low_confidence_threshold"]
    enable_paper_subcategory: bool = DEFAULT_GENERAL_CONFIG[
        "enable_paper_subcategory"
    ]
    skip_hidden_files: bool = DEFAULT_GENERAL_CONFIG["skip_hidden_files"]
    skip_system_files: bool = DEFAULT_GENERAL_CONFIG["skip_system_files"]


@dataclass(slots=True)
class DesktopConfig:
    """Desktop organizer-specific configuration."""

    categories: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_DESKTOP_CONFIG["categories"])
    )


@dataclass(slots=True)
class InvoiceConfig:
    """Invoice module-specific configuration."""

    root_dir: str = DEFAULT_INVOICE_CONFIG["root_dir"]
    pending_dir_name: str = DEFAULT_INVOICE_CONFIG["pending_dir_name"]
    monthly_dir_name: str = DEFAULT_INVOICE_CONFIG["monthly_dir_name"]
    duplicate_dir_name: str = DEFAULT_INVOICE_CONFIG["duplicate_dir_name"]
    report_dir_name: str = DEFAULT_INVOICE_CONFIG["report_dir_name"]
    log_dir_name: str = DEFAULT_INVOICE_CONFIG["log_dir_name"]
    metadata_dir_name: str = DEFAULT_INVOICE_CONFIG["metadata_dir_name"]
    move_strong_duplicates: bool = DEFAULT_INVOICE_CONFIG["move_strong_duplicates"]
    mark_suspected_duplicates: bool = DEFAULT_INVOICE_CONFIG[
        "mark_suspected_duplicates"
    ]
    hash_algorithm: str = DEFAULT_INVOICE_CONFIG["hash_algorithm"]
    excel_name_pattern: str = DEFAULT_INVOICE_CONFIG["excel_name_pattern"]
    month_folder_pattern: str = DEFAULT_INVOICE_CONFIG["month_folder_pattern"]


@dataclass(slots=True)
class AutomationConfig:
    """Automation-specific configuration."""

    enabled: bool = DEFAULT_AUTOMATION_CONFIG["enabled"]
    mailbox_address: str = DEFAULT_AUTOMATION_CONFIG["mailbox_address"]
    imap_host: str = DEFAULT_AUTOMATION_CONFIG["imap_host"]
    imap_port: int = DEFAULT_AUTOMATION_CONFIG["imap_port"]
    imap_folder: str = DEFAULT_AUTOMATION_CONFIG["imap_folder"]
    attachment_extensions: list[str] = field(
        default_factory=lambda: list(DEFAULT_AUTOMATION_CONFIG["attachment_extensions"])
    )
    attachment_size_limit_mb: int = DEFAULT_AUTOMATION_CONFIG["attachment_size_limit_mb"]
    mail_password_env_var: str = DEFAULT_AUTOMATION_CONFIG["mail_password_env_var"]
    feishu_webhook_env_var: str = DEFAULT_AUTOMATION_CONFIG["feishu_webhook_env_var"]
    lookback_days: int = DEFAULT_AUTOMATION_CONFIG["lookback_days"]


@dataclass(slots=True)
class AppConfig:
    """Root application configuration."""

    general: GeneralConfig = field(default_factory=GeneralConfig)
    desktop: DesktopConfig = field(default_factory=DesktopConfig)
    invoice: InvoiceConfig = field(default_factory=InvoiceConfig)
    automation: AutomationConfig = field(default_factory=AutomationConfig)

    def to_dict(self) -> dict[str, object]:
        """Convert the configuration tree into JSON-serializable data."""
        return asdict(self)
