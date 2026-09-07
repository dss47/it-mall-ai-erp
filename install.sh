#!/bin/bash
set -e

echo "===================================================="
echo "   🛒 IT MALL ENTERPRISE SUITE - 1-CLICK INSTALLER   "
echo "===================================================="

# 1. Vérification Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker n'est pas installé. Veuillez installer Docker avant de continuer."
    exit 1
fi

# 2. Configuration d'environnement
if [ ! -f voice-agent/db.env ]; then
    echo "📝 Création du fichier de configuration à partir du template..."
    cp voice-agent/db.env.example voice-agent/db.env
    echo "⚠️  N'oubliez pas de mettre vos clés API dans voice-agent/db.env !"
fi

# 3. Lancement des conteneurs
echo "🚀 Démarrage de tous les services (Odoo, PostgreSQL, FreePBX, n8n, IA)..."
docker compose up -d

echo ""
echo "===================================================="
echo "✅ Déploiement terminé avec succès !"
echo "👉 ERP Odoo : http://localhost:8069"
echo "👉 Automatisation n8n : http://localhost:5678"
echo "👉 Téléphonie FreePBX : extension *99 active"
echo "===================================================="
