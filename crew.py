import os
from crewai import Agent, Task, Crew
from dotenv import load_dotenv
from tools.smtp_email_tool import smtp_email_sender
from agents.search_agent import search_agent  # suppose que ce fichier est bien configuré

load_dotenv()

# Déclare l'agent d'envoi d'email (sans tools=[])
email_sender_agent = Agent(
    role="Email Sender",
    goal="Send an email with the funding results.",
    backstory="You're responsible for dispatching results to stakeholders.",
    verbose=True
)

# Tâche 1 : recherche de financements
search_task = Task(
    description="Search and summarize at least 5 active funding opportunities for documentary, fiction, or hybrid film projects.",
    expected_output="A detailed list of at least 5 film funding opportunities, including deadlines and links.",
    agent=search_agent
)

# Tâche 2 : création du texte d'email (facultatif, ici laissé vide car on utilise .invoke ensuite)
email_send_task = Task(
    description="Prepare the email content based on the search results.",
    expected_output="A ready-to-send email with the subject and funding list.",
    agent=email_sender_agent
)

# Crée l'équipe
crew = Crew(
    agents=[search_agent, email_sender_agent],
    tasks=[search_task, email_send_task],
    verbose=True
)

# Exécute la mission
results = crew.kickoff()
print("📄 Resultat généré par le Crew:\n", results)

# Envoi de l'email via smtp_email_sender (en dehors du Crew)
print("\n📤 Envoi de l'email...")

smtp_result = smtp_email_sender.invoke({
    "subject": "Film Funding Opportunities",
    "content": str(results).strip(),  # on convertit les résultats en texte propre
    "to_email": os.getenv("EMAIL_RECIPIENT")
})

print("📬 SMTP Result:", smtp_result)

