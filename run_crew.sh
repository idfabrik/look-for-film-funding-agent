#!/bin/bash

# Aller dans le bon dossier
cd /home/www-data/look-for-film-funding-agent

# Créer le dossier logs s'il n'existe pas
mkdir -p logs

# Activer l'environnement virtuel
echo "$(date): Activation de l'environnement virtuel" >> logs/crew.log
source venv/bin/activate

# Charger les variables d'environnement
if [ -f ".env" ]; then
    echo "$(date): Chargement du fichier .env" >> logs/crew.log
    set -a
    source .env
    set +a
fi

# Exécuter le script
echo "$(date): 🚀 Démarrage du script avec environnement virtuel activé" >> logs/crew.log
python crew.py >> logs/crew.log 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "$(date): ✅ Script terminé avec succès" >> logs/crew.log
else
    echo "$(date): ❌ Script terminé avec erreur (code: $EXIT_CODE)" >> logs/crew.log
fi

# Désactiver l'environnement virtuel
deactivate
