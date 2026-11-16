"""Liste noire : destinataires du dossier Envoyés de brunframe@gmail.com, commerces
de « Mes appels de 14h » et « stop » → onglet Liste noire.

Les lignes ajoutées à la main dans l'onglet sont conservées. Ne supprime jamais rien.

    python liste_noire.py --test       # lit Gmail et les feuilles, écrit sorties/test/liste_noire.csv
    python liste_noire.py              # met à jour l'onglet Liste noire
"""
from __future__ import annotations

import csv
import datetime as dt
import sys

from brunframe import config, journal
from brunframe.listenoire import entrees_feuille, entrees_gmail, est_oui

ENTETES = config.ONGLETS["Liste noire"]


def lire_gmail(log) -> list[dict]:
    from brunframe.google_api import executer, service
    gm = service("gmail", "v1")
    ids, jeton = [], None
    while True:
        r = executer(gm.users().threads().list(userId="me", q="in:sent", maxResults=100, pageToken=jeton))
        ids += [t["id"] for t in r.get("threads", [])]
        jeton = r.get("nextPageToken")
        if not jeton:
            break
    log.info("Gmail : %d fils dans Envoyés", len(ids))
    fils = []
    for i, tid in enumerate(ids, 1):
        fils.append(executer(gm.users().threads().get(
            userId="me", id=tid, format="metadata",
            metadataHeaders=["From", "To", "Cc", "Bcc", "Subject", "Date"])))
        if i % 50 == 0:
            log.info("  %d/%d fils lus", i, len(ids))
    return fils


def fusionner(existantes: list[dict], nouvelles: list[dict]) -> tuple[list[dict], int]:
    """Clé = (Type, Clé). Garde les lignes manuelles ; un « oui » ne redevient jamais « non »."""
    index = {(l.get("Type", ""), str(l.get("Clé", "")).lower()): l for l in existantes}
    ajoutees = 0
    for n in nouvelles:
        k = (n["Type"], str(n["Clé"]).lower())
        if k not in index:
            n["Ajouté le"] = str(dt.date.today())
            index[k] = n
            ajoutees += 1
            continue
        e = index[k]
        for champ in ("Nom", "Téléphone", "Site"):
            e[champ] = e.get(champ) or n.get(champ, "")
        if n.get("Dernier contact", "") > str(e.get("Dernier contact", "")):
            e["Dernier contact"] = n["Dernier contact"]
        for champ in ("A répondu", "Définitif"):
            if est_oui(n.get(champ)) and not est_oui(e.get(champ)):
                e[champ] = "oui"
                e["Motif"] = n["Motif"]
    return list(index.values()), ajoutees


def principal(args, log):
    nouvelles: list[dict] = []
    if args.hors_ligne:
        import json
        demo = json.loads((config.FIXTURES / "gmail_demo.json").read_text(encoding="utf-8"))
        nouvelles += list(entrees_gmail(demo["fils"], "demo@brunframe.test").values())
        nouvelles += entrees_feuille(demo["mes_appels"], "Mes appels de 14h (démo)")
        existantes = []
    else:
        from brunframe.google_api import Classeur
        nouvelles += list(entrees_gmail(lire_gmail(log), config.GMAIL_COMPTE).values())
        for fid in config.FEUILLES_A_EXCLURE:
            f = Classeur(fid)
            for onglet in f.onglets():
                n = entrees_feuille(f.valeurs(f"'{onglet}'"), "Mes appels de 14h")
                if n:
                    log.info("feuille %s / %s : %d commerces", fid, onglet, len(n))
                nouvelles += n
        existantes = []
        if config.PIPELINE_SHEET_ID:
            _, existantes = Classeur(config.PIPELINE_SHEET_ID).lire("Liste noire")
    toutes, ajoutees = fusionner(existantes, nouvelles)
    definitifs = sum(1 for l in toutes if est_oui(l.get("Définitif")))
    repondus = sum(1 for l in toutes if est_oui(l.get("A répondu")))
    log.info("Liste noire : %d entrées (%d nouvelles, %d définitives, %d ont répondu)",
             len(toutes), ajoutees, definitifs, repondus)

    if args.test:
        config.SORTIES_TEST.mkdir(parents=True, exist_ok=True)
        sortie = config.SORTIES_TEST / "liste_noire.csv"
        with sortie.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=ENTETES, extrasaction="ignore", delimiter=";")
            w.writeheader()
            w.writerows(toutes)
        log.info("TEST : rien écrit dans le Sheet. Aperçu : %s", sortie)
        return
    from brunframe.google_api import Classeur
    c = Classeur(config.PIPELINE_SHEET_ID)
    c.assurer_onglet("Liste noire", ENTETES)
    toutes.sort(key=lambda l: (l.get("Source", ""), str(l.get("Nom", "")).lower()))
    c.remplacer("Liste noire", ENTETES, toutes)
    log.info("onglet Liste noire mis à jour")


if __name__ == "__main__":
    a = journal.arguments(__doc__).parse_args()
    sys.exit(journal.lancer("liste_noire", principal, a))
