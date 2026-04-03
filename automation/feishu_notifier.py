"""Feishu webhook helpers for weekly automation notifications."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib import request


def _format_report_paths(report_paths: Iterable[str | Path]) -> str:
    lines = [str(path) for path in report_paths if str(path)]
    if not lines:
        return "无"
    return "\n".join(f"- {line}" for line in lines)


def build_success_text(
    *,
    mailbox_address: str,
    message_count: int,
    downloaded_count: int,
    moved_count: int,
    duplicate_count: int,
    review_required_count: int,
    error_count: int,
    report_paths: Iterable[str | Path],
) -> str:
    """Build the success text shown in the Feishu notification."""
    return "\n".join(
        [
            "每周发票自动化完成",
            f"邮箱 {mailbox_address}",
            f"邮件 {message_count} 封，下载 {downloaded_count} 个，新增发票 {moved_count} 张",
            (
                f"重复 {duplicate_count} 张，待复核 {review_required_count} 张，"
                f"错误 {error_count} 个"
            ),
            f"报表路径：\n{_format_report_paths(report_paths)}",
        ]
    )


def build_failure_text(
    *,
    mailbox_address: str,
    message_count: int = 0,
    downloaded_count: int = 0,
    moved_count: int = 0,
    duplicate_count: int = 0,
    review_required_count: int = 0,
    error_count: int = 1,
    report_paths: Iterable[str | Path] = (),
    error_message: str = "",
) -> str:
    """Build the failure text shown in the Feishu notification."""
    parts = [
        "每周发票自动化失败",
        f"邮箱 {mailbox_address}",
        f"邮件 {message_count} 封，下载 {downloaded_count} 个，新增发票 {moved_count} 张",
        (
            f"重复 {duplicate_count} 张，待复核 {review_required_count} 张，"
            f"错误 {error_count} 个"
        ),
    ]
    if error_message:
        parts.append(f"错误详情：{error_message}")
    parts.append(f"报表路径：\n{_format_report_paths(report_paths)}")
    return "\n".join(parts)


def build_success_payload(
    *,
    mailbox_address: str,
    message_count: int,
    downloaded_count: int,
    moved_count: int,
    duplicate_count: int,
    review_required_count: int,
    error_count: int,
    report_paths: Iterable[str | Path],
) -> dict[str, object]:
    """Build a Feishu text payload for a successful run."""
    return {
        "msg_type": "text",
        "content": {
            "text": build_success_text(
                mailbox_address=mailbox_address,
                message_count=message_count,
                downloaded_count=downloaded_count,
                moved_count=moved_count,
                duplicate_count=duplicate_count,
                review_required_count=review_required_count,
                error_count=error_count,
                report_paths=report_paths,
            )
        },
    }


def build_failure_payload(
    *,
    mailbox_address: str,
    message_count: int = 0,
    downloaded_count: int = 0,
    moved_count: int = 0,
    duplicate_count: int = 0,
    review_required_count: int = 0,
    error_count: int = 1,
    report_paths: Iterable[str | Path] = (),
    error_message: str = "",
) -> dict[str, object]:
    """Build a Feishu text payload for a failed run."""
    return {
        "msg_type": "text",
        "content": {
            "text": build_failure_text(
                mailbox_address=mailbox_address,
                message_count=message_count,
                downloaded_count=downloaded_count,
                moved_count=moved_count,
                duplicate_count=duplicate_count,
                review_required_count=review_required_count,
                error_count=error_count,
                report_paths=report_paths,
                error_message=error_message,
            )
        },
    }


@dataclass(slots=True)
class FeishuNotifier:
    """Send Feishu bot notifications over a webhook."""

    webhook_url: str
    timeout_seconds: int = 10
    opener: Callable[..., object] | None = None

    def send(self, payload: dict[str, object]) -> None:
        """POST a payload to the configured Feishu webhook."""
        if not self.webhook_url:
            raise ValueError("webhook_url is required")

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_obj = request.Request(
            self.webhook_url,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        opener = self.opener or request.urlopen
        with opener(request_obj, timeout=self.timeout_seconds):
            return None

    def send_success(
        self,
        *,
        mailbox_address: str,
        message_count: int,
        downloaded_count: int,
        moved_count: int,
        duplicate_count: int,
        review_required_count: int,
        error_count: int,
        report_paths: Iterable[str | Path],
    ) -> None:
        self.send(
            build_success_payload(
                mailbox_address=mailbox_address,
                message_count=message_count,
                downloaded_count=downloaded_count,
                moved_count=moved_count,
                duplicate_count=duplicate_count,
                review_required_count=review_required_count,
                error_count=error_count,
                report_paths=report_paths,
            )
        )

    def send_failure(
        self,
        *,
        mailbox_address: str,
        message_count: int = 0,
        downloaded_count: int = 0,
        moved_count: int = 0,
        duplicate_count: int = 0,
        review_required_count: int = 0,
        error_count: int = 1,
        report_paths: Iterable[str | Path] = (),
        error_message: str = "",
    ) -> None:
        self.send(
            build_failure_payload(
                mailbox_address=mailbox_address,
                message_count=message_count,
                downloaded_count=downloaded_count,
                moved_count=moved_count,
                duplicate_count=duplicate_count,
                review_required_count=review_required_count,
                error_count=error_count,
                report_paths=report_paths,
                error_message=error_message,
            )
        )
