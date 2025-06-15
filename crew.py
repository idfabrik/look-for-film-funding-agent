import os
import requests
import socket
import requests.packages.urllib3.util.connection as urllib3_cn
from crewai import Agent, Task, Crew
from dotenv import load_dotenv
from tools.smtp_email_tool import smtp_email_sender

# --- 🔧 Forcer l'utilisation d'IPv4 uniquement ---
def allowed_gai_family():
    return socket.AF_INET
urllib3_cn.allowed_gai_family = allowed_gai_family

# --- Charger les variables d'environnement ---
load_dotenv()

# --- Google Search API Wrapper ---
def google_search(query):
    api_key = os.getenv("GOOGLE_API_KEY")
    cse_id = os.getenv("GOOGLE_CSE_ID")
    if not api_key or not cse_id:
        raise ValueError("❌ GOOGLE_API_KEY or GOOGLE_CSE_ID is not set in the environment.")
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": cse_id,
        "q": query
    }
    print("🔐 API Key:", api_key)
    print("🔍 CSE ID:", cse_id)
    print("📡 Query:", query)
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    return [item["link"] for item in data.get("items", [])]

# --- VerifyBot API Wrapper ---
def extract_page_content(url):
    CONTENT_API_KEY = os.getenv("VERIFYBOT_CONTENT_API_KEY")
    if not CONTENT_API_KEY:
        raise ValueError("❌ VERIFYBOT_CONTENT_API_KEY not set in the environment.")
    api_url = "https://cockpit.verifybot.app/api-get-content.php"
    params = {
        "url": url,
        "key": CONTENT_API_KEY
    }
    response = requests.get(api_url, params=params)
    response.raise_for_status()
    data = response.json()
    return data.get("content") or data.get("summary") or "No summary available."

# --- Agents ---
search_agent = Agent(
    role="Film Funding Researcher",
    goal="Identify current film funding opportunities from public and private sources.",
    backstory=(
        "You are an expert in researching grants, co-production opportunities, and development funds for films and series."
    ),
    verbose=True,
)

data_cleaning_agent = Agent(
    role="Nettoyeur de données",
    goal="Nettoyer, uniformiser et reformuler les informations collectées pour créer une base exploitable dans un tableur, sans mise en forme superflue ni éléments markdown.",
    backstory="Spécialiste de la normalisation de données pour des bases structurées.",
    verbose=True,
)

# --- Fonction de recherche ---
def funding_research_task():
    query = "film funding opportunities 2025 documentary fiction site:.org OR site:.gov OR site:.eu"
    print("🔍 Performing Google search...")
    urls = google_search(query)
    print(f"🔗 Found {len(urls)} URLs")
    opportunities = []
    for url in urls[:5]:
        print(f"📄 Reading: {url}")
        summary = extract_page_content(url)
        opportunities.append(f"---\n{url}\n{summary}")
    return "\n\n".join(opportunities)

# --- Tasks ---
search_task = Task(
    description=f"""Analyze the collected web content and extract current film funding opportunities for documentaries or fiction projects.

For each funding opportunity, provide these exact fields:
- Nom: The official name of the grant/fund
- Organisme: The organization offering the funding
- Pays: Country or region of the funding body
- Deadline: Application deadline (if available)
- Lien: Direct URL to the funding page
- Résumé: Brief description of the funding (2-3 sentences)
- Email: Contact email (if available)  
- Conditions: Key eligibility requirements

Content to analyze:
{funding_research_task()}""",
    expected_output="A structured list of funding opportunities with the exact fields: Nom, Organisme, Pays, Deadline, Lien, Résumé, Email, Conditions for each entry.",
    agent=search_agent,
)

# Tâche de nettoyage
data_cleaning_task = Task(
    description="""Prends les résultats ci-dessous et nettoie les données : 
- Enlève tous les caractères inutiles (**...**, parenthèses superflues, etc.)
- Remplace les liens markdown par de vrais liens
- Corrige les formats d'email
- Reformule les résumés si trop longs (max 2-3 phrases)
- Sépare bien chaque aide avec les champs : Nom, Organisme, Pays, Deadline, Lien, Résumé, Email, Conditions
- Supprime les doublons potentiels
- Assure-toi que chaque champ est sur une ligne séparée
Donne un résultat prêt à être inséré dans un tableur.""",
    expected_output="Une version propre, lisible et directement exploitable pour un tableur avec des champs bien séparés",
    agent=data_cleaning_agent
)

# --- Crew ---
crew = Crew(
    agents=[search_agent, data_cleaning_agent],
    tasks=[search_task, data_cleaning_task],
    verbose=True,
)

# --- Run ---
print("🚀 Starting funding research and cleaning tasks...")
try:
    result = crew.kickoff()
    
    # Extraire le résultat final
    if hasattr(result, 'raw') and isinstance(result.raw, str):
        final_content = result.raw
    else:
        final_content = str(result)
        
except Exception as e:
    print("❌ Error during crew execution:", str(e))
    final_content = "No results due to error."

# --- Send email ---
email_subject = "🎬 Film Funding Opportunities - Cleaned Results"
to_email = os.getenv("EMAIL_RECIPIENT")

print("📤 Sending email...")
try:
    email_result = smtp_email_sender.invoke({
        "subject": email_subject,
        "content": final_content,
        "to_email": to_email
    })
    print("📧 Email result:", email_result)
except Exception as e:
    print("❌ Failed to send email:", str(e))

print("\n✅ Script completed!")

# Optionnel : afficher le résultat dans la console
print("\n" + "="*50)
print("RÉSULTATS NETTOYÉS :")
print("="*50)
print(final_content)
