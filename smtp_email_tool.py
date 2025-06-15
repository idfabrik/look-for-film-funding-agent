import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from crewai_tools import BaseTool
import os

class SMTPSendEmailTool(BaseTool):
    name = "smtp_email_sender"
    description = "Send an email with subject and content to a target address using SMTP credentials."

    def _run(self, subject: str, content: str, to_email: str) -> str:
        smtp_server = os.getenv("SMTP_SERVER")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER")
        smtp_password = os.getenv("SMTP_PASSWORD")
        from_email = smtp_user

        try:
            msg = MIMEMultipart()
            msg["From"] = from_email
            msg["To"] = to_email
            msg["Subject"] = subject

            msg.attach(MIMEText(content, "plain"))

            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)

            return f"Email sent to {to_email} successfully."
        except Exception as e:
            return f"Failed to send email: {str(e)}"

