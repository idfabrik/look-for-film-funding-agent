from sheets_utils import send_to_google_sheet

# Test avec les colonnes exactes de votre sheet
test_entry = {
    "Nom": "Test Aide CNC 2024",
    "Organisme": "CNC Test",
    "Pays": "France", 
    "Deadline": "31/12/2024",
    "Lien": "https://test-cnc.fr/aide-123",
    "Résumé": "Aide test pour documentaire",
    "Email": "contact@test-cnc.fr",
    "Conditions": "Documentaire en post-prod",
    "Catégorie": "Post-production",
    "Année": "2024"
}

print("🚀 Test d'envoi d'une entrée...")
send_to_google_sheet([test_entry])
