from crewai import Agent

email_agent = Agent(
    role="Email Sender",
    goal="Send an email containing the results of the film funding research",
    backstory=(
        "You are responsible for sending summary reports and useful data by email "
        "to the project owner or collaborators, using a secure SMTP server."
    ),
    verbose=True
)

