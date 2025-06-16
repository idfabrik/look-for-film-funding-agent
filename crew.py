from crewai import Agent, Task, Crew
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os
import requests
import re
from sheets_utils import (
    send_to_google_sheet, 
    get_existing_entries, 
    get_keywords_from_sheet, 
    generate_crew_prompt, 
    parse_crew_output,
    test_google_sheets_connection
)

# Charger les variables d'environnement (.env)
load_dotenv()

# Test de connexion Google Sheets au démarrage
print("🔧 Vérification de la connexion Google Sheets...")
if not test_google_sheets_connection():
    print("❌ Impossible de se connecter à Google Sheets. Vérifiez votre fichier credentials.json")
    exit(1)

# Initialiser le modèle LLM
llm = ChatOpenAI(model="gpt-4-turbo")

# Générer dynamiquement le prompt basé sur les colonnes du Google Sheet
prompt_text, expected_headers = generate_crew_prompt()
print(f"\n📋 Colonnes à rechercher : {expected_headers}\n")

# Récupérer les aides déjà trouvées
existing_aides = get_existing_entries()

# Agent 1 : Recherche
research_agent = Agent(
    role="Chercheur d'aides au documentaire",
    goal="Identifier et extraire des aides financières pertinentes pour un documentaire en postproduction, abordant l'animisme et les esprits, tourné en Thaïlande et coproduit avec la France.",
    backstory="Expert en financement culturel pour documentaires internationaux.",
    verbose=True,
    llm=llm
)

# Agent 2 : Nettoyeur
data_cleaning_agent = Agent(
    role="Nettoyeur de données",
    goal="Nettoyer et uniformiser les informations collectées pour créer une base exploitable, en respectant exactement les colonnes demandées.",
    backstory="Spécialiste de la normalisation de données pour des bases structurées.",
    verbose=True,
    llm=llm
)

# Agent 3 : Vérificateur & Analyste
analysis_agent = Agent(
    role="Vérificateur et analyste stratégique",
    goal="Vérifier la pertinence des liens, s'assurer qu'ils pointent vers des aides spécifiques, et enrichir avec des commentaires stratégiques.",
    backstory="Consultant expert en montage de dossiers de financement pour films internationaux.",
    verbose=True,
    llm=llm
)

# Génération de la consigne en excluant les aides déjà connues
exclusion_text = ""
if existing_aides:
    # Extraire les noms des aides existantes
    existing_names = []
    for aide in existing_aides:
        # Chercher le champ nom dans différentes variations possibles
        nom = aide.get('Nom') or aide.get('nom') or aide.get('NAME') or ""
        if nom:
            existing_names.append(nom)
    
    if existing_names:
        exclusion_text = "\nIgnore les aides déjà listées avec les noms suivants :\n" + "\n".join(
            f"- {nom}" for nom in existing_names
        )

# API Google Search params
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CX = os.getenv("GOOGLE_CSE_ID")  # Correction du nom de la variable

# Charger dynamiquement les mots-clés depuis Google Sheets (onglet "MotsClés")
keywords_to_test = get_keywords_from_sheet()

# Si pas de mots-clés dans le sheet, utiliser des mots-clés par défaut
if not keywords_to_test:
    print("⚠️ Aucun mot-clé trouvé dans l'onglet 'MotsClés'. Utilisation des mots-clés par défaut.")
    keywords_to_test = [
        "aide documentaire postproduction France",
        "financement documentaire coproduction internationale",
        "subvention documentaire culturel 2024"
    ]

print(f"\n🔍 Mots-clés à rechercher : {keywords_to_test}\n")

# API perso pour extraire le contenu des pages
CONTENT_API_KEY = os.getenv("VERIFYBOT_CONTENT_API_KEY")

def google_search_urls(query):
    """Effectue une recherche Google et retourne les URLs"""
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_API_KEY,
        "cx": GOOGLE_CX,
        "q": query
    }
    try:
        res = requests.get(url, params=params)
        results = res.json()
        links = [item["link"] for item in results.get("items", [])][:5]  # Limiter à 5 résultats
        print(f"\n🔍 Recherche : {query}")
        for link in links:
            print(f"  - {link}")
        return links
    except Exception as e:
        print(f"❌ Erreur recherche Google : {e}")
        return []

def get_page_content(target_url):
    """Extrait le contenu d'une page web"""
    api_url = f"https://cockpit.verifybot.app/api-get-content.php"
    params = {
        "url": target_url,
        "key": CONTENT_API_KEY
    }
    
    # Log de l'URL pour debug
    print(f"  📡 Appel API : {api_url}?url={target_url}&key={'*' * 10 if CONTENT_API_KEY else 'NO_KEY'}")
    
    try:
        response = requests.get(api_url, params=params, timeout=10)
        data = response.json()
        
        if response.status_code != 200:
            print(f"  ❌ Erreur HTTP {response.status_code}")
            return None
            
        content = data.get("content", "")
        if content:
            print(f"  ✅ Contenu extrait : {len(content)} caractères")
        else:
            print(f"  ⚠️ Réponse vide ou erreur : {data.get('error', 'Aucun contenu')}")
            
        return content if content else None
    except Exception as e:
        print(f"  ❌ Exception : {e}")
        return None

# Collecter le contenu des pages
documents_text = ""
total_urls = 0

for keyword in keywords_to_test:
    urls = google_search_urls(keyword)
    for url in urls:
        try:
            content = get_page_content(url)
            if content:
                documents_text += f"\n\n---\nContenu extrait de : {url}\n{content[:5000]}\n"  # Limiter la taille
                total_urls += 1
            else:
                print(f"⚠️ Aucun contenu extrait pour : {url}")
        except Exception as e:
            print(f"Erreur sur {url}: {e}")

print(f"\n📚 Total : {total_urls} pages extraites\n")

# Si aucun contenu trouvé, arrêter
if not documents_text:
    print("❌ Aucun contenu trouvé. Vérifiez vos clés API.")
    exit(1)

# Tâche de recherche avec prompt dynamique
funding_task = Task(
    description=f"""{prompt_text}
    
    IMPORTANT : Pour chaque aide trouvée, extrais TOUTES les informations demandées.
    Si une information n'est pas disponible, indique "Non spécifié" mais inclus quand même le champ.
    
    {exclusion_text}
    
    Contenu à analyser :
    {documents_text[:50000]}""",  # Limiter la taille pour GPT
    expected_output=f"Une liste structurée d'aides avec EXACTEMENT ces champs : {', '.join(expected_headers)}",
    agent=research_agent
)

# Tâche de nettoyage
data_cleaning_task = Task(
    description=f"""Prends les résultats et nettoie-les pour un tableur :
    - Supprime TOUS les caractères de formatage : *, **, _, __, #, ##, ###, etc.
    - Supprime les retours à la ligne multiples et remplace par des espaces
    - Supprime les tabulations et caractères spéciaux
    - Convertis tout en texte brut, sans formatage markdown ou HTML
    - Assure-toi que chaque aide a TOUS les champs suivants : {', '.join(expected_headers)}
    - Standardise les formats (dates en DD/MM/YYYY, emails sans espaces, liens complets avec https://)
    - Garde un format cohérent pour chaque entrée
    - Maximum 500 caractères par champ pour éviter les débordements
    - Remplace les caractères problématiques comme les guillemets par des apostrophes simples""",
    expected_output=f"Liste propre en texte brut avec ces champs exacts : {', '.join(expected_headers)}",
    agent=data_cleaning_agent
)

# Tâche d'analyse
analysis_task = Task(
    description=f"""Vérifie et enrichis chaque aide :
    - Vérifie que les liens sont pertinents (pas de pages d'accueil génériques)
    - Ajoute des commentaires stratégiques sur l'adéquation avec le projet
    - Complète les informations manquantes si possible
    - Structure finale avec TOUS ces champs : {', '.join(expected_headers)}""",
    expected_output=f"Version finale enrichie avec tous les champs : {', '.join(expected_headers)}",
    agent=analysis_agent
)

# Création de la crew
crew = Crew(
    agents=[research_agent, data_cleaning_agent, analysis_agent],
    tasks=[funding_task, data_cleaning_task, analysis_task],
    verbose=True
)

print("\n🚀 Lancement de la recherche d'aides...\n")

# Exécution
try:
    result = crew.kickoff()
    result_text = str(result)
    
    print("\n📄 Résultat brut (aperçu) :")
    print(result_text[:1000] + "..." if len(result_text) > 1000 else result_text)
    
    # Parser le résultat avec la nouvelle fonction dynamique
    entries = parse_crew_output(result_text, expected_headers)
    
    print(f"\n📊 {len(entries)} aide(s) extraite(s)")
    
    # Si pas d'entrées, essayer un parsing alternatif
    if not entries:
        print("\n⚠️ Parsing standard échoué. Tentative de parsing alternatif...")
        
        # Méthode alternative : chercher des blocs de texte structurés
        # Chercher toutes les URLs dans le texte
        urls = re.findall(r'https?://[^\s]+', result_text)
        print(f"URLs trouvées dans le résultat : {len(urls)}")
        
        # Créer des entrées basiques avec ce qu'on trouve
        for i, url in enumerate(urls[:10]):  # Limiter à 10
            # Chercher du contexte autour de l'URL
            url_context = ""
            url_pos = result_text.find(url)
            if url_pos > 0:
                # Prendre 200 caractères avant et après l'URL
                start = max(0, url_pos - 200)
                end = min(len(result_text), url_pos + len(url) + 200)
                url_context = result_text[start:end]
            
            # Essayer d'extraire un nom
            nom_patterns = [
                r'(?:Nom|Aide|Programme|Fonds)\s*:\s*([^\n]+)',
                r'(?:^|\n)([A-Z][^:\n]{10,50})(?=\n)',
                r'(?:aide|subvention|financement)\s+([^\n]+)'
            ]
            
            nom = f"Aide {i+1}"  # Nom par défaut
            for pattern in nom_patterns:
                match = re.search(pattern, url_context, re.IGNORECASE)
                if match:
                    nom = match.group(1).strip()
                    break
            
            # Créer une entrée basique
            entry = {}
            
            # Remplir avec les colonnes attendues
            for header in expected_headers:
                if 'nom' in header.lower():
                    entry[header] = nom
                elif 'lien' in header.lower() or 'url' in header.lower():
                    entry[header] = url.strip()
                elif 'résumé' in header.lower() or 'resume' in header.lower():
                    entry[header] = url_context.replace('\n', ' ').strip()[:200]
                elif 'statut' in header.lower():
                    entry[header] = "À vérifier"
                elif 'organisme' in header.lower():
                    if 'cnc' in url.lower():
                        entry[header] = "CNC"
                    elif 'scam' in url.lower():
                        entry[header] = "SCAM"
                    elif 'iledefrance' in url.lower():
                        entry[header] = "Région Île-de-France"
                    else:
                        entry[header] = ""
                elif 'pays' in header.lower():
                    if any(keyword in url.lower() for keyword in ['cnc', 'scam', 'iledefrance', 'france']):
                        entry[header] = "France"
                    else:
                        entry[header] = ""
                else:
                    entry[header] = ""
            
            entries.append(entry)
        
        print(f"\n📊 {len(entries)} aide(s) créée(s) par parsing alternatif")
    
    if entries:
        print("\n🔍 Aperçu des entrées extraites :")
        for i, entry in enumerate(entries[:3]):
            print(f"\n--- Entrée {i+1} ---")
            for key, value in entry.items():
                print(f"  {key}: {value[:100] if value and len(str(value)) > 100 else value}")
        
        # Envoi vers Google Sheets
        print("\n📤 Envoi vers Google Sheets...")
        send_to_google_sheet(entries)
    else:
        print("\n❌ Aucune aide trouvée même avec le parsing alternatif")
        print("\nDébut du résultat brut pour analyse :")
        print(result_text[:1000])
        
except Exception as e:
    print(f"\n❌ Erreur lors de l'exécution : {e}")
    import traceback
    traceback.print_exc()

#print("\n✅ Script terminé")

# Remplacer le dernier "print("\n✅ Script terminé")" par :

# Email de notification
try:
    from tools.smtp_email_tool import smtp_email_sender

    # Préparer le message
    if entries:
        subject = f"✅ Funding Script - {len(entries)} nouvelles aides"
        message = f"Script terminé avec succès. {len(entries)} nouvelles aides ajoutées au Google Sheet."
    else:
        subject = "⚠️ Funding Script - Aucune nouvelle aide"
        message = "Script terminé mais aucune nouvelle aide trouvée."

    # Ajouter timestamp
    # message += f"\nExécuté le {datetime.now().strftime('%d/%m/%Y à %H:%M')}"

    # Envoyer
    email_result = smtp_email_sender.invoke({
        "subject": subject,
        "content": message
    })
    print(f"\n📧 Email envoyé : {email_result}")

except Exception as e:
    print(f"\n⚠️ Erreur envoi email : {e}")

print("\n✅ Script terminé")
