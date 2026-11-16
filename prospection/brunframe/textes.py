"""Outils de texte : normalisation, slugs, téléphones, mots interdits."""
from __future__ import annotations

import re
import unicodedata

MOTS_INTERDITS = [
    "je me permets", "n'hésitez pas", "n’hésitez pas", "solution digitale", "booster",
    "optimiser votre présence", "présence en ligne", "sans promesse de", "boostez",
    "révolutionn", "incroyable", "exceptionnel", "garanti", "plus de clients",
    "augmenter vos ventes", "chiffre d'affaires", "dernière chance", "offre limitée",
]

# Mots trop génériques pour identifier un commerce par son nom.
MOTS_GENERIQUES = {
    "boulangerie", "patisserie", "boucherie", "charcuterie", "traiteur", "fromagerie",
    "fromager", "cave", "caviste", "vins", "vin", "epicerie", "fine", "chocolaterie",
    "chocolatier", "chocolat", "maison", "chez", "le", "la", "les", "l", "de", "du", "des",
    "d", "et", "au", "aux", "a", "en", "strasbourg", "sarl", "sas", "eurl", "sa", "the",
    "salon", "the", "boutique", "artisan", "artisanale", "votre", "site", "bonjour",
}


def sans_accents(texte: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texte or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normaliser(texte: str) -> str:
    """minuscules, sans accents, ponctuation -> espaces."""
    t = sans_accents(texte).lower().replace("œ", "oe").replace("æ", "ae")
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def coeur_nom(nom: str) -> str:
    """Nom sans les mots génériques : « Boucherie Muller » -> « muller »."""
    mots = [m for m in normaliser(nom).split() if m not in MOTS_GENERIQUES]
    return " ".join(mots)


def slugifier(texte: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", sans_accents(texte).lower()).strip("-")
    return s[:60].strip("-") or "commerce"


def chiffres_tel(tel: str) -> str:
    """9 derniers chiffres (indépendant de +33 / 0)."""
    d = re.sub(r"\D", "", tel or "")
    return d[-9:] if len(d) >= 9 else ""


def tel_national(tel: str) -> str:
    d = chiffres_tel(tel)
    if not d:
        return (tel or "").strip()
    d = "0" + d
    return " ".join(d[i:i + 2] for i in range(0, 10, 2))


def tel_international(tel: str) -> str:
    d = chiffres_tel(tel)
    return "+33" + d if d else ""


def est_mobile(tel: str) -> bool:
    d = chiffres_tel(tel)
    return bool(d) and d[0] in "67"


RE_TEL = re.compile(r"(?:\+33\s?|0)[1-9](?:[\s.\-]?\d{2}){4}")


def trouver_tels(texte: str) -> list[str]:
    return [tel_national(t) for t in RE_TEL.findall(texte or "")]


def note_fr(note) -> str:
    try:
        return f"{float(note):.1f}".replace(".", ",")
    except (TypeError, ValueError):
        return ""


def heure_fr(minutes: int) -> str:
    h, m = divmod(int(minutes) % (24 * 60), 60)
    return f"{h}h{m:02d}" if m else f"{h}h"


def possessif(nom: str) -> str:
    """« votre forêt-noire », « vos macarons »."""
    return ("vos " if nom.rstrip().endswith(("s", "x")) else "votre ") + nom


def mots_interdits(texte: str) -> list[str]:
    t = (texte or "").lower().replace("’", "'")
    return [m for m in MOTS_INTERDITS if m.replace("’", "'") in t]


def cellule(valeur):
    """Valeur écrite telle quelle (mode RAW : jamais interprétée comme formule)."""
    return "" if valeur is None else valeur


def lire_date(texte):
    """« 2026-11-16 » ou « 16/11/2026 » -> date (None si vide ou illisible)."""
    import datetime as dt
    t = str(texte or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(t[:10], fmt).date()
        except ValueError:
            continue
    return None
