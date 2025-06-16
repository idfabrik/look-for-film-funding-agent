# test_direct.py
from sheets_utils import send_to_google_sheet

# Test avec une entrée qui a exactement "Nom" et "Lien" (avec majuscules)
test_data = [{
    "Nom": "Test Aide CNC Documentaire 2024",
    "Lien": "https://www.cnc.fr/test-aide-2024",
    "Organisme": "CNC",
    "Pays": "France",
    "Deadline": "31/12/2024",
    "Résumé": "Aide test pour documentaire",
    "Email": "test@cnc.fr",
    "Conditions": "Documentaire en post-production",
    "Catégorie": "Post-production",
    "Année": "2024"
}]

print("🧪 Test d'envoi direct...")
send_to_google_sheet(test_data)
