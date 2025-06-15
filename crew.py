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

# --- Agent ---
search_agent = Agent(
    role="Film Funding Researcher",
    goal="Identify current film funding opportunities from public and private sources.",
    backstory=(
        "You are an expert in researching grants, co-production opportunities, and development funds for films and series."
    ),
    verbose=True,
)

# --- Task ---
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

# --- Crew ---
search_task = Task(
    description="Perform Google search and extract summaries from pages using VerifyBot API.",
    expected_output="A readable summary of at least 5 current film funding opportunities.",
    agent=search_agent,
    async_execution=False,
)

crew = Crew(
    agents=[search_agent],
    tasks=[search_task],
    verbose=True,
)

# --- Run ---
print("🚀 Starting funding research task...")
try:
    result = funding_research_task()
except Exception as e:
    print("❌ Error during funding research:", str(e))
    result = "No results due to error."

# --- Send email ---
email_subject = "🎬 Film Funding Opportunities"
to_email = os.getenv("EMAIL_RECIPIENT")

print("📤 Sending email...")
try:
    email_result = smtp_email_sender.invoke({
        "subject": email_subject,
        "content": result,
        "to_email": to_email
    })
    print("📧 Email result:", email_result)
except Exception as e:
    print("❌ Failed to send email:", str(e))

