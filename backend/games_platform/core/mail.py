"""Transactional email delivery (SMTP, or logged to the console in development)."""

from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 20
IMPLICIT_TLS_PORT = 465
DEFAULT_MAIL_FROM = "games@jakob-r.de"


class MailError(Exception):
    pass


def _send_smtp(message: EmailMessage) -> None:
    host = os.getenv("SMTP_HOST", "localhost")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    context = ssl.create_default_context()
    if port == IMPLICIT_TLS_PORT:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=SMTP_TIMEOUT_SECONDS) as server:
            if username:
                server.login(username, password)
            server.send_message(message)
        return
    with smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT_SECONDS) as server:
        server.starttls(context=context)
        if username:
            server.login(username, password)
        server.send_message(message)


async def send_email(*, to: str, subject: str, body: str) -> None:
    """Send a plain-text email. `AUTH_MAIL_BACKEND=console` (default) only logs it."""
    if os.getenv("AUTH_MAIL_BACKEND", "console") != "smtp":
        logger.info("Email to %s | %s\n%s", to, subject, body)
        return
    sender = os.getenv("AUTH_MAIL_FROM", DEFAULT_MAIL_FROM)
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    message["Date"] = formatdate(usegmt=True)
    _, addr = parseaddr(sender)
    message["Message-ID"] = make_msgid(
        domain=addr.rsplit("@", 1)[-1] if "@" in addr else "localhost"
    )
    message.set_content(body)
    try:
        await asyncio.to_thread(_send_smtp, message)
    except (OSError, smtplib.SMTPException) as e:
        logger.error("SMTP send failed: %s", repr(e))
        raise MailError("Could not send email") from e
