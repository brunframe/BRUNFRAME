"""Journal de chaque exécution (logs/) et erreur écrite en clair dans l'onglet Suivi."""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import traceback

from . import config


def ouvrir(nom_script: str) -> logging.Logger:
    for flux in (sys.stdout, sys.stderr):  # Planificateur Windows : console en cp1252
        if hasattr(flux, "reconfigure"):
            flux.reconfigure(encoding="utf-8", errors="replace")
    config.LOGS.mkdir(parents=True, exist_ok=True)
    fichier = config.LOGS / f"{nom_script}_{dt.date.today():%Y-%m-%d}.log"
    log = logging.getLogger(nom_script)
    log.setLevel(logging.INFO)
    if not log.handlers:
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S")
        for h in (logging.FileHandler(fichier, encoding="utf-8"), logging.StreamHandler(sys.stdout)):
            h.setFormatter(fmt)
            log.addHandler(h)
    return log


def arguments(description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--test", action="store_true",
                   help="n'écrit rien dans le Sheet, ne déploie rien, n'envoie rien : sorties dans sorties/test/")
    p.add_argument("--hors-ligne", action="store_true",
                   help="données de démonstration locales (fixtures/), implique --test")
    return p


def signaler_erreur(nom_script: str, erreur: BaseException):
    """Écrit l'erreur dans Suivi (si le Sheet est joignable)."""
    if not config.PIPELINE_SHEET_ID:
        return
    try:
        from .google_api import Classeur
        c = Classeur(config.PIPELINE_SHEET_ID)
        c.ajouter("Suivi", config.ONGLETS["Suivi"], [{
            "Date": f"{dt.datetime.now():%Y-%m-%d %H:%M}", "Type": "erreur", "Nom": nom_script,
            "Détail": f"{type(erreur).__name__} : {erreur}"[:400],
            "Résultat": "Le script s'est arrêté. Voir logs/ sur le PC.",
        }])
    except Exception:  # le Sheet lui-même est peut-être la cause
        pass


def lancer(nom_script: str, principal, args) -> int:
    log = ouvrir(nom_script)
    if getattr(args, "hors_ligne", False):
        args.test = True
    mode = "HORS LIGNE (démo)" if getattr(args, "hors_ligne", False) else ("TEST" if args.test else "RÉEL")
    log.info("=== %s — mode %s ===", nom_script, mode)
    try:
        principal(args, log)
        log.info("=== terminé ===")
        return 0
    except KeyboardInterrupt:
        log.warning("interrompu")
        return 130
    except Exception as e:
        log.error("ÉCHEC : %s\n%s", e, traceback.format_exc())
        if not args.test:
            signaler_erreur(nom_script, e)
        return 1


def noter_suivi(classeur, type_: str, nom: str, detail: str, resultat: str = "", place_id: str = ""):
    classeur.ajouter("Suivi", config.ONGLETS["Suivi"], [{
        "Date": f"{dt.datetime.now():%Y-%m-%d %H:%M}", "Type": type_, "Nom": nom,
        "place_id": place_id, "Détail": detail, "Résultat": resultat}])
