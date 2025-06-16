import gspread
from google.oauth2.service_account import Credentials
import re
from datetime import datetime

# Configuration
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
CREDENTIALS_FILE = 'credentials.json'
SPREADSHEET_ID = '1tPTgSOLZxXQkBs0e5r_RuAmE6GODI1qgq_g7RFTELSE'
WORKSHEET_NAME = 'Film Funding'


def normalize_key(text):
    """Normalise une clé pour la comparaison (minuscules, sans accents, sans espaces)"""
    if not text:
        return ""
    # Remplacer les accents
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
    # Supprimer les espaces et caractères spéciaux
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
        
        # Retourner les en-têtes (première ligne)
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
        # Prompt par défaut si pas de colonnes
        return """Extrais les informations suivantes pour chaque aide :
        - Nom de l'aide
        - Organisme
        - Pays
        - Deadline
        - Lien
        - Résumé
        - Email de contact
        - Conditions d'éligibilité"""
    
    # Construire le prompt basé sur les colonnes existantes
    prompt = "Extrais les informations suivantes pour chaque aide :\n"
    
    for header in headers:
        # Ignorer certaines colonnes automatiques
        if header.lower() not in ['date ajout', 'id', 'timestamp']:
            prompt += f"- {header}\n"
    
    # Ajouter une instruction pour le format de sortie
    prompt += f"\nFormate chaque aide avec EXACTEMENT ces champs : {', '.join(headers)}"
    prompt += "\nSi tu ne trouves pas d'information pour un champ, laisse-le vide mais inclus quand même le champ."
    
    print(f"\n📝 Prompt généré pour les agents :\n{prompt}\n")
    return prompt, headers


def parse_crew_output(result_text, expected_headers):
    """Parse le résultat des agents de manière flexible"""
    entries = []
    
    # Nettoyer le texte
    result_text = result_text.strip()
    
    # Stratégie 1 : Rechercher des blocs avec les noms de champs
    # On cherche des patterns comme "Nom: valeur" ou "Nom : valeur"
    current_entry = {}
    
    lines = result_text.split('\n')
    
    for line in lines:
        line = line.strip()
        
        # Détecter si c'est un nouveau bloc (souvent signalé par "Nom:" au début)
        if any(line.lower().startswith(h.lower() + ':') or line.lower().startswith(h.lower() + ' :') 
               for h in expected_headers if 'nom' in h.lower()):
            # Si on a déjà une entrée en cours, la sauvegarder
            if current_entry and any(v for v in current_entry.values() if v):
                entries.append(current_entry)
                current_entry = {}
        
        # Extraire les paires clé:valeur
        for header in expected_headers:
            patterns = [
                f"{header}\\s*:\\s*(.+)",
                f"{header.lower()}\\s*:\\s*(.+)",
                f"{header.upper()}\\s*:\\s*(.+)"
            ]
            
            for pattern in patterns:
                match = re.match(pattern, line, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    # Nettoyer la valeur
                    value = value.rstrip(',;.')
                    current_entry[header] = value
                    break
    
    # Ajouter la dernière entrée
    if current_entry and any(v for v in current_entry.values() if v):
        entries.append(current_entry)
    
    # Stratégie 2 : Si pas d'entrées trouvées, essayer une approche par blocs
    if not entries:
        blocks = re.split(r'\n\s*\n', result_text)
        
        for block in blocks:
            if not block.strip():
                continue
                
            entry = {}
            for header in expected_headers:
                # Chercher le pattern dans tout le bloc
                patterns = [
                    f"{header}\\s*:\\s*([^\n]+?)(?=(?:{'|'.join(expected_headers)})\\s*:|$)",
                    f"{header.lower()}\\s*:\\s*([^\n]+?)(?=(?:{('|'.join(expected_headers)).lower()})\\s*:|$)"
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, block, re.IGNORECASE | re.MULTILINE | re.DOTALL)
                    if match:
                        value = match.group(1).strip()
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
    for i, entry in enumerate(new_entries[:3]):  # Afficher les 3 premières
        print(f"\n--- Entrée {i+1} (clés disponibles) ---")
        for k, v in entry.items():
            print(f"  '{k}': {v[:50] if v else 'VIDE'}...")
        
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    
    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)
        print(f"✅ Connecté à la feuille '{WORKSHEET_NAME}'")
    except Exception as e:
        print(f"❌ ERREUR de connexion : {e}")
        return

    # Récupérer toutes les valeurs actuelles
    all_values = sheet.get_all_values()
    
    if not all_values:
        # Si la feuille est vide, créer les en-têtes basés sur les clés de la première entrée
        if new_entries:
            headers = list(new_entries[0].keys())
            # Ajouter Date Ajout si pas présent
            if 'Date Ajout' not in headers:
                headers.append('Date Ajout')
            sheet.append_row(headers)
            all_values = [headers]
            print(f"📝 En-têtes créés : {headers}")
    
    headers = all_values[0]
    
    # Créer un index des colonnes
    column_index = {header: idx for idx, header in enumerate(headers)}
    
    # Identifier les colonnes clés pour les doublons
    nom_idx = None
    lien_idx = None
    
    for header, idx in column_index.items():
        if 'nom' in header.lower():
            nom_idx = idx
        elif 'lien' in header.lower() or 'url' in header.lower():
            lien_idx = idx
    
    # Construire l'ensemble des entrées existantes
    existing_keys = set()
    if nom_idx is not None and lien_idx is not None and len(all_values) > 1:
        for row in all_values[1:]:
            if len(row) > max(nom_idx, lien_idx):
                nom = row[nom_idx].strip() if nom_idx < len(row) else ""
                lien = row[lien_idx].strip() if lien_idx < len(row) else ""
                if nom and lien:
                    existing_keys.add((nom, lien))
    
    # Traiter chaque nouvelle entrée
    added_count = 0
    skipped_count = 0
    date_ajout = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    for entry in new_entries:
        # Construire la ligne selon l'ordre des colonnes
        row = [""] * len(headers)
        
        # Extraire nom et lien pour la détection de doublons
        nom = ""
        lien = ""
        
        # Remplir la ligne
        for header, idx in column_index.items():
            if header == 'Date Ajout':
                row[idx] = date_ajout
            else:
                # Chercher la valeur dans l'entrée
                # D'abord essayer une correspondance exacte
                value = entry.get(header, "")
                
                # Si pas trouvé, essayer avec des variations
                if not value:
                    # Essayer en minuscules
                    for key in entry.keys():
                        if key.lower() == header.lower():
                            value = entry[key]
                            break
                    
                    # Essayer normalisé
                    if not value:
                        norm_header = normalize_key(header)
                        for key in entry.keys():
                            if normalize_key(key) == norm_header:
                                value = entry[key]
                                break
                
                row[idx] = str(value)
                
                # Capturer nom et lien pour la clé
                if 'nom' in header.lower() and value:
                    nom = value
                elif ('lien' in header.lower() or 'url' in header.lower()) and value:
                    lien = value
        
        # Vérifier les doublons
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
        else:
            print(f"⚠️ Entrée ignorée - Nom: '{nom}' | Lien: '{lien}'")
            print(f"   Données complètes de l'entrée : {entry}")
    
    print(f"\n📊 Résumé : {added_count} nouvelle(s) entrée(s), {skipped_count} doublon(s)")
    
    # Analyser les champs non mappés
    if new_entries:
        analyze_unmapped_fields(new_entries[0], headers)


def analyze_unmapped_fields(sample_entry, existing_headers):
    """Analyse les champs qui ne correspondent à aucune colonne"""
    unmapped = []
    normalized_headers = [normalize_key(h) for h in existing_headers]
    
    for key in sample_entry.keys():
        if key not in existing_headers:
            # Vérifier aussi en normalisé
            if normalize_key(key) not in normalized_headers:
                unmapped.append(key)
    
    if unmapped:
        print(f"\n💡 Nouveaux champs détectés qui pourraient être ajoutés comme colonnes :")
        for field in unmapped:
            print(f"   - {field}")
        print("   → Ajoutez simplement ces colonnes dans votre Google Sheet pour les capturer automatiquement")


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
