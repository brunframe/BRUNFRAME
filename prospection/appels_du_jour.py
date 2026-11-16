"""Chaque matin à 7h : 10 commerces à appeler dans l'onglet « Appels du jour »,
au format de « Mes appels de 14h » (un commerce par colonne, menu Résultat).

Avant de remplacer la liste, les résultats de la veille (colonne/ligne Résultat,
la seule qu'Andy remplit) sont archivés dans Suivi et reportés dans Prospects ;
les « Non » partent en Liste noire.

    python appels_du_jour.py --test          # liste dans sorties/test/appels_du_jour.csv, rien écrit
    python appels_du_jour.py                 # archive la veille, écrit la liste du jour
"""
from __future__ import annotations

import csv
import datetime as dt
import sys

from brunframe import accroches, config, journal
from brunframe import pipeline as pl
from brunframe.horaires import JOURS, quand_appeler
from brunframe.listenoire import ListeNoire
from brunframe.textes import lire_date, normaliser, note_fr, possessif, trouver_tels

ONGLET = "Appels du jour"
CHAMPS = [
    "Appel", "Numéro", "Quand appeler", "Demande à parler à", "Leur problème", "0. Tu te présentes",
    "1. Compliment + problème", "2. Ta question, puis tu te tais", "3. Tu proposes", "Lien de la maquette",
    "Si on te demande le prix", "Objection 1", "Objection 2", "Objection 3", "Résultat", "Réf. (ne pas modifier)",
]


# --- Archivage des résultats -------------------------------------------------

def lire_liste(c) -> list[dict]:
    """Relit l'onglet quelle que soit sa disposition. [{champ: valeur}]"""
    v = c.valeurs(f"'{ONGLET}'") if ONGLET in c.onglets() else []
    if not v:
        return []
    if v[0] and v[0][0] == "Appel" and len(v) > 1 and v[1][:1] == ["Numéro"]:  # colonnes
        etiquettes = [l[0] if l else "" for l in v]
        n = max(len(l) for l in v)
        return [{etiquettes[i]: (v[i][j] if j < len(v[i]) else "") for i in range(len(v))} for j in range(1, n)]
    entetes = v[0]
    return [{e: (l[j] if j < len(l) else "") for j, e in enumerate(entetes)} for l in v[1:]]


def statut_apres(resultat: str) -> tuple[str, int | None, bool]:
    """(statut, jours avant rappel, liste noire ?)"""
    r = normaliser(resultat)
    if not r:
        return "", None, False
    if r.startswith(("rdv", "rendez", "oui", "maquette ok")):
        return "RDV", None, False
    if r.startswith(("deja equipe", "deja un site")):
        return "Non", None, True
    if r.startswith(("non", "stop", "pas interesse")):
        return "Non", None, True
    if r.startswith("pas de reponse") or "repondeur" in r or "messagerie" in r:
        return "À rappeler", 1, False
    return "À rappeler", 2, False  # « À rappeler », « rappeler jeudi 17h »…


def jour_ouvre(depuis: dt.date, n: int) -> dt.date:
    d = depuis
    while n > 0:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def archiver(c, prospects: list[dict], log, jour: dt.date) -> int:
    precedente = lire_liste(c)
    if not precedente:
        return 0
    _, suivi = c.lire("Suivi")
    deja = {(s.get("place_id"), s.get("Résultat"), s.get("Détail")) for s in suivi if s.get("Type") == "appel"}
    par_id = {p["place_id"]: p for p in prospects}
    suivis, noirs, maj = [], [], {}
    for e in precedente:
        pid, resultat = e.get("Réf. (ne pas modifier)", ""), str(e.get("Résultat", "")).strip()
        if not pid or not resultat:
            continue
        date_liste = lire_date(e.get("Date liste")) or jour_precedent(jour)
        detail = f"Liste du {date_liste}"
        nom = str(e.get("Appel", "")).split(". ", 1)[-1]
        if (pid, resultat, detail) in deja:
            continue
        suivis.append({"Date": str(jour), "Type": "appel", "Nom": nom, "place_id": pid,
                       "Détail": detail, "Résultat": resultat})
        p = par_id.get(pid)
        statut, rappel, noir = statut_apres(resultat)
        if p:
            p["Dernier appel"] = str(date_liste)
            p["Nb appels"] = pl.entier(p.get("Nb appels")) + 1
            p["Premier contact"] = p.get("Premier contact") or p["Dernier appel"]
            if not p.get("Retrait prévu"):
                debut = lire_date(p["Premier contact"]) or date_liste
                p["Retrait prévu"] = str(debut + dt.timedelta(days=config.JOURS_AVANT_RETRAIT))
            if statut == "À rappeler" and p["Nb appels"] >= config.MAX_TENTATIVES and normaliser(resultat).startswith("pas de reponse"):
                statut, rappel = "Injoignable", None
            p["Statut"] = statut or p.get("Statut", "")
            p["Prochain appel"] = str(jour_ouvre(date_liste, rappel)) if rappel else ""
            maj[pid] = p
        if noir:
            noirs.append({"Clé": pid, "Type": "place_id", "Nom": nom,
                          "Téléphone": " / ".join(trouver_tels(e.get("Numéro", ""))),
                          "Site": "", "Source": "Appels du jour", "Motif": f"« {resultat} » au téléphone",
                          "Dernier contact": str(date_liste), "A répondu": "oui", "Définitif": "oui",
                          "Ajouté le": str(jour)})
    c.ajouter("Suivi", config.ONGLETS["Suivi"], suivis)
    c.ajouter("Liste noire", config.ONGLETS["Liste noire"], noirs)
    if maj:
        c.mettre_a_jour("Prospects", config.ONGLETS["Prospects"], list(maj.values()))
    log.info("veille archivée : %d résultats, %d en liste noire", len(suivis), len(noirs))
    return len(suivis)


def jour_precedent(jour: dt.date) -> dt.date:
    """La liste archivée date du dernier jour ouvré avant aujourd'hui."""
    d = jour - dt.timedelta(days=1)
    while d.weekday() > 4:
        d -= dt.timedelta(days=1)
    return d


# --- Sélection et rédaction ----------------------------------------------------

def selectionner(prospects: list[dict], ln: ListeNoire, jour: dt.date) -> list[dict]:
    a_rappeler, nouveaux = [], []
    for p in prospects:
        if not p.get("Lien maquette") or p.get("Statut") not in ("Maquette prête", "À rappeler"):
            continue
        if ln.motif(p.get("Nom", ""), p.get("Téléphone", ""), p.get("Site", ""), p.get("place_id", "")):
            continue
        prochain = lire_date(p.get("Prochain appel"))
        if prochain and prochain > jour:
            continue
        (a_rappeler if p.get("Statut") == "À rappeler" else nouveaux).append(p)
    a_rappeler.sort(key=lambda p: p.get("Prochain appel", ""))
    nouveaux.sort(key=lambda p: -pl.flottant(p.get("Score")))
    return (a_rappeler + nouveaux)[:config.APPELS_PAR_JOUR]


def vendredi_ou_samedi(jour: dt.date) -> str:
    d = jour + dt.timedelta(days=1)
    while d.weekday() not in (4, 5):
        d += dt.timedelta(days=1)
    return "vendredi" if d.weekday() == 4 else "samedi"


def colonne(i: int, p: dict, jour: dt.date) -> dict:
    cat = pl.cle_categorie(p.get("Catégorie", ""))
    acc = accroches.accroche(jour, cat)
    etat = p.get("État du site", "")
    specs = [s for s in (p.get("Spécialité 1"), p.get("Spécialité 2")) if s]
    note, avis = note_fr(p.get("Note")), pl.entier(p.get("Nb avis"))
    passage = vendredi_ou_samedi(jour)
    rappel = p.get("Statut") == "À rappeler"
    adresse = str(p.get("Adresse", "")).split(",")[0]

    probleme = f"{avis} avis à {note}. {etat or 'Aucun site'}."
    if etat.startswith(("Aucun site", "Seulement")):
        probleme += f" Pour commander {acc['pour']}, il faut appeler, souvent pendant le service."
    elif etat.startswith("Site cassé"):
        probleme += " Le bouton « Site web » de sa fiche Google ne mène nulle part."
    else:
        probleme += f" Aucun moyen de commander {acc['pour']} en ligne : tout passe par le téléphone."

    if rappel:
        dernier = lire_date(p.get("Dernier appel"))
        quand_dernier = f" {JOURS[dernier.weekday()]}" if dernier and (jour - dernier).days < 7 else ""
        intro = (f"« Bonjour, c'est Andy, de BRUNFRAME. Je vous ai appelé{quand_dernier} pour la page que "
                 f"j'ai faite pour {p['Nom']}. Vous avez un instant ? »")
    else:
        intro = (f"« Bonjour, c'est Andy, de BRUNFRAME. J'ai fait le site de Shemtov, rue du Maréchal-Foch, "
                 f"et j'ai préparé une page pour {p['Nom']}. Je vous prends 30 secondes ? »")

    geste = config.CATEGORIES.get(cat, {}).get("geste", "pendant le service")
    question = (f"« Pour {acc['pour'].removeprefix('pour ')}, vos clients commandent comment ? » "
                f"Après sa réponse : « Et quand le téléphone sonne {geste}, vous faites comment ? »")
    if acc["cle"] == "general":
        question = (f"« Aujourd'hui, un client qui veut commander à l'avance, il fait comment ? » "
                    f"Après sa réponse : « Et quand le téléphone sonne {geste}, vous faites comment ? »")

    contenu = ", ".join([possessif(specs[0]) if specs else "vos spécialités", "vos horaires"])
    propose = (f"« Je l'ai faite pour vous : {contenu}, et les commandes {acc['pour']} qui arrivent sur votre "
               f"WhatsApp, pas au téléphone. Je passe vous la montrer {passage}, 5 minutes, à un moment calme ? "
               "Si ça ne vous plaît pas, on en reste là. »")

    prix = ("« 550 € avec la commande sur WhatsApp, payés à la mise en ligne, et seulement si le site vous plaît. "
            "Ou rien au départ : 49 € par mois sur un an, ou 59 € par mois sans engagement. "
            "Ensuite le domaine, 10 à 20 € par an, à votre nom. »")
    if config.CLIENTS_SIGNES < 3:
        prix += (" Si c'est le moment : « Vous seriez parmi mes 3 premiers : rien à payer avant la mise en ligne, "
                 "et rien du tout si le site final ne vous plaît pas. En échange, un avis Google. »")

    if etat.startswith(("Aucun site", "Seulement")):
        obj1 = ("« J'ai Facebook / Instagram »\n« Parfait, on met le lien. La page sert à prendre les commandes "
                "sans que vous ayez à décrocher. Vous en prenez combien par téléphone avant Noël ? »"
                if acc["cle"] == "fetes" else
                "« J'ai Facebook / Instagram »\n« Parfait, on met le lien. La page sert à prendre les commandes "
                "sans que vous ayez à décrocher. Vous en prenez combien par téléphone dans une semaine ? »")
    elif etat.startswith("Site cassé"):
        obj1 = ("« J'ai déjà un site »\n« Je l'ai ouvert depuis votre fiche Google : il ne s'affiche pas. "
                "Vous le saviez ? »")
    else:
        obj1 = ("« J'ai déjà un site »\n« Oui, je l'ai vu. Sur un téléphone, un client peut commander dessus ? »")
    obj2 = ("« C'est cher »\n« Une commande de fêtes, c'est combien en moyenne chez vous ? » Puis le calcul avec "
            "SON chiffre : 550 ÷ son chiffre = N. « Si le site vous amène N commandes, il est payé. » Toujours « si ».")
    if acc["cle"] != "fetes":
        obj2 = obj2.replace("Une commande de fêtes", "Une commande")
    obj3 = ("« Je n'ai pas 550 € maintenant »\n« Il y a aussi une formule sans rien à payer au départ : "
            "49 € par mois sur un an, ou 59 € par mois sans engagement. »")
    if avis >= 150:
        obj3 = ("« On a déjà assez de clients »\n« Tant mieux. La page ne sert pas à en avoir plus : elle prend les "
                f"commandes quand vous êtes au comptoir. Combien d'appels de commande un samedi ? »\n\n{obj3}")

    quand, _ = quand_appeler(_plages_texte(p), cat, jour)
    if rappel and p.get("Prochain appel"):
        quand = f"Rappel prévu. {quand}"
    return {
        "Appel": f"{i}. {p['Nom']}",
        "Numéro": f"{p.get('Téléphone', '')} ({adresse})" if p.get("Téléphone") else f"Pas de numéro : passer au {adresse}",
        "Quand appeler": quand,
        "Demande à parler à": "Le patron ou la patronne. Si un employé répond : son prénom et quand rappeler. Pas de pitch.",
        "Leur problème": probleme,
        "0. Tu te présentes": intro,
        "1. Compliment + problème": p.get("Observation", ""),
        "2. Ta question, puis tu te tais": question,
        "3. Tu proposes": propose,
        "Lien de la maquette": p.get("Lien maquette", ""),
        "Si on te demande le prix": prix,
        "Objection 1": obj1, "Objection 2": obj2, "Objection 3": obj3,
        "Résultat": "",
        "Réf. (ne pas modifier)": p.get("place_id", ""),
    }


def _plages_texte(p: dict) -> dict:
    """Reconstruit les plages depuis le texte « Horaires » (« Mar–Ven 8h–12h30, 14h30–19h · … »)."""
    import re
    from brunframe.horaires import JOURS_COURTS
    plages = {j: [] for j in range(7)}
    for morceau in str(p.get("Horaires", "")).split(" · "):
        m = re.match(r"(\w{3})(?:–(\w{3}))?\s+(.*)", morceau.strip())
        if not m:
            continue
        try:
            a = JOURS_COURTS.index(m.group(1).lower())
            b = JOURS_COURTS.index(m.group(2).lower()) if m.group(2) else a
        except ValueError:
            continue
        for h1, m1, h2, m2 in re.findall(r"(\d{1,2})h(\d{2})?–(\d{1,2})h(\d{2})?", m.group(3)):
            debut, fin = int(h1) * 60 + int(m1 or 0), int(h2) * 60 + int(m2 or 0)
            for j in range(a, b + 1):
                plages[j].append((debut, fin if fin > debut else 1440))
    return plages


# --- Écriture --------------------------------------------------------------------

def ecrire(c, colonnes: list[dict], jour: dt.date):
    if config.APPELS_DISPOSITION == "lignes":
        entetes = ["Date liste"] + CHAMPS
        lignes = [{"Date liste": str(jour), **col} for col in colonnes]
        c.remplacer(ONGLET, entetes, lignes)
        return
    grille = [[ch] + [col[ch] for col in colonnes] for ch in CHAMPS]
    grille.append(["Date liste"] + [str(jour)] * len(colonnes))
    c.vider(ONGLET)
    c.ecrire_valeurs(f"'{ONGLET}'!A1", grille)
    sid = c.onglets()[ONGLET]
    ligne_resultat = CHAMPS.index("Résultat")
    n = len(colonnes)
    c.batch([
        {"updateSheetProperties": {"properties": {"sheetId": sid, "gridProperties": {
            "frozenRowCount": 1, "frozenColumnCount": 1}}, "fields": "gridProperties(frozenRowCount,frozenColumnCount)"}},
        {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": len(grille),
                                  "startColumnIndex": 0, "endColumnIndex": n + 1},
                        "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"}},
                        "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)"}},
        {"repeatCell": {"range": {"sheetId": sid, "startColumnIndex": 0, "endColumnIndex": 1},
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                        "fields": "userEnteredFormat.textFormat.bold"}},
        {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                        "fields": "userEnteredFormat.textFormat.bold"}},
        {"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
                                       "properties": {"pixelSize": 170}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": 1, "endIndex": n + 1},
                                       "properties": {"pixelSize": 330}, "fields": "pixelSize"}},
        {"setDataValidation": {"range": {"sheetId": sid, "startRowIndex": ligne_resultat, "endRowIndex": ligne_resultat + 1,
                                         "startColumnIndex": 1, "endColumnIndex": n + 1},
                               "rule": {"condition": {"type": "ONE_OF_LIST", "values": [
                                   {"userEnteredValue": r} for r in config.RESULTATS]},
                                   "strict": False, "showCustomUi": True}}},
        {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": ligne_resultat, "endRowIndex": ligne_resultat + 1,
                                  "startColumnIndex": 0, "endColumnIndex": n + 1},
                        "cell": {"userEnteredFormat": {"backgroundColor": {"red": 1, "green": 0.95, "blue": 0.75}}},
                        "fields": "userEnteredFormat.backgroundColor"}},
    ])


def principal(args, log):
    jour = dt.date.today()
    if args.date:
        jour = dt.date.fromisoformat(args.date)
    c = None if args.hors_ligne else pl.classeur()
    prospects = pl.charger_prospects(args, c)
    if not args.test:
        c.assurer_onglet(ONGLET, [])
        archiver(c, prospects, log, jour)
        prospects = pl.charger_prospects(args, c)
    ln = ListeNoire(pl.liste_noire(args, c), jour)
    choisis = selectionner(prospects, ln, jour)
    if len(choisis) < config.APPELS_PAR_JOUR:
        log.warning("seulement %d commerces avec maquette à appeler (objectif %d) : lancer prospects.py / maquette.py",
                    len(choisis), config.APPELS_PAR_JOUR)
    colonnes = [colonne(i, p, jour) for i, p in enumerate(choisis, 1)]
    for col in colonnes:
        log.info("%s | %s", col["Appel"], col["Quand appeler"])
    if args.test:
        config.SORTIES_TEST.mkdir(parents=True, exist_ok=True)
        sortie = config.SORTIES_TEST / "appels_du_jour.csv"
        with sortie.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            for ch in CHAMPS:
                w.writerow([ch] + [col[ch] for col in colonnes])
        log.info("TEST : rien écrit dans le Sheet. Aperçu : %s", sortie)
        return
    ecrire(c, colonnes, jour)
    if len(choisis) < config.APPELS_PAR_JOUR:
        journal.noter_suivi(c, "alerte", "appels_du_jour.py",
                            f"{len(choisis)} appels seulement aujourd'hui", "Il manque des maquettes prêtes.")
    log.info("onglet « %s » : %d commerces", ONGLET, len(colonnes))


if __name__ == "__main__":
    p = journal.arguments(__doc__)
    p.add_argument("--date", default="", help="simule un autre jour (AAAA-MM-JJ), pour les tests")
    a = p.parse_args()
    sys.exit(journal.lancer("appels_du_jour", principal, a))
