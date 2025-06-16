import gspread
from google.oauth2.service_account import Credentials
import re
from datetime import datetime

# Configuration
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
CREDENTIALS_FILE = 'credentials.json'
SPREADSHEET_ID = '1tPTgSOLZxXQkBs0e5r_RuAmE6GODI1qgq_g7RFTELSE'
WORKSHEET_NAME = 'Film Funding'


def test_google_sheets_connection():
    """Teste la connexion à Google Sheets"""
    try:
        print("🔧 Test de connexion à Google Sheets...")
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        print(f"✅ Spreadsheet ouvert : {spreadsheet.title}")
        sheet = spreadsheet.worksheet(WORKSHEET_NAME)
        print(f"✅ Feuille '{WORKSHEET_NAME}' accessible")
        headers = sheet.row_values(1) if sheet.row_count > 0 else []
        print(f"✅ En-têtes lus : {headers}")
        return True
    except FileNotFoundError:
        print("❌ Fichier credentials.json introuvable")
        return False
    except Exception as e:
        print(f"❌ Erreur de connexion : {e}")
        return False


def normalize_key(text):
    """Normalise une clé pour la comparaison (minuscules, sans accents, sans espaces)"""
    if not text:
        return ""
    replacements = {
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'à': 'a', 'â': 'a', 'ä': 'a',
        'ù': 'u', 'û': 'u', 'ü': 'u',
        'ô': 'o', 'ö': 'o',
        'î': 'i', 'ï': 'i',
        'ç': 'c'
    }
    text = text.lower()
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r'[^a-z0-9]', '', text)
    return text


def get_sheet_columns():
    """Récupère les colonnes actuelles du Google Sheet"""
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)
        all_values = sheet.get_all_values()
        if not all_values:
            return []
        headers = [h.strip() for h in all_values[0] if h.strip()]
        print(f"📋 Colonnes détectées dans le sheet : {headers}")
        return headers
    except Exception as e:
        print(f"❌ ERREUR lors de la lecture des colonnes : {e}")
        return []


def generate_crew_prompt():
    """Génère dynamiquement le prompt pour les agents CrewAI basé sur les colonnes du sheet"""
    headers = get_sheet_columns()
    if not headers:
        default_headers = ["Nom", "Organisme", "Pays", "Deadline", "Lien", "Résumé", "Email de contact", "Conditions d'éligibilité"]
        prompt = "Extrais les informations suivantes pour chaque aide :\n"
        for header in default_headers:
            prompt += f"- {header}\n"
        prompt += f"\nFormate chaque aide avec EXACTEMENT ces champs : {', '.join(default_headers)}"
        prompt += "\nSi tu ne trouves pas d'information pour un champ, laisse-le vide mais inclus quand même le champ."
        return prompt, default_headers
    
    prompt = "Extrais les informations suivantes pour chaque aide :\n"
    for header in headers:
        if header.lower() not in ['date ajout', 'id', 'timestamp']:
            prompt += f"- {header}\n"
    prompt += f"\nFormate chaque aide avec EXACTEMENT ces champs : {', '.join(headers)}"
    prompt += "\nSi tu ne trouves pas d'information pour un champ, laisse-le vide mais inclus quand même le champ."
    print(f"\n📝 Prompt généré pour les agents :\n{prompt}\n")
    return prompt, headers


def clean_text_for_spreadsheet(text):
    """Nettoie le texte pour le rendre compatible avec les tableurs"""
    if not text:
        return ""
    text = str(text)
    # Supprimer le formatage markdown
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    text = re.sub(r'#{1,6}\s*', '', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'```[^`]*```', '', text)
    # Nettoyer les liens markdown
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Supprimer les caractères problématiques
    text = text.replace('"', "'").replace('"', "'").replace('"', "'").replace('«', "'").replace('»', "'")
    # Nettoyer les espaces
    text = re.sub(r'\n+', ' ', text)
    text = re.sub(r'\t+', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text)
    text = text.strip()
    if len(text) > 500:
        text = text[:497] + "..."
    return text


def validate_email(email):
    """Valide et nettoie une adresse email"""
    if not email:
        return ""
    email = clean_text_for_spreadsheet(email)
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if re.match(email_pattern, email):
        return email.lower()
    elif '@' in email:
        return email
    else:
        return ""


def validate_url(url):
    """Valide et nettoie une URL"""
    if not url:
        return ""
    url = clean_text_for_spreadsheet(url)
    if url and not url.startswith(('http://', 'https://')):
        if url.startswith('www.'):
            url = 'https://' + url
        elif '.' in url and not url.startswith(('ftp://', 'mailto:')):
            url = 'https://' + url
    return url


def parse_crew_output(result_text, expected_headers):
    """Parse le résultat des agents de manière flexible"""
    entries = []
    result_text = result_text.strip()
    current_entry = {}
    lines = result_text.split('\n')
    
    for line in lines:
        line = line.strip()
        if any(line.lower().startswith(h.lower() + ':') or line.lower().startswith(h.lower() + ' :') 
               for h in expected_headers if 'nom' in h.lower()):
            if current_entry and any(v for v in current_entry.values() if v):
                entries.append(current_entry)
                current_entry = {}
        
        for header in expected_headers:
            patterns = [
                f"{re.escape(header)}\\s*:\\s*(.+)",
                f"{re.escape(header.lower())}\\s*:\\s*(.+)",
                f"{re.escape(header.upper())}\\s*:\\s*(.+)"
            ]
            for pattern in patterns:
                match = re.match(pattern, line, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    value = clean_text_for_spreadsheet(value.rstrip(',;.'))
                    current_entry[header] = value
                    break
    
    if current_entry and any(v for v in current_entry.values() if v):
        entries.append(current_entry)
    
    if not entries:
        blocks = re.split(r'\n\s*\n', result_text)
        for block in blocks:
            if not block.strip():
                continue
            entry = {}
            for header in expected_headers:
                patterns = [
                    f"{re.escape(header)}\\s*:\\s*([^\n]+?)(?=(?:{'|'.join([re.escape(h) for h in expected_headers])})\\s*:|$)",
                    f"{re.escape(header.lower())}\\s*:\\s*([^\n]+?)(?=(?:{'|'.join([re.escape(h.lower()) for h in expected_headers])})\\s*:|$)"
                ]
                for pattern in patterns:
                    match = re.search(pattern, block, re.IGNORECASE | re.MULTILINE | re.DOTALL)
                    if match:
                        value = match.group(1).strip()
                        value = clean_text_for_spreadsheet(value)
                        entry[header] = value
                        break
            if entry and any(v for v in entry.values() if v):
                entries.append(entry)
    
    print(f"\n🔍 {len(entries)} entrées extraites du résultat des agents")
    return entries


def send_to_google_sheet(new_entries):
    """Envoie les entrées en s'adaptant complètement aux colonnes du sheet"""
    if not new_entries:
        print("⚠️ Aucune entrée à envoyer")
        return
        
    print(f"\n📋 DEBUG - Entrées reçues : {len(new_entries)}")
    
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    
    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)
        print(f"✅ Connecté à la feuille '{WORKSHEET_NAME}'")
    except Exception as e:
        print(f"❌ ERREUR de connexion : {e}")
        return

    all_values = sheet.get_all_values()
    
    if not all_values:
        if new_entries:
            headers = list(new_entries[0].keys())
            if 'Date Ajout' not in headers:
                headers.append('Date Ajout')
            sheet.append_row(headers)
            all_values = [headers]
            print(f"📝 En-têtes créés : {headers}")
    
    headers = all_values[0]
    column_index = {header: idx for idx, header in enumerate(headers)}
    
    nom_idx = None
    lien_idx = None
    for header, idx in column_index.items():
        if 'nom' in header.lower():
            nom_idx = idx
        elif 'lien' in header.lower() or 'url' in header.lower():
            lien_idx = idx
    
    existing_keys = set()
    if nom_idx is not None and lien_idx is not None and len(all_values) > 1:
        for row in all_values[1:]:
            if len(row) > max(nom_idx, lien_idx):
                nom = row[nom_idx].strip() if nom_idx < len(row) else ""
                lien = row[lien_idx].strip() if lien_idx < len(row) else ""
                if nom and lien:
                    existing_keys.add((nom, lien))
    
    added_count = 0
    skipped_count = 0
    date_ajout = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    for entry in new_entries:
        row = [""] * len(headers)
        nom = ""
        lien = ""
        
        for header, idx in column_index.items():
            if header == 'Date Ajout':
                row[idx] = date_ajout
            else:
                value = entry.get(header, "")
                if not value:
                    for key in entry.keys():
                        if key.lower() == header.lower():
                            value = entry[key]
                            break
                    if not value:
                        norm_header = normalize_key(header)
                        for key in entry.keys():
                            if normalize_key(key) == norm_header:
                                value = entry[key]
                                break
                
                if value:
                    if 'email' in header.lower() or 'mail' in header.lower():
                        value = validate_email(str(value))
                    elif 'lien' in header.lower() or 'url' in header.lower() or 'site' in header.lower():
                        value = validate_url(str(value))
                    else:
                        value = clean_text_for_spreadsheet(str(value))
                
                row[idx] = value if value else ""
                
                if 'nom' in header.lower() and value:
                    nom = str(value)
                elif ('lien' in header.lower() or 'url' in header.lower()) and value:
                    lien = str(value)
        
        if nom and lien:
            key = (nom.strip(), lien.strip())
            if key not in existing_keys:
                try:
                    sheet.append_row(row)
                    print(f"✅ Ajouté : {nom}")
                    added_count += 1
                    existing_keys.add(key)
                except Exception as e:
                    print(f"❌ ERREUR lors de l'ajout : {e}")
            else:
                print(f"⏭️ Doublon ignoré : {nom}")
                skipped_count += 1
    
    print(f"\n📊 Résumé : {added_count} nouvelle(s) entrée(s), {skipped_count} doublon(s)")


def analyze_unmapped_fields(sample_entry, existing_headers):
    """Analyse les champs qui ne correspondent à aucune colonne"""
    unmapped = []
    normalized_headers = [normalize_key(h) for h in existing_headers]
    for key in sample_entry.keys():
        if key not in existing_headers:
            if normalize_key(key) not in normalized_headers:
                unmapped.append(key)
    if unmapped:
        print(f"\n💡 Nouveaux champs détectés qui pourraient être ajoutés comme colonnes :")
        for field in unmapped:
            print(f"   - {field}")


def get_existing_entries():
    """Récupère toutes les entrées existantes avec tous leurs champs"""
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)
        records = sheet.get_all_records()
        print(f"📋 {len(records)} entrées existantes trouvées")
        return records
    except Exception as e:
        print(f"❌ ERREUR : {e}")
        return []


def log_keywords_to_sheet(keywords):
    """Ajoute des mots-clés dans l'onglet MotsClés"""
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("MotsClés")
    except gspread.WorksheetNotFound:
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        sheet = spreadsheet.add_worksheet(title="MotsClés", rows=100, cols=2)
        print("📝 Feuille 'MotsClés' créée")
    for keyword in keywords:
        try:
            sheet.append_row([keyword])
            print(f"✅ Mot-clé ajouté : {keyword}")
        except Exception as e:
            print(f"❌ ERREUR : {e}")


def get_keywords_from_sheet():
    """Récupère les mots-clés depuis l'onglet MotsClés"""
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("MotsClés")
        keywords = [k for k in sheet.col_values(1) if k.strip()]
        print(f"📋 {len(keywords)} mots-clés chargés")
        return keywords
    except gspread.WorksheetNotFound:
        print("⚠️ Aucun onglet 'MotsClés' trouvé")
        return []
    except Exception as e:
        print(f"❌ ERREUR : {e}")
        return []
