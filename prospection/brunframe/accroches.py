"""Accroches réelles selon le calendrier (jamais d'urgence inventée)."""
from __future__ import annotations

import datetime as dt


def paques(annee: int) -> dt.date:
    """Dimanche de Pâques (algorithme de Meeus/Jones/Butcher)."""
    a, b, c = annee % 19, annee // 100, annee % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mois = (h + l - 7 * m + 114) // 31
    jour = ((h + l - 7 * m + 114) % 31) + 1
    return dt.date(annee, mois, jour)


ACCROCHES = {
    "fetes": {
        "titre": "Commandes de fêtes", "objet": "vos commandes de fêtes",
        "bouton": "Commander pour les fêtes", "pour": "pour les fêtes",
        "phrase": "ils commandent pour les fêtes",
    },
    "galette": {
        "titre": "Galettes des rois", "objet": "vos galettes des rois",
        "bouton": "Réserver une galette", "pour": "pour la galette des rois",
        "phrase": "ils réservent leur galette des rois",
    },
    "saint_valentin": {
        "titre": "Saint-Valentin", "objet": "la Saint-Valentin",
        "bouton": "Commander pour la Saint-Valentin", "pour": "pour la Saint-Valentin",
        "phrase": "ils commandent pour la Saint-Valentin",
    },
    "paques": {
        "titre": "Pâques", "objet": "vos commandes de Pâques",
        "bouton": "Commander pour Pâques", "pour": "pour Pâques",
        "phrase": "ils commandent pour Pâques",
    },
    "general": {
        "titre": "Commande à l'avance", "objet": "vos commandes",
        "bouton": "Commander à l'avance", "pour": "à l'avance",
        "phrase": "ils commandent à l'avance",
    },
}

CATS_GALETTE = {"boulangerie", "patisserie"}
CATS_VALENTIN = {"chocolatier", "patisserie", "caviste", "fromagerie", "traiteur", "epicerie"}
CATS_PAQUES = {"chocolatier", "patisserie", "boulangerie", "boucherie", "traiteur", "epicerie"}


def cle_accroche(jour: dt.date, categorie: str) -> str:
    m, d = jour.month, jour.day
    if (m == 11) or (m == 12 and d <= 20):
        return "fetes"
    if (m == 12 and d > 20) or m == 1:
        return "galette" if categorie in CATS_GALETTE else "general"
    if m == 2 and d <= 14:
        return "saint_valentin" if categorie in CATS_VALENTIN else "general"
    p = paques(jour.year)
    if dt.date(jour.year, 3, 1) <= jour <= p + dt.timedelta(days=1):
        return "paques" if categorie in CATS_PAQUES else "general"
    return "general"


def accroche(jour: dt.date, categorie: str) -> dict:
    cle = cle_accroche(jour, categorie)
    return {"cle": cle, **ACCROCHES[cle]}
