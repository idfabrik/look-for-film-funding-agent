#!/bin/bash

# Aller dans le bon dossier
cd /home/www-data/look-for-film-funding-agent

# Créer le dossier logs s'il n'existe pas
mkdir -p logs

# Activer l'environnement virtuel
echo "$(date): Activation de l'environnement virtuel" >> logs/crew.log
source venv/bin/activate

# Vérifier que l'environnement virtuel est bien activé
echo "$(date): VIRTUAL_ENV: ${VIRTUAL_ENV:-'NON DEFINI'}" >> logs/crew.log
echo "$(date): Chemin Python après activation venv: $(which python)" >> logs/crew.log

# Charger les variables d'environnement
if [ -f ".env" ]; then
    echo "$(date): Chargement du fichier .env" >> logs/crew.log
    set -a
    source .env
    set +a
    
    # DEBUG SPECIFIQUE SMTP
    echo "$(date): === DEBUG VARIABLES SMTP ===" >> logs/crew.log
    echo "SMTP_SERVER: ${SMTP_SERVER:-'NON DEFINI'}" >> logs/crew.log
    echo "SMTP_PORT: ${SMTP_PORT:-'NON DEFINI'}" >> logs/crew.log  
    echo "SMTP_USER: ${SMTP_USER:-'NON DEFINI'}" >> logs/crew.log
    echo "SMTP_PASSWORD: ${SMTP_PASSWORD:+PRESENT}" >> logs/crew.log
    echo "$(date): === FIN DEBUG SMTP ===" >> logs/crew.log
fi

# Exporter explicitement les variables SMTP
export SMTP_SERVER
export SMTP_PORT  
export SMTP_USER
export SMTP_PASSWORD

# Vérifier la version de Python utilisée
echo "$(date): Version Python: $(python --version)" >> logs/crew.log
echo "$(date): Chemin Python: $(which python)" >> logs/crew.log
echo "$(date): Version Python3: $(python3 --version)" >> logs/crew.log
echo "$(date): Chemin Python3: $(which python3)" >> logs/crew.log

# Exécuter le script avec python3
echo "$(date): 🚀 Démarrage du script avec python3" >> logs/crew.log
python3 crew.py >> logs/crew.log 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "$(date): ✅ Script terminé avec succès" >> logs/crew.log
else
    echo "$(date): ❌ Script terminé avec erreur (code: $EXIT_CODE)" >> logs/crew.log
fi

# Désactiver l'environnement virtuel
deactivate
