"""Recherche Google Places par catégorie et par quartier, filtres de la section 2,
score (avis × note × absence de site) → fiches qualifiées dans l'onglet Prospects.

    python prospects.py --test               # vraie recherche, rien écrit : sorties/test/prospects.csv
    python prospects.py                      # ajoute jusqu'à 50 fiches dans Prospects
    python prospects.py --nombre 20 --categories boucherie,traiteur
    python prospects.py --rafraichir         # remet à jour les fiches vérifiées il y a plus de 30 jours
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from collections import Counter

from brunframe import accroches, claude_cli, config, journal
from brunframe import pipeline as pl
from brunframe.filtres import (ETATS_LIBELLES, charger_chaines, est_casher, est_chaine, est_shemtov,
                               score, verifier_site)
from brunframe.horaires import format_horaires, meilleur_creneau, plages_depuis_places
from brunframe.listenoire import ListeNoire
from brunframe.places import PlafondAtteint, Places, nom
from brunframe.specialites import citee_dans, extraire
from brunframe.textes import mots_interdits, note_fr, tel_national

FICHIER_VUS = config.STATE / "places_vus.json"
TYPES_HORS_CIBLE = {"bar", "night_club", "hotel", "lodging", "supermarket", "gas_station",
                    "cafe", "coffee_shop", "meal_delivery"}
MOTS_CIBLE = ("traiteur", "boucher", "charcut", "patiss", "boulang", "fromag", "cave", "vin",
              "chocolat", "epicerie")


def hors_cible(place: dict) -> bool:
    t = place.get("primaryType", "")
    if t in TYPES_HORS_CIBLE or t.endswith("restaurant"):
        from brunframe.textes import normaliser
        return not any(m in normaliser(nom(place)) for m in MOTS_CIBLE)
    return False


def phrase_probleme(etat: str, pour: str) -> str:
    return {
        "aucun": f"Mais pour commander {pour}, il faut vous appeler.",
        "reseau_social": f"Mais pour commander {pour}, il faut vous appeler.",
        "casse": "Mais le lien « Site web » de votre fiche Google ne mène nulle part.",
        "wix_gratuit": f"Mais sur votre site actuel, on ne peut pas commander {pour}.",
        "gratuit": f"Mais sur votre site actuel, on ne peut pas commander {pour}.",
        "pas_mobile": "Mais sur un téléphone, votre site est difficile à lire, et on ne peut pas y commander.",
        "sans_commande": f"Mais sur votre site, on ne peut pas commander {pour}.",
    }.get(etat, f"Mais pour commander {pour}, il faut vous appeler.")


def observation_simple(f: dict, pour: str) -> str:
    debut = f"{f['avis']} avis à {f['note']}"
    specs = [s for s in f["specialites"] if s]
    if len(specs) == 2:
        debut += f", et vos clients y parlent de {specs[0]} et de {specs[1]}."
    elif specs:
        debut += f", et vos clients y parlent de {specs[0]}."
    else:
        debut += " sur Google."
    return f"« {debut} {phrase_probleme(f['etat'], pour)} »"


def valider(phrase, faits: dict) -> bool:
    if not isinstance(phrase, str) or not 30 <= len(phrase) <= 260 or mots_interdits(phrase):
        return False
    autorises = json.dumps(faits, ensure_ascii=False)
    return all(n in autorises or n.replace(",", ".") in autorises for n in re.findall(r"\d+(?:,\d+)?", phrase))


def observations_claude(fiches: list[dict], log) -> dict[str, str]:
    """Une phrase personnalisée par commerce, par lots de 10. {} si indisponible."""
    if not claude_cli.disponible():
        log.info("claude introuvable : observations déterministes")
        return {}
    res = {}
    for i in range(0, len(fiches), 10):
        lot = [{"id": f["id"], "nom": f["nom"], "categorie": f["categorie"], "note": f["note"],
                "avis": f["avis"], "site": f["etat_texte"], "specialites": f["specialites"],
                "accroche": f["pour"], "extraits": f["extraits"]} for f in fiches[i:i + 10]]
        prompt = (
            "Pour chaque commerce de bouche ci-dessous, écris UNE phrase qu'Andy dira au téléphone, "
            "au vouvoiement, 30 mots maximum, entre guillemets français, sur ce modèle : "
            "« 67 avis à 4,9 : vos clients parlent de votre forêt-noire. Mais pour commander "
            "pour les fêtes, il faut vous appeler. » (remplacer « pour les fêtes » par le champ accroche)\n"
            "Règles : uniquement les faits donnés (note, avis, extraits, état du site). Aucun chiffre "
            "absent des faits. Rien d'inventé, pas de superlatif, pas de promesse. Mots interdits : "
            "« je me permets », « n'hésitez pas », « booster », « optimiser », « solution digitale ». "
            "La 2e moitié dit le problème concret lié à l'état du site, sur un ton neutre, sans dénigrer leur site.\n"
            'Réponds uniquement en JSON : {"<id>": "<phrase>"}\n'
            + json.dumps(lot, ensure_ascii=False))
        r = claude_cli.demander_json(prompt)
        if not isinstance(r, dict):
            log.warning("claude : réponse inutilisable pour le lot %d", i // 10 + 1)
            continue
        for faits in lot:
            phrase = r.get(faits["id"])
            if valider(phrase, faits):
                res[faits["id"]] = phrase.strip()
            else:
                log.info("observation rejetée (%s) : %s", faits["nom"], str(phrase)[:120])
    return res


def charger_vus(args) -> dict:
    if args.test or not FICHIER_VUS.exists():
        return {}
    return json.loads(FICHIER_VUS.read_text(encoding="utf-8"))


def rafraichir(args, log, places: Places):
    c = pl.classeur() if not args.hors_ligne else None
    lignes = pl.charger_prospects(args, c)
    jour = dt.date.today()
    a_jour = []
    from brunframe.textes import lire_date
    for l in lignes:
        v = lire_date(l.get("Vérifié le"))
        if v and (jour - v).days < config.JOURS_FRAICHEUR_PLACES:
            continue
        p = places.fiche(l["place_id"])
        if not p:
            continue
        plages = plages_depuis_places(p.get("regularOpeningHours"))
        l.update({"Nom": nom(p) or l["Nom"], "Adresse": p.get("shortFormattedAddress") or p.get("formattedAddress", ""),
                  "Téléphone": tel_national(p.get("nationalPhoneNumber", "")), "Horaires": format_horaires(plages),
                  "Site": p.get("websiteUri", ""), "Note": p.get("rating", ""), "Nb avis": p.get("userRatingCount", ""),
                  "Lien Google Maps": p.get("googleMapsUri", ""), "Vérifié le": str(jour)})
        if p.get("businessStatus") not in (None, "OPERATIONAL"):
            l["Statut"] = "Fermé"
        a_jour.append(l)
    log.info("%d fiches rafraîchies (plus de %d jours)", len(a_jour), config.JOURS_FRAICHEUR_PLACES)
    if args.test:
        pl.enregistrer_test(a_jour, "prospects_rafraichis")
    elif a_jour:
        c.mettre_a_jour("Prospects", config.ONGLETS["Prospects"], a_jour)


def principal(args, log):
    jour = dt.date.today()
    places = Places(hors_ligne=args.hors_ligne, log=log)
    if args.rafraichir:
        return rafraichir(args, log, places)
    c = None if args.hors_ligne else pl.classeur()
    ln = ListeNoire(pl.liste_noire(args, c), jour)
    deja = set() if args.hors_ligne else {l["place_id"] for l in c.lire("Prospects")[1]}  # le vrai Sheet
    vus = charger_vus(args)
    chaines = charger_chaines()
    categories = args.categories.split(",") if args.categories else list(config.CATEGORIES)
    if args.quartiers:
        niveaux = [[q.strip() for q in args.quartiers.split(",")]]
    else:
        niveaux = [[q for q, d in config.QUARTIERS.items() if d["niveau"] == n] for n in (1, 2)]

    exclus, traites, candidats = Counter(), set(), []
    try:
        for i, quartiers in enumerate(niveaux):
            if i and len(candidats) >= args.nombre * 1.3:
                break
            if i:
                log.info("Centre épuisé (%d candidats) : quartiers voisins %s", len(candidats), ", ".join(quartiers))
            for quartier in quartiers:
                for cat in categories:
                    for p in places.rechercher(cat, quartier):
                        pid = p["id"]
                        if pid in traites:
                            continue
                        traites.add(pid)
                        motif = None
                        ancien = vus.get(pid)
                        if pid in deja:
                            motif = "déjà dans Prospects"
                        elif ancien and (jour - dt.date.fromisoformat(ancien["le"])).days < config.JOURS_AVANT_RECONTACT:
                            motif = "déjà évalué (< 60 jours)"
                        elif p.get("businessStatus", "OPERATIONAL") != "OPERATIONAL":
                            motif = "fermé"
                        elif (p.get("userRatingCount") or 0) < config.MIN_AVIS or (p.get("rating") or 0) < config.MIN_NOTE:
                            motif = "moins de 30 avis ou note < 4,3"
                        elif hors_cible(p):
                            motif = "hors cible (restaurant, bar…)"
                        elif est_shemtov(nom(p)):
                            motif = "client (Shemtov)"
                        elif est_chaine(nom(p), chaines):
                            motif = "chaîne ou franchise"
                        elif est_casher(nom(p)) and pid not in config.ACCORD_CASHER:
                            motif = "casher : concurrent de Shemtov"
                        else:
                            m = ln.motif(nom(p), p.get("nationalPhoneNumber", ""), p.get("websiteUri", ""), pid)
                            if m:
                                motif = f"liste noire ({m})"
                        if motif:
                            exclus[motif] += 1
                            continue
                        etat, detail = verifier_site(p.get("websiteUri", "")) if not args.hors_ligne else (
                            p.get("_etat_demo", "aucun"), "")
                        if etat == "commande_en_ligne":
                            exclus["outil de commande en place"] += 1
                            vus[pid] = {"le": str(jour), "motif": "commande en ligne"}
                            continue
                        candidats.append({"place": p, "categorie": cat, "quartier": quartier, "etat": etat,
                                          "detail": detail,
                                          "score": score(p["userRatingCount"], p["rating"], etat)})
                log.info("%s : %d candidats cumulés", quartier, len(candidats))
    except PlafondAtteint as e:
        log.warning("%s — on continue avec les %d candidats déjà trouvés", e, len(candidats))

    candidats.sort(key=lambda x: -x["score"])
    fiches = []
    for cand in candidats:
        if len(fiches) >= args.nombre:
            break
        p, cat = cand["place"], cand["categorie"]
        try:
            avis, resume = places.avis(p["id"])
        except PlafondAtteint as e:
            log.warning("%s", e)
            break
        if est_casher(resume, *avis) and p["id"] not in config.ACCORD_CASHER:
            exclus["casher : concurrent de Shemtov"] += 1
            vus[p["id"]] = {"le": str(jour), "motif": "casher"}
            continue
        specs = [s for s in extraire(avis, cat) if citee_dans(s, avis)]
        extraits = [a[:220] for a in avis[:2]]
        plages = plages_depuis_places(p.get("regularOpeningHours"))
        etat_texte = ETATS_LIBELLES[cand["etat"]] + (f" ({cand['detail']})" if cand["detail"] else "")
        fiches.append({"id": p["id"], "nom": nom(p), "categorie": config.CATEGORIES[cat]["label"],
                       "cat": cat, "note": note_fr(p["rating"]), "avis": p["userRatingCount"],
                       "etat": cand["etat"], "etat_texte": etat_texte, "specialites": specs,
                       "extraits": extraits, "place": p, "plages": plages, "quartier": cand["quartier"],
                       "score": cand["score"], "pour": accroches.accroche(jour, cat)["pour"]})
        vus[p["id"]] = {"le": str(jour), "motif": "qualifié"}

    perso = {} if args.sans_claude else observations_claude(fiches, log)
    lignes = []
    for f in fiches:
        p = f["place"]
        specs = f["specialites"] + ["", ""]
        lignes.append({
            "place_id": f["id"], "Nom": f["nom"], "Catégorie": f["categorie"], "Quartier": f["quartier"],
            "Adresse": p.get("shortFormattedAddress") or p.get("formattedAddress", ""),
            "Téléphone": tel_national(p.get("nationalPhoneNumber", "")),
            "Horaires": format_horaires(f["plages"]), "Site": p.get("websiteUri", ""),
            "État du site": f["etat_texte"], "Note": p["rating"], "Nb avis": p["userRatingCount"],
            "Spécialité 1": specs[0], "Spécialité 2": specs[1],
            "Observation": perso.get(f["id"]) or observation_simple(f, f["pour"]),
            "Meilleur créneau": meilleur_creneau(f["plages"], f["cat"]),
            "Lien Google Maps": p.get("googleMapsUri", ""), "Score": f["score"],
            "Statut": "Qualifié", "Ajouté le": str(jour), "Vérifié le": str(jour), "Nb appels": 0,
        })

    log.info("%d fiches qualifiées (%d personnalisées par claude). Exclusions : %s", len(lignes),
             len(perso), ", ".join(f"{k} {v}" for k, v in exclus.most_common()) or "aucune")
    log.info("Appels Places ce mois : %s", places.compteur() or "hors ligne")
    if len(lignes) < args.nombre:
        log.warning("Seulement %d fiches sur %d : élargir (--quartiers) ou passer à la niche suivante.",
                    len(lignes), args.nombre)
    if args.test:
        pl.enregistrer_test(lignes)
        log.info("TEST : rien écrit dans le Sheet. Aperçu : %s", config.SORTIES_TEST / "prospects.csv")
        return
    c.assurer_onglet("Prospects", config.ONGLETS["Prospects"])
    c.ajouter("Prospects", config.ONGLETS["Prospects"], lignes)
    config.STATE.mkdir(parents=True, exist_ok=True)
    FICHIER_VUS.write_text(json.dumps(vus, indent=0), encoding="utf-8")
    journal.noter_suivi(c, "info", "prospects.py", f"{len(lignes)} fiches ajoutées",
                        ", ".join(f"{k} {v}" for k, v in exclus.most_common(6)))


if __name__ == "__main__":
    p = journal.arguments(__doc__)
    p.add_argument("--nombre", type=int, default=50, help="fiches qualifiées à ajouter (défaut 50)")
    p.add_argument("--categories", default="", help="ex. boucherie,traiteur (défaut : toutes)")
    p.add_argument("--quartiers", default="", help="ex. « Krutenau,Gare » (défaut : centre puis voisins)")
    p.add_argument("--sans-claude", action="store_true", help="observations sans claude -p")
    p.add_argument("--rafraichir", action="store_true", help="met à jour les fiches de plus de 30 jours")
    a = p.parse_args()
    sys.exit(journal.lancer("prospects", principal, a))
