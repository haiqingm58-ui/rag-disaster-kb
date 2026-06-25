from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app_server.settings import settings


class EmailServiceError(RuntimeError):
    """Raised when a user-facing email cannot be sent."""


def send_registration_code(to_email: str, code: str) -> None:
    _send_verification_code(
        to_email=to_email,
        code=code,
        subject="GeoRisk 注册验证码",
        first_line=f"您的 GeoRisk 注册验证码是：{code}",
    )


def send_password_reset_code(to_email: str, code: str) -> None:
    _send_verification_code(
        to_email=to_email,
        code=code,
        subject="GeoRisk 修改密码验证码",
        first_line=f"您的 GeoRisk 修改密码验证码是：{code}",
    )


def _send_verification_code(to_email: str, code: str, subject: str, first_line: str) -> None:
    if not settings.smtp_configured:
        raise EmailServiceError("邮件服务未配置，请联系管理员检查 SMTP 设置。")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_sender
    message["To"] = to_email
    message.set_content(
        "\n".join(
            [
                "您好，",
                "",
                first_line,
                f"验证码 {settings.registration_code_expire_minutes} 分钟内有效，请勿转发给他人。",
                "",
                "如果这不是您本人操作，请忽略本邮件。",
            ]
        )
    )

    try:
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds) as server:
                _login_and_send(server, message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds) as server:
                if settings.smtp_use_tls:
                    server.starttls()
                _login_and_send(server, message)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailServiceError("验证码邮件发送失败，请稍后重试或联系管理员。") from exc


def _login_and_send(server: smtplib.SMTP, message: EmailMessage) -> None:
    if settings.smtp_username and settings.smtp_password:
        server.login(settings.smtp_username, settings.smtp_password)
    server.send_message(message)
