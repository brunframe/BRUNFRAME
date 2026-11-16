"""Accès commun au pipeline : Sheet en mode réel, fichiers locaux en mode test."""
from __future__ import annotations

import csv
import json

from . import config

FICHIER_TEST = config.SORTIES_TEST / "prospects.json"


def cle_categorie(label: str) -> str:
    for cle, c in config.CATEGORIES.items():
        if c["label"] == label or cle == label:
            return cle
    return "epicerie"


def exiger_sheet():
    if not config.PIPELINE_SHEET_ID:
        raise RuntimeError("PIPELINE_SHEET_ID absent de .env : lancez d'abord « python init_sheet.py ».")


def classeur():
    from .google_api import Classeur
    exiger_sheet()
    return Classeur(config.PIPELINE_SHEET_ID)


def charger_prospects(args, c=None) -> list[dict]:
    """En test, la chaîne passe par sorties/test/prospects.json (écrit par prospects.py --test) :
    on valide tout sans toucher au Sheet."""
    if args.test and FICHIER_TEST.exists():
        return json.loads(FICHIER_TEST.read_text(encoding="utf-8"))
    if args.hors_ligne:
        raise RuntimeError("Lancez d'abord « python prospects.py --hors-ligne ».")
    _, lignes = (c or classeur()).lire("Prospects")
    return lignes


def enregistrer_test(lignes: list[dict], nom: str = "prospects"):
    config.SORTIES_TEST.mkdir(parents=True, exist_ok=True)
    (config.SORTIES_TEST / f"{nom}.json").write_text(
        json.dumps(lignes, ensure_ascii=False, indent=1), encoding="utf-8")
    entetes = config.ONGLETS["Prospects"]
    with (config.SORTIES_TEST / f"{nom}.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=entetes, extrasaction="ignore", delimiter=";")
        w.writeheader()
        w.writerows(lignes)


def liste_noire(args, c=None) -> list[dict]:
    if args.hors_ligne:
        from .listenoire import entrees_feuille, entrees_gmail
        demo = json.loads((config.FIXTURES / "gmail_demo.json").read_text(encoding="utf-8"))
        return (list(entrees_gmail(demo["fils"], "demo@brunframe.test").values())
                + entrees_feuille(demo["mes_appels"], "Mes appels de 14h (démo)"))
    fichier = config.SORTIES_TEST / "liste_noire.csv"
    if args.test and fichier.exists():  # écrit par liste_noire.py --test
        with fichier.open(encoding="utf-8-sig") as f:
            return list(csv.DictReader(f, delimiter=";"))
    _, lignes = (c or classeur()).lire("Liste noire")
    return lignes


def entier(v, defaut=0) -> int:
    try:
        return int(float(str(v).replace(",", ".")))
    except (TypeError, ValueError):
        return defaut


def flottant(v, defaut=0.0) -> float:
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return defaut
