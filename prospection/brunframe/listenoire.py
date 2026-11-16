"""Liste noire : construction (Gmail, feuilles d'appels) et vérification d'un prospect."""
from __future__ import annotations

import datetime as dt
import html
import re
from email.utils import getaddresses, parseaddr
from urllib.parse import parse_qs, urlparse

from . import config
from .filtres import hote, site_normalise
from .textes import chiffres_tel, coeur_nom, lire_date, normaliser, trouver_tels

DOMAINES_GENERIQUES = {
    "gmail.com", "googlemail.com", "hotmail.com", "hotmail.fr", "outlook.com", "outlook.fr", "live.com",
    "live.fr", "msn.com", "yahoo.com", "yahoo.fr", "orange.fr", "wanadoo.fr", "free.fr", "sfr.fr",
    "neuf.fr", "laposte.net", "icloud.com", "me.com", "aol.com", "gmx.fr", "gmx.com", "gmx.de",
    "numericable.fr", "bbox.fr", "protonmail.com", "proton.me", "web.de", "club-internet.fr",
}
RE_STOP = re.compile(r"\b(stop|non merci|pas interesse|pas interessee|ne m interesse pas|desinscri|"
                     r"unsubscribe|ne plus recevoir|retirez moi|arretez|ne pas me contacter)\b")
RE_AUTO = re.compile(r"^(reponse automatique|automatic reply|auto reply|absence|out of office|absent)")


def est_oui(v) -> bool:
    return str(v).strip().lower() in ("oui", "o", "true", "vrai", "1", "x")


# --- Gmail ----------------------------------------------------------------

def _url_reelle(url: str) -> str:
    url = html.unescape(url)
    p = urlparse(url)
    if p.hostname and p.hostname.endswith("google.com") and p.path == "/url":
        return parse_qs(p.query).get("q", [url])[0]
    return url


def sites_dans(texte: str) -> list[str]:
    urls = re.findall(r"https?://[^\s<>\"']+", html.unescape(texte or ""))
    res = []
    for u in urls:
        u = _url_reelle(u.rstrip(".,;)"))
        h = hote(u)
        if h and not h.endswith(("google.com", "brunframe.com", "netlify.app", "pages.dev")):
            res.append(u)
    return res


def nom_depuis_objet(objet: str) -> str:
    """« 2000 Aiguilles : votre site » -> « 2000 Aiguilles »."""
    objet = re.sub(r"^\s*(re|tr|fwd?)\s*:\s*", "", objet or "", flags=re.I)
    for sep in (" : ", " — ", " – ", " - "):
        if sep in objet:
            return objet.split(sep)[0].strip()
    return objet.strip()


def entrees_gmail(fils: list[dict], moi: str) -> dict[str, dict]:
    """fils = threads Gmail (format metadata). Retourne {email: entrée}."""
    entrees: dict[str, dict] = {}
    for fil in fils:
        messages = fil.get("messages", [])
        destinataires, repondu, stop = set(), False, False
        objet, sites, date_max = "", [], None
        for m in messages:
            h = {x["name"].lower(): x["value"] for x in m.get("payload", {}).get("headers", [])}
            expediteur = parseaddr(h.get("from", ""))[1].lower()
            date = dt.datetime.fromtimestamp(int(m.get("internalDate", 0)) / 1000).date()
            snippet = m.get("snippet", "")
            if expediteur == moi or "SENT" in m.get("labelIds", []):
                champs = [h[k] for k in ("to", "cc", "bcc") if h.get(k)]
                for _, adr in getaddresses(champs):
                    if adr and adr.lower() != moi:
                        destinataires.add(adr.lower())
                objet = objet or h.get("subject", "")
                sites += sites_dans(snippet)
                date_max = max(date_max or date, date)
            elif expediteur.startswith(("mailer-daemon", "postmaster")):
                continue
            elif not RE_AUTO.match(normaliser(h.get("subject", ""))):
                repondu = True
                if RE_STOP.search(normaliser(snippet)) or normaliser(snippet).startswith("non"):
                    stop = True
        for adr in destinataires:
            e = entrees.setdefault(adr, {
                "Clé": adr, "Type": "email", "Nom": nom_depuis_objet(objet), "Téléphone": "",
                "Site": sites[0] if sites else "", "Source": "Gmail (Envoyés)",
                "Motif": "Déjà contacté par mail", "Dernier contact": "", "A répondu": "non",
                "Définitif": "non"})
            if date_max and (not e["Dernier contact"] or str(date_max) > e["Dernier contact"]):
                e["Dernier contact"] = str(date_max)
            if repondu:
                e["A répondu"] = "oui"
                e["Motif"] = "A répondu au mail"
            if stop:
                e["Définitif"] = "oui"
                e["Motif"] = "A répondu non / stop"
    return entrees


# --- Feuilles d'appels (« Mes appels de 14h » ou format en lignes) -------

def entrees_feuille(valeurs: list[list], source: str) -> list[dict]:
    if not valeurs:
        return []
    etiquettes = [normaliser(l[0]) if l else "" for l in valeurs]
    noms, tels = [], []
    if "appel" in etiquettes and "numero" in etiquettes:  # un commerce par colonne
        lnom = valeurs[etiquettes.index("appel")]
        ltel = valeurs[etiquettes.index("numero")]
        for j in range(1, len(lnom)):
            noms.append(lnom[j])
            tels.append(ltel[j] if j < len(ltel) else "")
    else:  # un commerce par ligne
        entetes = [normaliser(x) for x in valeurs[0]]
        inom = next((i for i, e in enumerate(entetes) if e in ("entreprise", "nom", "commerce")), None)
        itel = next((i for i, e in enumerate(entetes) if e in ("telephone", "numero", "tel")), None)
        if inom is None:
            return []
        for l in valeurs[1:]:
            noms.append(l[inom] if inom < len(l) else "")
            tels.append(l[itel] if itel is not None and itel < len(l) else "")
    res = []
    for n, t in zip(noms, tels):
        nom = re.sub(r"^\s*\d+\.\s*", "", str(n))
        nom = re.sub(r"\s*\(.*?\)\s*", " ", nom).strip()
        if not nom:
            continue
        numeros = trouver_tels(str(t))
        res.append({"Clé": numeros[0] if numeros else nom, "Type": "appel", "Nom": nom,
                    "Téléphone": " / ".join(numeros), "Site": "", "Source": source,
                    "Motif": f"Dans « {source} » : Andy s'en occupe", "Dernier contact": "",
                    "A répondu": "", "Définitif": "oui"})
    return res


# --- Vérification ------------------------------------------------------------

class ListeNoire:
    def __init__(self, lignes: list[dict], aujourdhui: dt.date | None = None):
        self.jour = aujourdhui or dt.date.today()
        self.lignes = [l for l in lignes if self._bloquante(l)]
        self.tels, self.sites, self.domaines, self.noms, self.ids = {}, {}, {}, [], {}
        for l in self.lignes:
            motif = l.get("Motif") or l.get("Source") or "liste noire"
            for t in str(l.get("Téléphone", "")).split("/") + [l.get("Clé", "")]:
                if chiffres_tel(t):
                    self.tels[chiffres_tel(t)] = motif
            if l.get("Site"):
                self.sites[site_normalise(l["Site"])] = motif
            cle = str(l.get("Clé", ""))
            if l.get("Type") == "place_id":
                self.ids[cle] = motif
            if "@" in cle:
                local, dom = cle.lower().split("@", 1)
                if dom not in DOMAINES_GENERIQUES:
                    self.domaines[dom] = motif
                if len(local) >= 6:
                    self.noms.append((re.sub(r"\d+$", "", local), motif, True))
            c = coeur_nom(l.get("Nom", ""))
            if len(c) >= 3:
                self.noms.append((c, motif, False))

    def _bloquante(self, l: dict) -> bool:
        if est_oui(l.get("Définitif")) or est_oui(l.get("A répondu")):
            return True
        d = lire_date(l.get("Dernier contact"))
        if d is None:
            return True  # par prudence : contact sans date = bloqué
        return (self.jour - d).days < config.JOURS_AVANT_RECONTACT

    def motif(self, nom: str = "", telephone: str = "", site: str = "", place_id: str = "") -> str | None:
        if place_id and place_id in self.ids:
            return self.ids[place_id]
        if chiffres_tel(telephone) and chiffres_tel(telephone) in self.tels:
            return self.tels[chiffres_tel(telephone)]
        if site:
            if site_normalise(site) in self.sites:
                return self.sites[site_normalise(site)]
            if hote(site) in self.domaines:
                return self.domaines[hote(site)]
        coeur = coeur_nom(nom)
        compact = coeur.replace(" ", "")
        if len(coeur) < 3:
            return None
        for c, motif, est_local in self.noms:
            if est_local:
                if len(compact) >= 6 and (compact in c or c == compact):
                    return motif
                continue
            if c == coeur:
                return motif
            court, long_ = sorted((c, coeur), key=len)
            if len(court) >= 5 and re.search(r"(^| )" + re.escape(court) + r"( |$)", long_):
                return motif
        return None
