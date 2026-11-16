"""Horaires d'ouverture (format Places API) et meilleur créneau d'appel.

Représentation interne : {jour: [(début, fin), ...]} avec jour 0 = lundi
et des minutes depuis minuit.
"""
from __future__ import annotations

import datetime as dt

from . import config
from .textes import heure_fr

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
JOURS_COURTS = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]
DUREE_MIN = 15


def plages_depuis_places(opening_hours: dict | None) -> dict[int, list[tuple[int, int]]]:
    plages: dict[int, list[tuple[int, int]]] = {j: [] for j in range(7)}
    if not opening_hours:
        return plages
    for p in opening_hours.get("periods", []):
        o = p.get("open") or {}
        c = p.get("close")
        jo = (int(o.get("day", 0)) - 1) % 7
        debut = int(o.get("hour", 0)) * 60 + int(o.get("minute", 0))
        if c is None:  # ouvert 24h/24
            return {j: [(0, 1440)] for j in range(7)}
        jc = (int(c.get("day", 0)) - 1) % 7
        fin = int(c.get("hour", 0)) * 60 + int(c.get("minute", 0))
        if jc == jo and fin > debut:
            plages[jo].append((debut, fin))
        else:  # passe minuit
            plages[jo].append((debut, 1440))
            if fin > 0:
                plages[jc].append((0, fin))
    for j in plages:
        plages[j].sort()
    return plages


def horaires_connus(plages) -> bool:
    return any(plages.get(j) for j in range(7))


def _texte_jour(intervalles) -> str:
    if not intervalles:
        return "fermé"
    return ", ".join(f"{heure_fr(a)}–{heure_fr(b)}" for a, b in intervalles)


def _jours_groupes(jours: list[int]) -> str:
    """[0,1,2,4] -> « lun–mer, ven »."""
    if not jours:
        return ""
    groupes, debut, prec = [], jours[0], jours[0]
    for j in jours[1:] + [None]:
        if j is not None and j == prec + 1:
            prec = j
            continue
        if prec - debut >= 2:
            groupes.append(f"{JOURS_COURTS[debut]}–{JOURS_COURTS[prec]}")
        elif prec != debut:
            groupes.append(f"{JOURS_COURTS[debut]}, {JOURS_COURTS[prec]}")
        else:
            groupes.append(JOURS_COURTS[debut])
        if j is not None:
            debut = prec = j
    return ", ".join(groupes)


def format_horaires(plages) -> str:
    """« Lun fermé · Mar–Ven 8h–12h30, 14h30–19h · Sam 7h30–13h »."""
    if not horaires_connus(plages):
        return "Horaires non publiés"
    morceaux, j = [], 0
    while j < 7:
        texte = _texte_jour(plages[j])
        k = j
        while k + 1 < 7 and _texte_jour(plages[k + 1]) == texte:
            k += 1
        jours = JOURS_COURTS[j].capitalize() + (f"–{JOURS_COURTS[k].capitalize()}" if k > j else "")
        morceaux.append(f"{jours} {texte}")
        j = k + 1
    return " · ".join(morceaux)


def _soustraire(segment, retraits):
    morceaux = [segment]
    for ra, rb in retraits:
        suite = []
        for a, b in morceaux:
            if rb <= a or ra >= b:
                suite.append((a, b))
                continue
            if a < ra:
                suite.append((a, ra))
            if rb < b:
                suite.append((rb, b))
        morceaux = suite
    return [(a, b) for a, b in morceaux if b - a >= DUREE_MIN]


def segments_jour(plages, categorie: str, jour: int, avec_rush: bool = False):
    """Segments appelables ce jour-là : créneau d'Andy ∩ ouvert − rush."""
    if jour > 4:
        return []
    rush = [] if avec_rush else config.CATEGORIES.get(categorie, {}).get("rush", [])
    ouverts = plages.get(jour, []) if horaires_connus(plages) else [(0, 1440)]
    res = []
    for sa, sb in config.CRENEAUX_ANDY:
        for oa, ob in ouverts:
            a, b = max(sa, oa), min(sb, ob)
            if b - a >= DUREE_MIN:
                res.extend(_soustraire((a, b), rush))
    return sorted(res)


def meilleur_creneau(plages, categorie: str) -> str:
    """Résumé pour l'onglet Prospects, ex. « 14h–14h30 (mar–ven) ; sinon 16h15–17h (lun–ven) »."""
    if not horaires_connus(plages):
        return "Horaires inconnus : essayer 14h, sinon 16h15"
    for avec_rush, suffixe in ((False, ""), (True, " (heure de pointe)")):
        options = []
        for sa, sb in config.CRENEAUX_ANDY:
            par_segment: dict[tuple[int, int], list[int]] = {}
            for jour in range(5):
                for seg in segments_jour(plages, categorie, jour, avec_rush):
                    if seg[0] >= sa and seg[1] <= sb:
                        par_segment.setdefault(seg, []).append(jour)
                        break
            if par_segment:
                seg, jours = max(par_segment.items(), key=lambda kv: (len(kv[1]), -kv[0][0]))
                options.append(f"{heure_fr(seg[0])}–{heure_fr(min(seg[1], seg[0] + 60))} ({_jours_groupes(jours)})")
        if options:
            return " ; sinon ".join(options[:2]) + suffixe
    return "Fermé sur les créneaux d'Andy : passer en boutique (samedi)"


def quand_appeler(plages, categorie: str, jour_liste: dt.date) -> tuple[str, dt.date]:
    """Texte « Quand appeler » pour la liste du jour, et la date visée."""
    for decalage in range(0, 8):
        d = jour_liste + dt.timedelta(days=decalage)
        segs = segments_jour(plages, categorie, d.weekday()) or segments_jour(
            plages, categorie, d.weekday(), avec_rush=True)
        if not segs:
            continue
        a, b = segs[0]
        texte = f"{heure_fr(a)}–{heure_fr(min(b, a + 60))}"
        if len(segs) > 1:
            texte += f", sinon {heure_fr(segs[1][0])}–{heure_fr(min(segs[1][1], segs[1][0] + 60))}"
        if decalage == 0:
            prefixe = "Aujourd'hui"
            if a >= config.CRENEAUX_ANDY[1][0] and horaires_connus(plages):
                texte += " (fermé ou en rush à 14h)"
        elif decalage == 1:
            prefixe = f"Demain ({JOURS[d.weekday()]})"
        else:
            prefixe = JOURS[d.weekday()].capitalize()
        if decalage and jour_liste.weekday() < 5 and horaires_connus(plages):
            texte += " : fermé aujourd'hui sur tes créneaux"
        return f"{prefixe} {texte}", d
    return "Fermé sur tes créneaux : passer en boutique (samedi)", jour_liste


def ouvert_json(plages) -> dict[str, list[list[int]]]:
    return {str(j): [[a, b] for a, b in plages.get(j, [])] for j in range(7)}


def lignes_horaires(plages) -> list[tuple[str, str]]:
    return [(JOURS[j].capitalize(), _texte_jour(plages.get(j, []))) for j in range(7)]
