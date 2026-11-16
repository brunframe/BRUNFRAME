"""Prépare le Google Sheet « BRUNFRAME — Pipeline » : crée le classeur s'il n'existe
pas, ajoute les 5 onglets et leurs en-têtes, vérifie l'accès aux feuilles d'appels.

    python init_sheet.py --test   # montre ce qui serait fait
    python init_sheet.py          # le fait (ouvre le navigateur la 1re fois pour l'OAuth)
"""
from __future__ import annotations

import sys

from brunframe import config, journal


def principal(args, log):
    if args.hors_ligne:
        for onglet, entetes in config.ONGLETS.items():
            log.info("onglet « %s » : %s", onglet, ", ".join(entetes) or "(disposition des appels)")
        return
    from brunframe.google_api import Classeur, creer_classeur

    sheet_id = config.PIPELINE_SHEET_ID
    if not sheet_id:
        if args.test:
            log.info("TEST : créerait le classeur « %s »", config.TITRE_PIPELINE)
            return
        sheet_id = creer_classeur(config.TITRE_PIPELINE)
        fichier_env = config.BASE / ".env"
        with fichier_env.open("a", encoding="utf-8") as f:
            f.write(f"\nPIPELINE_SHEET_ID={sheet_id}\n")
        log.info("Classeur créé : https://docs.google.com/spreadsheets/d/%s (ID ajouté à .env)", sheet_id)

    c = Classeur(sheet_id)
    existants = c.onglets()
    for onglet, entetes in config.ONGLETS.items():
        if args.test:
            log.info("TEST : onglet « %s » %s", onglet, "présent" if onglet in existants else "à créer")
            continue
        if c.assurer_onglet(onglet, entetes):
            log.info("onglet « %s » créé", onglet)
    if not args.test:
        # supprime la feuille vide d'origine si elle existe encore
        for vide in ("Feuille 1", "Sheet1", "Feuille1"):
            if vide in c.onglets() and len(c.onglets()) > 1:
                c.batch([{"deleteSheet": {"sheetId": c.onglets()[vide]}}])

    for fid in config.FEUILLES_A_EXCLURE:
        try:
            meta = Classeur(fid).onglets()
            log.info("feuille d'appels lisible (%s) : onglets %s", fid, ", ".join(meta))
        except Exception as e:  # accès non partagé avec le compte OAuth
            log.warning("feuille %s illisible (%s). Partagez-la en lecture avec %s.",
                        fid, type(e).__name__, config.GMAIL_COMPTE)
    log.info("Sheet : https://docs.google.com/spreadsheets/d/%s", sheet_id)


if __name__ == "__main__":
    a = journal.arguments(__doc__).parse_args()
    sys.exit(journal.lancer("init_sheet", principal, a))
