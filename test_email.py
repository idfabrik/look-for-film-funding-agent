from tools.smtp_email_tool import smtp_email_sender

result = smtp_email_sender.invoke({
    "subject": "Test Email from CLI",
    "content": "This is a test email sent from CLI using .invoke().",
    # "to_email": "override@example.com"  # facultatif
})

print(result)

