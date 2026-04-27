from pathlib import Path

from fastapi_mail import ConnectionConfig, MessageSchema, MessageType, FastMail
from pydantic import NameEmail

from src.config import settings

# Directory containing Jinja2 HTML templates
TEMPLATES_DIR = Path(__file__).parent / "templates"

def _get_mail_config() -> ConnectionConfig:
    return ConnectionConfig(
        MAIL_USERNAME=settings.mail_username,
        MAIL_PASSWORD=settings.mail_password,
        MAIL_FROM=settings.mail_from,
        MAIL_FROM_NAME=settings.mail_from_name,
        MAIL_PORT=settings.mail_port,
        MAIL_SERVER=settings.mail_server,
        MAIL_STARTTLS=settings.mail_starttls,
        MAIL_SSL_TLS=settings.mail_ssl_tls,
        USE_CREDENTIALS=True,
        VALIDATE_CERTS=True,
        TEMPLATE_FOLDER=TEMPLATES_DIR,
    )


def _base_context() -> dict:
    """Common template variables injected into every email."""
    from datetime import datetime, timezone
    return {
        "base_url": settings.base_url,
        "year": datetime.now(timezone.utc).year,
    }


class EmailService:
    """Async email service backed by fastapi-mail + Jinja2 templates."""

    @staticmethod
    async def send_welcome_email(email: NameEmail) -> None:
        """Send a welcome email to a newly registered user."""
        context = {**_base_context(), "email": email}
        message = MessageSchema(
            subject="Chào mừng đến với MiniLink! 🎉",
            recipients=[email],
            template_body=context,
            subtype=MessageType.html,
        )
        fm = FastMail(_get_mail_config())
        await fm.send_message(message, template_name="welcome.html")

    @staticmethod
    async def send_reset_password_email(
        email: NameEmail,
        reset_token: str,
        expire_minutes: int = 30,
    ) -> None:
        """Send a password-reset email containing the reset link."""
        reset_url = f"{settings.base_url}/reset-password?token={reset_token}"
        context = {
            **_base_context(),
            "email": email,
            "reset_url": reset_url,
            "expire_minutes": expire_minutes,
        }
        message = MessageSchema(
            subject="Đặt lại mật khẩu MiniLink 🔐",
            recipients=[email],
            template_body=context,
            subtype=MessageType.html,
        )
        fm = FastMail(_get_mail_config())
        await fm.send_message(message, template_name="reset_password.html")

    @staticmethod
    async def send_forgot_password_code(
        email: NameEmail,
        code: str,
        expire_minutes: int = 10,
    ) -> None:
        """Send a forgot-password OTP code email."""
        context = {
            **_base_context(),
            "email": email,
            "code": code,
            "expire_minutes": expire_minutes,
        }
        message = MessageSchema(
            subject="Mã xác nhận đặt lại mật khẩu MiniLink 🔑",
            recipients=[email],
            template_body=context,
            subtype=MessageType.html,
        )
        fm = FastMail(_get_mail_config())
        await fm.send_message(message, template_name="forgot_password_code.html")

    @staticmethod
    async def send_custom_email(
        recipients: list[NameEmail],
        subject: str,
        template_name: str,
        context: dict,
    ) -> None:
        """Generic helper to send any templated email.

        Args:
            recipients: List of recipient email addresses.
            subject: Email subject line.
            template_name: Filename of the Jinja2 template inside ``templates/``.
            context: Variables to inject into the template.
        """
        full_context = {**_base_context(), **context}
        message = MessageSchema(
            subject=subject,
            recipients=recipients,
            template_body=full_context,
            subtype=MessageType.html,
        )
        fm = FastMail(_get_mail_config())
        await fm.send_message(message, template_name=template_name)


