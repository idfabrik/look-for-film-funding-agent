import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
from langchain_core.tools import tool

load_dotenv()

@tool
def smtp_email_sender(subject: str, content: str, to_email: str = None) -> str:
    """
    Send an email via SMTP using the .env credentials.
    """
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", 465))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    env_recipient = os.getenv("EMAIL_RECIPIENT")
    final_recipient = to_email or env_recipient

    print("📤 Sending email to:", final_recipient)
    print("Subject:", subject)
    print("Content:", content)

    if not all([smtp_server, smtp_user, smtp_password, final_recipient]):
        return "❌ Missing required SMTP settings or recipient email."

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = final_recipient
    msg.set_content(content)

    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        return f"✅ Email sent to {final_recipient}"
    except Exception as e:
        return f"❌ Failed to send email: {str(e)}"

