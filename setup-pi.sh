#!/usr/bin/env bash
set -e

echo "================================================"
echo "  mm-ledger — Setup Raspberry Pi"
echo "================================================"
echo ""

# ── 1. Vérifications ──────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo ">> Installation de Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    echo ">> Docker installé. Déconnecte-toi et reconnecte-toi, puis relance ce script."
    exit 0
fi

if ! docker compose version &>/dev/null; then
    echo "ERREUR: docker compose non disponible. Mets à jour Docker."
    exit 1
fi

# ── 2. Configuration VPN ─────────────────────────────────────────────────────
echo ""
echo ">> Configuration du VPN WireGuard"
echo ""

if [ -z "${WG_HOST:-}" ]; then
    echo "Pour accéder à mm-ledger depuis l'extérieur, il faut une adresse publique."
    echo "Options :"
    echo "  1. IP publique fixe (ex: 82.123.45.67)"
    echo "  2. Domaine DynDNS gratuit (ex: mon-rasp.duckdns.org)"
    echo ""
    read -p "Ton IP publique ou domaine DynDNS : " WG_HOST
fi

if [ -z "${WG_PASSWORD:-}" ]; then
    read -s -p "Mot de passe pour l'admin VPN (interface web) : " WG_PASSWORD
    echo ""
fi

# Générer le hash bcrypt pour wg-easy
WG_PASSWORD_HASH=$(docker run --rm ghcr.io/wg-easy/wg-easy wgpw "$WG_PASSWORD" 2>/dev/null || echo "")

# ── 3. Fichier .env ──────────────────────────────────────────────────────────
cat > .env << EOF
# VPN
WG_HOST=${WG_HOST}
WG_PASSWORD_HASH=${WG_PASSWORD_HASH}

# IBKR (optionnel — décommente si tu utilises Interactive Brokers)
# IBKR_USERNAME=
# IBKR_PASSWORD=
# IBKR_TRADING_MODE=live
EOF

echo ""
echo ">> .env créé"

# ── 4. Ouvrir le port sur le routeur ─────────────────────────────────────────
echo ""
echo "================================================"
echo "  IMPORTANT : Ouvre le port UDP 51820 sur ton"
echo "  routeur (redirection vers l'IP locale du Pi)"
echo "================================================"
echo ""
LOCAL_IP=$(hostname -I | awk '{print $1}')
echo "  IP locale du Pi : ${LOCAL_IP}"
echo "  Port à rediriger : UDP 51820 → ${LOCAL_IP}:51820"
echo ""
read -p "Appuie sur Entrée quand c'est fait..."

# ── 5. Lancer ─────────────────────────────────────────────────────────────────
echo ""
echo ">> Construction et lancement de mm-ledger + VPN..."
docker compose --profile vpn up -d --build

echo ""
echo "================================================"
echo "  C'est lancé !"
echo ""
echo "  mm-ledger  : http://${LOCAL_IP}:8000"
echo "  Admin VPN  : http://${LOCAL_IP}:51821"
echo ""
echo "  Pour ajouter un client VPN :"
echo "  1. Ouvre http://${LOCAL_IP}:51821"
echo "  2. Connecte-toi avec ton mot de passe VPN"
echo "  3. Clique 'New Client'"
echo "  4. Scanne le QR code avec l'app WireGuard"
echo "     sur ton téléphone"
echo ""
echo "  Une fois connecté au VPN, accède à mm-ledger"
echo "  sur http://10.8.0.1:8000"
echo "================================================"
