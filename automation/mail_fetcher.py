"""IMAP attachment fetching helpers for automation jobs."""

from __future__ import annotations

import imaplib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email import message_from_bytes
from email.message import Message
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable, Protocol

from utils.file_hash import compute_file_hash


class _ImapClient(Protocol):
    def login(self, mailbox_address: str, password: str) -> object: ...

    def select(self, folder: str) -> object: ...

    def search(self, charset: str | None, *criteria: str) -> object: ...

    def fetch(self, message_id: str, parts: str) -> object: ...

    def close(self) -> object: ...

    def logout(self) -> object: ...


@dataclass(slots=True)
class FetchedAttachment:
    """A single attachment downloaded from IMAP."""

    message_id: str
    filename: str
    path: Path
    attachment_hash: str
    size_bytes: int


@dataclass(slots=True)
class MailFetchResult:
    """Summary of a mailbox scan."""

    scanned_message_count: int = 0
    downloaded_count: int = 0
    skipped_duplicate_count: int = 0
    failed_attachment_count: int = 0
    processed_message_ids: list[str] = field(default_factory=list)
    downloaded_attachments: list[FetchedAttachment] = field(default_factory=list)
    downloaded_attachment_hashes: list[str] = field(default_factory=list)

    @property
    def downloaded_files(self) -> list[Path]:
        return [attachment.path for attachment in self.downloaded_attachments]


class MailFetcher:
    """Fetch PDF attachments from an IMAP mailbox."""

    def __init__(
        self, client_factory: Callable[[], _ImapClient] | None = None
    ) -> None:
        self._client_factory = client_factory

    def fetch_new_attachments(
        self,
        *,
        mailbox_address: str,
        password: str,
        host: str,
        port: int,
        folder: str,
        last_success_at: str | None,
        download_dir: Path,
        allowed_extensions: list[str],
        known_attachment_hashes: set[str],
        size_limit_mb: int,
        lookback_days: int = 3,
    ) -> MailFetchResult:
        """Download new attachments from the mailbox."""
        download_dir.mkdir(parents=True, exist_ok=True)
        result = MailFetchResult()
        cutoff = self._parse_cursor(last_success_at)
        search_since = (cutoff - timedelta(days=lookback_days)) if cutoff else (
            datetime.now(UTC) - timedelta(days=lookback_days)
        )
        search_since_token = search_since.strftime("%d-%b-%Y")
        allowed_suffixes = {suffix.lower() for suffix in allowed_extensions}
        seen_hashes = set(known_attachment_hashes)

        client = self._create_client(host=host, port=port)
        try:
            client.login(mailbox_address, password)
            client.select(folder)
            search_response = client.search(None, "SINCE", search_since_token)
            message_ids = self._parse_message_ids(search_response)

            for message_id in message_ids:
                raw_message = self._fetch_message_bytes(client, message_id)
                if raw_message is None:
                    continue

                message = message_from_bytes(raw_message)
                message_date = self._parse_message_date(message)
                if cutoff and message_date and message_date <= cutoff:
                    continue

                result.scanned_message_count += 1
                result.processed_message_ids.append(message_id)
                self._download_attachments_for_message(
                    message=message,
                    message_id=message_id,
                    download_dir=download_dir,
                    allowed_suffixes=allowed_suffixes,
                    seen_hashes=seen_hashes,
                    size_limit_bytes=size_limit_mb * 1024 * 1024,
                    result=result,
                )
        finally:
            self._close_client(client)

        return result

    def _create_client(self, host: str, port: int) -> _ImapClient:
        if self._client_factory is not None:
            return self._client_factory()
        return imaplib.IMAP4_SSL(host=host, port=port)

    def _download_attachments_for_message(
        self,
        *,
        message: Message,
        message_id: str,
        download_dir: Path,
        allowed_suffixes: set[str],
        seen_hashes: set[str],
        size_limit_bytes: int,
        result: MailFetchResult,
    ) -> None:
        attachment_index = 0
        for part in message.walk():
            if part.is_multipart():
                continue

            filename = part.get_filename()
            if not filename:
                continue

            suffix = Path(filename).suffix.lower()
            if suffix not in allowed_suffixes:
                continue

            payload = part.get_payload(decode=True) or b""
            if size_limit_bytes and len(payload) > size_limit_bytes:
                continue

            attachment_index += 1
            target_path = self._unique_path(
                download_dir,
                f"{message_id}-{attachment_index}-{Path(filename).name}",
            )

            try:
                target_path.write_bytes(payload)
                attachment_hash = compute_file_hash(target_path)
            except OSError:
                result.failed_attachment_count += 1
                if target_path.exists():
                    target_path.unlink(missing_ok=True)
                continue

            if attachment_hash in seen_hashes:
                result.skipped_duplicate_count += 1
                target_path.unlink(missing_ok=True)
                continue

            seen_hashes.add(attachment_hash)
            attachment = FetchedAttachment(
                message_id=message_id,
                filename=Path(filename).name,
                path=target_path,
                attachment_hash=attachment_hash,
                size_bytes=len(payload),
            )
            result.downloaded_attachments.append(attachment)
            result.downloaded_attachment_hashes.append(attachment_hash)
            result.downloaded_count += 1

    def _fetch_message_bytes(
        self, client: _ImapClient, message_id: str
    ) -> bytes | None:
        response = client.fetch(message_id, "(RFC822)")
        if not isinstance(response, tuple) or len(response) < 2:
            return None

        payload_items = response[1]
        for item in payload_items:
            if isinstance(item, tuple) and len(item) >= 2:
                raw_message = item[1]
                if isinstance(raw_message, bytes):
                    return raw_message
        return None

    def _parse_message_ids(self, search_response: object) -> list[str]:
        if not isinstance(search_response, tuple) or len(search_response) < 2:
            return []

        payload_items = search_response[1]
        if not payload_items:
            return []

        raw_ids = payload_items[0]
        if isinstance(raw_ids, bytes):
            decoded = raw_ids.decode("ascii", errors="ignore")
        else:
            decoded = str(raw_ids)
        return [message_id for message_id in decoded.split() if message_id]

    def _parse_cursor(self, last_success_at: str | None) -> datetime | None:
        if not last_success_at:
            return None

        cursor = datetime.fromisoformat(last_success_at)
        if cursor.tzinfo is None:
            cursor = cursor.replace(tzinfo=UTC)
        return cursor.astimezone(UTC)

    def _parse_message_date(self, message: Message) -> datetime | None:
        raw_date = message.get("Date")
        if not raw_date:
            return None

        try:
            message_date = parsedate_to_datetime(raw_date)
        except (TypeError, ValueError):
            return None

        if message_date.tzinfo is None:
            message_date = message_date.replace(tzinfo=UTC)
        return message_date.astimezone(UTC)

    def _unique_path(self, directory: Path, filename: str) -> Path:
        candidate = directory / filename
        if not candidate.exists():
            return candidate

        stem = candidate.stem
        suffix = candidate.suffix
        index = 1
        while True:
            next_candidate = directory / f"{stem}-{index}{suffix}"
            if not next_candidate.exists():
                return next_candidate
            index += 1

    def _close_client(self, client: _ImapClient) -> None:
        try:
            client.close()
        except Exception:
            pass

        try:
            client.logout()
        except Exception:
            pass
