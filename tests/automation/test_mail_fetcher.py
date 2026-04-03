from __future__ import annotations

import hashlib
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

from automation.mail_fetcher import MailFetcher


def _build_message(
    subject: str,
    sent_at: str,
    attachments: list[tuple[str, bytes, str]],
) -> bytes:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = "sender@example.com"
    message["To"] = "chenduanxiwei@163.com"
    message["Date"] = sent_at
    message.set_content("invoice body")

    for filename, content, mimetype in attachments:
        maintype, subtype = mimetype.split("/", 1)
        message.add_attachment(
            content,
            maintype=maintype,
            subtype=subtype,
            filename=filename,
        )

    return message.as_bytes()


@dataclass
class FakeImapClient:
    messages: dict[str, bytes]

    def login(self, mailbox_address: str, password: str) -> tuple[str, list[bytes]]:
        self.mailbox_address = mailbox_address
        self.password = password
        return "OK", []

    def select(self, folder: str) -> tuple[str, list[bytes]]:
        self.folder = folder
        return "OK", [str(len(self.messages)).encode("ascii")]

    def search(self, charset: str | None, *criteria: str) -> tuple[str, list[bytes]]:
        self.search_charset = charset
        self.search_criteria = criteria
        return "OK", [" ".join(self.messages.keys()).encode("ascii")]

    def fetch(self, message_id: str, parts: str) -> tuple[str, list[tuple[bytes, bytes]]]:
        return "OK", [(message_id.encode("ascii"), self.messages[message_id])]

    def close(self) -> tuple[str, list[bytes]]:
        return "OK", []

    def logout(self) -> tuple[str, list[bytes]]:
        return "OK", []


def test_mail_fetcher_downloads_only_new_pdf_attachments(tmp_path: Path) -> None:
    older_message = _build_message(
        "Older",
        "Sat, 29 Mar 2026 08:30:00 +0000",
        [("old.pdf", b"older-pdf", "application/pdf")],
    )
    new_pdf = b"invoice-pdf-content"
    newer_message = _build_message(
        "Newer",
        "Sat, 29 Mar 2026 10:00:00 +0000",
        [
            ("invoice.pdf", new_pdf, "application/pdf"),
            ("notes.txt", b"not a pdf", "text/plain"),
        ],
    )
    duplicate_message = _build_message(
        "Duplicate",
        "Sat, 29 Mar 2026 11:00:00 +0000",
        [("duplicate.pdf", new_pdf, "application/pdf")],
    )

    client = FakeImapClient(
        messages={
            "1000": older_message,
            "1001": newer_message,
            "1002": duplicate_message,
        }
    )
    fetcher = MailFetcher(client_factory=lambda: client)

    result = fetcher.fetch_new_attachments(
        mailbox_address="chenduanxiwei@163.com",
        password="secret",
        host="imap.163.com",
        port=993,
        folder="INBOX",
        last_success_at="2026-03-29T09:00:00",
        download_dir=tmp_path,
        allowed_extensions=[".pdf"],
        known_attachment_hashes=set(),
        size_limit_mb=20,
    )

    assert result.scanned_message_count == 2
    assert result.downloaded_count == 1
    assert result.skipped_duplicate_count == 1
    assert result.failed_attachment_count == 0
    assert result.processed_message_ids == ["1001", "1002"]
    assert result.downloaded_attachment_hashes
    assert result.downloaded_files[0].suffix == ".pdf"
    assert result.downloaded_files[0].exists()


def test_mail_fetcher_skips_attachment_hashes_that_are_already_known(
    tmp_path: Path,
) -> None:
    message = _build_message(
        "Known",
        "Sat, 29 Mar 2026 10:00:00 +0000",
        [("invoice.pdf", b"already-seen", "application/pdf")],
    )
    client = FakeImapClient(messages={"1001": message})
    fetcher = MailFetcher(client_factory=lambda: client)

    known_hash = hashlib.sha256(b"already-seen").hexdigest()
    result = fetcher.fetch_new_attachments(
        mailbox_address="chenduanxiwei@163.com",
        password="secret",
        host="imap.163.com",
        port=993,
        folder="INBOX",
        last_success_at="2026-03-29T09:00:00",
        download_dir=tmp_path,
        allowed_extensions=[".pdf"],
        known_attachment_hashes={known_hash},
        size_limit_mb=20,
    )

    assert result.downloaded_count == 0
    assert result.downloaded_attachment_hashes == []
    assert result.skipped_duplicate_count == 1
    assert result.processed_message_ids == ["1001"]
