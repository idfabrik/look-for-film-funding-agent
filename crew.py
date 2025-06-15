import os
import requests
import socket
import requests.packages.urllib3.util.connection as urllib3_cn
from crewai import Agent, Task, Crew
from dotenv import load_dotenv
from tools.smtp_email_tool import smtp_email_sender
import gspread
from google.oauth2.service_account import Credentials
import re

# --- 🔧 Forcer l'utilisation d'IPv4 uniquement ---
def allowed_gai_family():
    return socket.AF_INET
urllib3_cn.allowed_gai_family = allowed_gai_family

# --- Charger les variables d'environnement ---
load_dotenv()

# --- Configuration Google Sheets ---
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
CREDENTIALS_FILE = os.getenv('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
SPREADSHEET_ID = '1tPTgSOLZxXQkBs0e5r_RuAmE6GODI1qgq_g7RFTELSE'

# --- Configuration de recherche ---
SEARCH_QUERIES = [
    # Recherches prioritaires France
    "financement film documentaire 2025 2026 France CNC aide cinema",
    "subvention documentaire fiction serie France 2025 2026",
    "coproduction internationale France Afrique cinema 2025 2026",
    "aide production audiovisuelle France documentaire fiction 2025",
    
    # Recherches prioritaires Allemagne
    "film funding Germany documentary fiction 2025 2026 Filmförderung",
    "German film funding international coproduction Africa 2025 2026",
    "Filmförderungsanstalt FFA documentary funding 2025 2026",
    "German French coproduction film funding 2025 2026",
    
    # Recherches spécifiques Bénin/Afrique
    "film funding Africa Benin documentary fiction 2025 2026",
    "African cinema funding international coproduction 2025 2026",
    "francophone film funding Africa documentary 2025 2026",
    
    # Recherches thématiques
    "documentary funding political subjects Africa 2025 2026",
    "cultural documentary funding voodoo traditional beliefs 2025",
    "international coproduction funding documentary series 2025 2026",
    
    # Recherches européennes
    "European film funding documentary fiction 2025 2026 Creative Europe",
    "EU funding cinema coproduction Africa 2025 2026",
    
    # Recherches générales
    "film funding opportunities 2025 2026 documentary fiction",
    "international film funding documentary series 2025 2026"
]

# --- Fonctions Google Sheets ---
def get_google_sheet():
    """Initialise et retourne la feuille Google Sheets"""
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    
    # Essayer d'ouvrir la feuille principale, sinon créer une nouvelle
    try:
        sheet = spreadsheet.worksheet("Film Funding")
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title="Film Funding", rows="1000", cols="10")
    
    return sheet

def setup_sheet_headers(sheet):
    """Configure les en-têtes de colonnes si elles n'existent pas"""
    headers = [
        "Nom", "Organisme", "Pays", "Deadline", "Lien", 
        "Résumé", "Email", "Conditions", "Catégorie", "Année", 
        "Date Ajout", "Statut", "Priorité"
    ]
    
    # Vérifier si la première ligne contient déjà des en-têtes
    try:
        existing_headers = sheet.row_values(1)
        if not existing_headers or len(existing_headers) == 0:
            sheet.append_row(headers)
            print("✅ En-têtes ajoutés à la feuille")
        else:
            # Ajouter les colonnes manquantes
            for i, header in enumerate(headers):
                if i >= len(existing_headers) or existing_headers[i] != header:
                    if i < len(existing_headers):
                        sheet.update_cell(1, i+1, header)
                    else:
                        # Étendre la ligne d'en-têtes
                        current_headers = sheet.row_values(1)
                        current_headers.extend(headers[len(current_headers):])
                        sheet.update('1:1', [current_headers])
                        break
    except Exception as e:
        print(f"⚠️ Erreur lors de la configuration des en-têtes : {e}")
        sheet.append_row(headers)

def categorize_funding(nom, resume, organisme):
    """Détermine la catégorie de financement"""
    text_to_analyze = f"{nom} {resume} {organisme}".lower()
    
    if any(word in text_to_analyze for word in ['série', 'series', 'tv', 'télévision', 'television']):
        return "Série"
    elif any(word in text_to_analyze for word in ['fiction', 'long-métrage', 'feature']):
        return "Fiction"
    elif any(word in text_to_analyze for word in ['documentaire', 'documentary', 'doc']):
        return "Documentaire"
    else:
        return "Général"

def determine_priority(pays, organisme):
    """Détermine la priorité basée sur le pays"""
    text_to_check = f"{pays} {organisme}".lower()
    
    if any(word in text_to_check for word in ['france', 'français', 'cnc', 'french']):
        return "Haute - France"
    elif any(word in text_to_check for word in ['germany', 'german', 'allemagne', 'deutschland', 'ffa']):
        return "Haute - Allemagne"
    elif any(word in text_to_check for word in ['bénin', 'benin', 'afrique', 'africa']):
        return "Moyenne - Afrique"
    elif any(word in text_to_check for word in ['europe', 'eu', 'creative']):
        return "Moyenne - Europe"
    else:
        return "Normale"

def extract_year(deadline, resume):
    """Extrait l'année de l'aide"""
    text_to_check = f"{deadline} {resume}"
    
    if '2025' in text_to_check:
        return "2025"
    elif '2026' in text_to_check:
        return "2026"
    elif any(word in text_to_check.lower() for word in ['2025', '2026']):
        return "2025-2026"
    else:
        return "Non spécifié"
    """Récupère les entrées existantes pour éviter les doublons"""
    try:
        records = sheet.get_all_records()
        existing = set()
        for record in records:
            nom = record.get('Nom', '').strip()
            lien = record.get('Lien', '').strip()
            if nom and lien:
                existing.add((nom.lower(), lien))
        return existing
    except Exception as e:
        print(f"⚠️ Erreur lors de la récupération des entrées : {e}")
        return set()

def send_to_google_sheets(funding_data):
    """Envoie les données vers Google Sheets"""
    try:
        sheet = get_google_sheet()
        setup_sheet_headers(sheet)
        existing_entries = get_existing_entries(sheet)
        
        added_count = 0
        duplicate_count = 0
        
        for entry in funding_data:
            nom = entry.get('nom', '').strip()
            lien = entry.get('lien', '').strip()
            
            # Vérifier les doublons
            if (nom.lower(), lien) in existing_entries:
                duplicate_count += 1
                print(f"⏭️ Doublon ignoré : {nom}")
                continue
            
            # Déterminer la catégorie, année et priorité
            categorie = categorize_funding(entry.get('nom', ''), entry.get('résumé', ''), entry.get('organisme', ''))
            annee = extract_year(entry.get('deadline', ''), entry.get('résumé', ''))
            priorite = determine_priority(entry.get('pays', ''), entry.get('organisme', ''))
            
            # Préparer la ligne de données
            from datetime import datetime
            row_data = [
                entry.get('nom', ''),
                entry.get('organisme', ''),
                entry.get('pays', ''),
                entry.get('deadline', ''),
                entry.get('lien', ''),
                entry.get('résumé', ''),
                entry.get('email', ''),
                entry.get('conditions', ''),
                categorie,
                annee,
                datetime.now().strftime('%Y-%m-%d %H:%M'),
                'Nouveau',
                priorite
            ]
            
            try:
                sheet.append_row(row_data)
                added_count += 1
                print(f"✅ Ajouté : {nom}")
            except Exception as e:
                print(f"❌ Erreur lors de l'ajout de {nom} : {e}")
        
        print(f"\n📊 Résumé Google Sheets :")
        print(f"   - {added_count} nouvelles entrées ajoutées")
        print(f"   - {duplicate_count} doublons ignorés")
        
        return True
        
    except Exception as e:
        print(f"❌ Erreur Google Sheets : {e}")
        return False

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

# --- Fonction de parsing des résultats ---
def parse_funding_results(result_text):
    """Parse le texte des résultats pour extraire les données structurées"""
    funding_entries = []
    
    # Essayer différents patterns de regex pour capturer les données
    patterns = [
        # Pattern principal avec tous les champs
        r"Nom\s*:\s*(.*?)\s*Organisme\s*:\s*(.*?)\s*Pays\s*:\s*(.*?)\s*Deadline\s*:\s*(.*?)\s*Lien\s*:\s*(.*?)\s*Résumé\s*:\s*(.*?)\s*Email\s*:\s*(.*?)\s*Conditions\s*:\s*(.*?)(?=Nom\s*:|$)",
        # Pattern alternatif sans certains champs
        r"Nom\s*:\s*(.*?)\s*Organisme\s*:\s*(.*?)\s*Pays\s*:\s*(.*?)\s*Lien\s*:\s*(.*?)\s*Résumé\s*:\s*(.*?)(?=Nom\s*:|$)",
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, result_text, re.DOTALL | re.IGNORECASE)
        
        for match in matches:
            if len(match) >= 5:  # Au minimum nom, organisme, pays, lien, résumé
                entry = {
                    "nom": match[0].strip(),
                    "organisme": match[1].strip(),
                    "pays": match[2].strip(),
                    "deadline": match[3].strip() if len(match) > 3 else "",
                    "lien": match[4].strip() if len(match) > 4 else match[3].strip(),
                    "résumé": match[5].strip() if len(match) > 5 else match[4].strip(),
                    "email": match[6].strip() if len(match) > 6 else "",
                    "conditions": match[7].strip() if len(match) > 7 else ""
                }
                
                # Nettoyer les données
                for key, value in entry.items():
                    entry[key] = re.sub(r'\*\*', '', value)  # Enlever les **
                    entry[key] = re.sub(r'[\(\)]+', '', entry[key])  # Enlever parenthèses superflues
                    entry[key] = entry[key].strip()
                
                if entry["nom"] and entry["organisme"]:  # Vérifier que les champs essentiels existent
                    funding_entries.append(entry)
        
        if funding_entries:  # Si on a trouvé des entrées, on s'arrête
            break
    
    # Si aucun pattern ne fonctionne, essayer une approche plus simple
    if not funding_entries:
        lines = result_text.split('\n')
        current_entry = {}
        
        for line in lines:
            line = line.strip()
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip().lower()
                value = value.strip()
                
                if 'nom' in key:
                    if current_entry and current_entry.get('nom'):
                        funding_entries.append(current_entry)
                    current_entry = {'nom': value}
                elif 'organisme' in key:
                    current_entry['organisme'] = value
                elif 'pays' in key:
                    current_entry['pays'] = value
                elif 'deadline' in key:
                    current_entry['deadline'] = value
                elif 'lien' in key:
                    current_entry['lien'] = value
                elif 'résumé' in key or 'resume' in key:
                    current_entry['résumé'] = value
                elif 'email' in key:
                    current_entry['email'] = value
                elif 'condition' in key:
                    current_entry['conditions'] = value
        
        if current_entry and current_entry.get('nom'):
            funding_entries.append(current_entry)
    
    return funding_entries

# --- Agents ---
search_agent = Agent(
    role="Spécialiste du financement audiovisuel France-Allemagne-Afrique",
    goal="Identifier les aides au financement pour documentaires, fictions et séries, priorité France-Allemagne, pour projet tourné au Bénin sur vaudou et politique.",
    backstory=(
        "Expert en coproductions internationales France-Allemagne-Afrique, spécialisé dans les projets "
        "documentaires et fictions abordant des sujets culturels et politiques africains."
    ),
    verbose=True,
)

data_cleaning_agent = Agent(
    role="Nettoyeur de données",
    goal="Nettoyer, uniformiser et reformuler les informations collectées pour créer une base exploitable dans un tableur, sans mise en forme superflue ni éléments markdown.",
    backstory="Spécialiste de la normalisation de données pour des bases structurées.",
    verbose=True,
)

# --- Fonction de recherche améliorée ---
def funding_research_task():
    print("🔍 Performing multiple Google searches...")
    all_opportunities = []
    
    for i, query in enumerate(SEARCH_QUERIES, 1):
        print(f"\n🎯 Recherche {i}/{len(SEARCH_QUERIES)}: {query}")
        try:
            urls = google_search(query)
            print(f"🔗 Found {len(urls)} URLs")
            
            # Traiter plus d'URLs par requête (10 au lieu de 5)
            for j, url in enumerate(urls[:10]):
                print(f"📄 Reading {j+1}/10: {url}")
                try:
                    summary = extract_page_content(url)
                    all_opportunities.append(f"---\nQuery: {query}\nURL: {url}\n{summary}")
                except Exception as e:
                    print(f"⚠️ Erreur extraction {url}: {e}")
                    continue
        except Exception as e:
            print(f"❌ Erreur recherche '{query}': {e}")
            continue
    
    print(f"\n✅ Total: {len(all_opportunities)} contenus extraits")
    return "\n\n".join(all_opportunities)

# --- Tasks ---
search_task = Task(
    description=f"""Analyse le contenu web collecté et extrait les opportunités de financement pour:

PROJET CIBLE:
- Documentaire/Fiction/Série sur le vaudou et la politique au Bénin
- Coproduction France-Allemagne-Bénin
- Années 2025-2026

PRIORITÉS DE RECHERCHE:
1. Aides françaises (CNC, régionales, etc.)
2. Aides allemandes (FFA, Länder, etc.) 
3. Aides européennes (Creative Europe, etc.)
4. Aides internationales Afrique-Europe

Pour chaque aide, fournis ces champs EXACTS:
- Nom: Nom officiel de l'aide
- Organisme: Organisation qui propose le financement
- Pays: Pays ou région de l'organisme
- Deadline: Date limite de candidature (2025/2026)
- Lien: URL directe vers la page de l'aide
- Résumé: Description courte (2-3 phrases)
- Email: Email de contact si disponible
- Conditions: Critères d'éligibilité clés

Contenu à analyser:
{funding_research_task()}""",
    expected_output="Liste structurée d'aides avec champs: Nom, Organisme, Pays, Deadline, Lien, Résumé, Email, Conditions. Priorité aux aides France-Allemagne 2025-2026.",
    agent=search_agent,
)

# Tâche de nettoyage
data_cleaning_task = Task(
    description="""Nettoie et structure les données pour un projet documentaire/fiction au Bénin:

NETTOYAGE:
- Supprime caractères inutiles (**...**, parenthèses superflues)
- Corrige formats email et liens
- Reformule résumés trop longs (max 2-3 phrases)
- Identifie si l'aide concerne: Documentaire/Fiction/Série

PRIORISATION:
- Marque les aides France et Allemagne comme prioritaires
- Identifie les aides 2025 et 2026
- Signale les aides spécifiques coproduction internationale

STRUCTURE FINALE:
Champs obligatoires: Nom, Organisme, Pays, Deadline, Lien, Résumé, Email, Conditions
Résultat prêt pour tableur avec classification automatique.""",
    expected_output="Version propre et classifiée (Documentaire/Fiction/Série) avec priorités France-Allemagne identifiées",
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

# --- Parser et envoyer vers Google Sheets ---
print("📊 Parsing results for Google Sheets...")
funding_data = parse_funding_results(final_content)

if funding_data:
    print(f"📋 Found {len(funding_data)} funding opportunities")
    
    # Envoyer vers Google Sheets
    sheets_success = send_to_google_sheets(funding_data)
    
    if sheets_success:
        print("✅ Data successfully sent to Google Sheets!")
    else:
        print("❌ Failed to send data to Google Sheets")
else:
    print("⚠️ No structured funding data found to send to Google Sheets")

# --- Send email ---
email_subject = "🎬 Film Funding Opportunities - Cleaned Results"
to_email = os.getenv("EMAIL_RECIPIENT")

if to_email:
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
else:
    print("⚠️ No email recipient configured, skipping email...")

print("\n✅ Script completed!")

# Optionnel : afficher le résultat dans la console
print("\n" + "="*50)
print("RÉSULTATS NETTOYÉS :")
print("="*50)
print(final_content)

if funding_data:
    print("\n" + "="*50)
    print("DONNÉES STRUCTURÉES POUR GOOGLE SHEETS :")
    print("="*50)
    for i, entry in enumerate(funding_data, 1):
        print(f"\n--- ENTRÉE {i} ---")
        for key, value in entry.items():
            print(f"{key.capitalize()}: {value}")
