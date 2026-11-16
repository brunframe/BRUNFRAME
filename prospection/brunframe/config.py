"""Configuration : chemins, variables d'environnement, cibles, créneaux.

Les clés et identifiants viennent uniquement de `.env` (jamais du code).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent
load_dotenv(BASE / ".env")

LOGS = BASE / "logs"
STATE = BASE / "state"
SITE = BASE / "site"
CAPTURES = BASE / "captures" / "maquettes"
SORTIES_TEST = BASE / "sorties" / "test"
FIXTURES = BASE / "fixtures"
GABARITS = BASE / "gabarits"
PERSONNALISATION = BASE / "personnalisation"


def env(nom: str, defaut: str = "") -> str:
    return os.environ.get(nom, defaut).strip()


# --- Accès (tous dans .env) ---------------------------------------------
PLACES_KEY = env("GOOGLE_PLACES_API_KEY")
PIPELINE_SHEET_ID = env("PIPELINE_SHEET_ID")
GMAIL_COMPTE = env("GMAIL_COMPTE", "brunframe@gmail.com").lower()
OAUTH_CLIENT = BASE / env("OAUTH_CLIENT_FILE", "state/client_secret.json")
OAUTH_TOKEN = STATE / "token.json"
FEUILLES_A_EXCLURE = [s for s in env("FEUILLES_A_EXCLURE").split(",") if s.strip()]
DEMO_BASE_URL = env("DEMO_BASE_URL", "https://brunframe-demo.pages.dev").rstrip("/")
CF_PROJET = env("CLOUDFLARE_PAGES_PROJECT", "brunframe-demo")
CHROMIUM_PATH = env("CHROMIUM_PATH")
CLAUDE_CMD = env("CLAUDE_CMD", "claude")
ACCORD_CASHER = {s.strip() for s in env("ACCORD_CASHER_PLACE_IDS").split(",") if s.strip()}
CLIENTS_SIGNES = int(env("CLIENTS_SIGNES", "0") or 0)
PLACES_PLAFOND_MENSUEL = int(env("PLACES_PLAFOND_MENSUEL", "900") or 900)
APPELS_DISPOSITION = env("APPELS_DISPOSITION", "colonnes")  # colonnes | lignes

ANDY_TEL = "06 30 83 59 78"
SHEMTOV_SITE = "shemtov-foch.netlify.app"

# --- Critères (section 2 du brief) --------------------------------------
MIN_AVIS = 30
MIN_NOTE = 4.3
JOURS_AVANT_RECONTACT = 60
JOURS_AVANT_RETRAIT = 21
JOURS_FRAICHEUR_PLACES = 30
APPELS_PAR_JOUR = 10
MAX_TENTATIVES = 3

# Créneaux d'appel d'Andy (lun-ven) en minutes depuis minuit.
CRENEAUX_ANDY = [(14 * 60, 14 * 60 + 30), (16 * 60 + 15, 18 * 60 + 30)]

# --- Catégories ---------------------------------------------------------
# requete : texte envoyé à Places ; rush : heures de pointe (minutes) ;
# couleurs : palette par défaut de la maquette (remplaçable par commerce).
CATEGORIES: dict[str, dict] = {
    "boucherie": {
        "label": "Boucherie-charcuterie", "requete": "boucherie charcuterie",
        "rush": [(10 * 60, 12 * 60 + 30), (17 * 60, 19 * 60)],
        "couleurs": {"fond": "#2B0E12", "accent": "#B3263A", "clair": "#F7ECEC"},
        "geste": "pendant que vous servez au comptoir",
    },
    "traiteur": {
        "label": "Traiteur", "requete": "traiteur",
        "rush": [(11 * 60, 13 * 60 + 30), (17 * 60, 19 * 60 + 30)],
        "couleurs": {"fond": "#14261C", "accent": "#2F7D4F", "clair": "#EDF4EF"},
        "geste": "en plein service",
    },
    "patisserie": {
        "label": "Pâtisserie", "requete": "pâtisserie",
        "rush": [(11 * 60 + 30, 13 * 60), (16 * 60 + 30, 18 * 60 + 30)],
        "couleurs": {"fond": "#2A1420", "accent": "#C2457A", "clair": "#F9EDF2"},
        "geste": "les mains dans la pâte",
    },
    "chocolatier": {
        "label": "Chocolatier", "requete": "chocolatier",
        "rush": [(11 * 60 + 30, 13 * 60), (17 * 60, 19 * 60)],
        "couleurs": {"fond": "#22140D", "accent": "#8A5230", "clair": "#F4EDE8"},
        "geste": "en plein travail du chocolat",
    },
    "fromagerie": {
        "label": "Fromagerie", "requete": "fromagerie",
        "rush": [(11 * 60 + 30, 13 * 60), (17 * 60 + 30, 19 * 60)],
        "couleurs": {"fond": "#262010", "accent": "#B8860B", "clair": "#F7F2E2"},
        "geste": "pendant que vous coupez au comptoir",
    },
    "caviste": {
        "label": "Caviste", "requete": "caviste cave à vin",
        "rush": [(18 * 60, 19 * 60 + 30)],
        "couleurs": {"fond": "#240C17", "accent": "#7D1D3F", "clair": "#F5EBEF"},
        "geste": "en plein conseil avec un client",
    },
    "epicerie": {
        "label": "Épicerie fine", "requete": "épicerie fine",
        "rush": [(11 * 60 + 30, 13 * 60), (17 * 60 + 30, 19 * 60)],
        "couleurs": {"fond": "#1C2214", "accent": "#5B6B1E", "clair": "#F2F4E8"},
        "geste": "avec du monde en boutique",
    },
    "boulangerie": {
        "label": "Boulangerie", "requete": "boulangerie",
        "rush": [(7 * 60, 9 * 60), (11 * 60 + 30, 13 * 60 + 30), (17 * 60, 19 * 60)],
        "couleurs": {"fond": "#2A1C0E", "accent": "#A8681F", "clair": "#F8F0E4"},
        "geste": "avec la file au comptoir",
    },
}

# --- Quartiers (rectangles lat/lng) -------------------------------------
# niveau 1 = centre (tram ou vélo) ; niveau 2 = quartiers voisins, utilisés
# automatiquement quand le centre ne suffit plus.
QUARTIERS: dict[str, dict] = {
    "Grande Île": {"niveau": 1, "bas": (48.5765, 7.7355), "haut": (48.5870, 7.7560)},
    "Neustadt": {"niveau": 1, "bas": (48.5850, 7.7440), "haut": (48.5960, 7.7680)},
    "Krutenau": {"niveau": 1, "bas": (48.5735, 7.7520), "haut": (48.5815, 7.7650)},
    "Gare": {"niveau": 1, "bas": (48.5790, 7.7240), "haut": (48.5920, 7.7380)},
    "Esplanade": {"niveau": 1, "bas": (48.5700, 7.7600), "haut": (48.5820, 7.7800)},
    "Contades-Orangerie": {"niveau": 2, "bas": (48.5880, 7.7520), "haut": (48.5990, 7.7820)},
    "Neudorf": {"niveau": 2, "bas": (48.5600, 7.7480), "haut": (48.5740, 7.7700)},
    "Bourse-Étoile": {"niveau": 2, "bas": (48.5680, 7.7420), "haut": (48.5770, 7.7560)},
    "Laiterie-Koenigshoffen": {"niveau": 2, "bas": (48.5760, 7.7100), "haut": (48.5850, 7.7300)},
    "Cronenbourg": {"niveau": 2, "bas": (48.5900, 7.7150), "haut": (48.6020, 7.7400)},
    "Montagne-Verte": {"niveau": 2, "bas": (48.5650, 7.7150), "haut": (48.5780, 7.7350)},
}

# --- Onglets du Sheet « BRUNFRAME — Pipeline » -------------------------
TITRE_PIPELINE = "BRUNFRAME — Pipeline"
ONGLETS: dict[str, list[str]] = {
    "Prospects": [
        "place_id", "Nom", "Catégorie", "Quartier", "Adresse", "Téléphone", "Horaires",
        "Site", "État du site", "Note", "Nb avis", "Spécialité 1", "Spécialité 2",
        "Observation", "Meilleur créneau", "Lien Google Maps", "Score", "Slug",
        "Lien maquette", "Capture", "Statut", "Ajouté le", "Vérifié le", "Maquette le",
        "Premier contact", "Retrait prévu", "Dernier appel", "Nb appels", "Prochain appel",
    ],
    "Appels du jour": [],  # disposition « Mes appels de 14h » (voir appels_du_jour.py)
    "Suivi": ["Date", "Type", "Nom", "place_id", "Détail", "Résultat"],
    "Contenus": ["Date", "Format", "Texte", "Score qualité", "Statut", "Lien"],
    "Liste noire": [
        "Clé", "Type", "Nom", "Téléphone", "Site", "Source", "Motif",
        "Dernier contact", "A répondu", "Définitif", "Ajouté le",
    ],
}

RESULTATS = ["RDV pris", "À rappeler", "Pas de réponse", "Non", "Déjà équipé"]

STATUTS_PROTEGES = {"RDV", "Présentation", "Signé"}  # jamais retirés automatiquement
