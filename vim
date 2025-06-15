from tools.smtp_email_tool import smtp_email_sender

result = smtp_email_sender(
    subject="Test Email from CLI",
    content="This is a test email sent via the smtp_email_sender tool.",
    to_email=None  # Ou "autre@email.com" si tu veux override le .env
)

print(result)

