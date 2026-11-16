"""Filtres de la section 2 : site, chaînes, casher, score."""
from __future__ import annotations

import re
from urllib.parse import urlparse

import requests

from . import config
from .textes import normaliser

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

RESEAUX = ("facebook.com", "fb.com", "instagram.com", "linktr.ee", "tiktok.com", "linkedin.com")
PLATEFORMES_COMMANDE = ("ubereats.com", "deliveroo.fr", "just-eat.fr", "justeat", "zenchef",
                        "clickandcollect", "sumupstore", "sumup.store", "square.site", "ecwid",
                        "toogoodtogo")
GRATUITS = ("jimdofree.com", "jimdosite.com", "site123.me", "webnode.", "e-monsite.com",
            "wordpress.com", "business.site", "sites.google.com", "blogspot.", "over-blog",
            "wifeo.com", "pagesperso-orange.fr", "free.fr/", "monsite-orange.fr", "godaddysites.com",
            "mystrikingly.com", "weebly.com", "simplesite.com")
SIGNES_CASSE = ("domain is for sale", "ce domaine est a vendre", "domaine a vendre", "site en construction",
                "under construction", "coming soon", "bientot disponible", "page en construction",
                "this domain", "parked", "account suspended", "compte suspendu", "default web site page",
                "index of /")
SIGNES_COMMANDE = ("ajouter au panier", "add to cart", "mon panier", "votre panier", "/panier", "/cart",
                   "woocommerce", "cdn.shopify.com", "click and collect", "click & collect",
                   "click&collect", "commander en ligne", "commande en ligne", "commandez en ligne",
                   "prestashop", "wix-ecommerce", "wixstores", "ecwid", "zelty", "lightspeed",
                   "commerce.sumup", "sumup.store", "square.site", "ubereats.com", "deliveroo.fr",
                   "just-eat.fr", "zenchef", "/checkout", "passer commande")

ETATS_LIBELLES = {
    "aucun": "Aucun site",
    "reseau_social": "Seulement un réseau social",
    "casse": "Site cassé",
    "wix_gratuit": "Wix gratuit",
    "gratuit": "Site gratuit",
    "pas_mobile": "Illisible sur mobile",
    "sans_commande": "Sans moyen de commander",
    "commande_en_ligne": "Outil de commande en place",
}
FACTEUR_SITE = {"aucun": 1.0, "reseau_social": 1.0, "casse": 0.95, "wix_gratuit": 0.85,
                "gratuit": 0.85, "pas_mobile": 0.75, "sans_commande": 0.5}


def hote(url: str) -> str:
    try:
        h = urlparse(url if "://" in url else "http://" + url).hostname or ""
    except ValueError:
        return ""
    return h.lower().removeprefix("www.")


def site_normalise(url: str) -> str:
    """hôte + chemin, pour comparer deux adresses de site."""
    if not url:
        return ""
    p = urlparse(url if "://" in url else "http://" + url)
    return (hote(url) + (p.path or "").rstrip("/")).lower()


def classer_url(url: str) -> str | None:
    """Classement sans requête réseau (None = il faut visiter le site)."""
    if not url:
        return "aucun"
    h = hote(url)
    complet = url.lower()
    if any(h == r or h.endswith("." + r) for r in RESEAUX):
        return "reseau_social"
    if any(p in complet for p in PLATEFORMES_COMMANDE):
        return "commande_en_ligne"
    if h.endswith("wixsite.com"):
        return "wix_gratuit"
    if any(g in complet for g in GRATUITS):
        return "gratuit"
    return None


def analyser_html(html: str) -> str:
    bas = normaliser(html[:400000]) if html else ""
    brut = (html or "").lower()
    if len(bas) < 200 or any(s in bas for s in SIGNES_CASSE):
        return "casse"
    if any(s in brut for s in SIGNES_COMMANDE):
        return "commande_en_ligne"
    if not re.search(r"<meta[^>]+name=[\"']?viewport", brut):
        return "pas_mobile"
    return "sans_commande"


def verifier_site(url: str, timeout: int = 12) -> tuple[str, str]:
    """(état, détail) — voir ETATS_LIBELLES."""
    etat = classer_url(url)
    if etat in ("aucun", "reseau_social", "commande_en_ligne"):
        return etat, hote(url)
    gratuit = etat  # wix_gratuit / gratuit : on visite quand même (outil de commande ? cassé ?)
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "fr-FR,fr"},
                         timeout=timeout, allow_redirects=True)
    except requests.RequestException as e:
        return "casse", f"ne répond pas ({type(e).__name__})"
    final = classer_url(r.url)
    if final in ("reseau_social", "commande_en_ligne"):
        return final, hote(r.url)
    gratuit = gratuit or final
    if r.status_code >= 400:
        return "casse", f"erreur {r.status_code}"
    etat = analyser_html(r.text)
    if gratuit and etat in ("sans_commande", "pas_mobile"):
        etat = gratuit
    return etat, hote(r.url)


# --- Chaînes, casher, client ---------------------------------------------

def charger_chaines() -> list[str]:
    fichier = config.BASE / "config" / "chaines.txt"
    if not fichier.exists():
        return []
    return [normaliser(l) for l in fichier.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")]


def est_chaine(nom: str, chaines: list[str]) -> bool:
    n = normaliser(nom)
    return any(n == c or n.startswith(c + " ") or n.endswith(" " + c) for c in chaines if c)


RE_CASHER = re.compile(r"\b(casher|cacher|kasher|kosher|kascher|beth din|beit din|loubavitch|cachere|cachir)\b")


def est_casher(*textes: str) -> bool:
    return any(RE_CASHER.search(normaliser(t or "")) for t in textes)


def est_shemtov(nom: str) -> bool:
    return "shemtov" in normaliser(nom).replace(" ", "")


def score(nb_avis: int, note: float, etat_site: str) -> float:
    return round(nb_avis * note * FACTEUR_SITE.get(etat_site, 0), 1)
