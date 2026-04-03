from __future__ import annotations

from automation.feishu_notifier import build_success_payload


def test_feishu_notifier_builds_success_payload() -> None:
    payload = build_success_payload(
        mailbox_address="chenduanxiwei@163.com",
        message_count=12,
        downloaded_count=9,
        moved_count=7,
        duplicate_count=1,
        review_required_count=1,
        error_count=0,
        report_paths=["D:/发票管理/导出报表/发票台账_202604.xlsx"],
    )

    assert payload["msg_type"] == "text"
    assert "邮件 12 封" in payload["content"]["text"]
    assert "新增发票 7 张" in payload["content"]["text"]
