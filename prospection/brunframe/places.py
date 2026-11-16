"""Client Google Places API (New), officiel. Aucun scraping.

Conditions Google Maps Platform : seul le place_id est gardé durablement ;
les avis ne sont lus qu'en mémoire. Un compteur mensuel par SKU empêche de
sortir de la gratuité (PLACES_PLAFOND_MENSUEL dans .env).
"""
from __future__ import annotations

import datetime as dt
import json
import time

import requests

from . import config

API = "https://places.googleapis.com/v1"

CHAMPS_FICHE = ["id", "displayName", "formattedAddress", "shortFormattedAddress", "location",
                "businessStatus", "primaryType", "types", "rating", "userRatingCount", "websiteUri",
                "nationalPhoneNumber", "regularOpeningHours", "googleMapsUri"]
CHAMPS_AVIS = ["id", "reviews", "editorialSummary"]

SKU_RECHERCHE = "text_search_enterprise"
SKU_AVIS = "place_details_enterprise_atmosphere"
SKU_FICHE = "place_details_enterprise"


class PlafondAtteint(RuntimeError):
    pass


class Places:
    def __init__(self, hors_ligne: bool = False, log=None):
        self.hors_ligne = hors_ligne
        self.log = log
        self.fichier_compteur = config.STATE / "compteur_places.json"
        self.mois = f"{dt.date.today():%Y-%m}"
        if hors_ligne:
            self.demo = json.loads((config.FIXTURES / "places_demo.json").read_text(encoding="utf-8"))
        elif not config.PLACES_KEY:
            raise RuntimeError("GOOGLE_PLACES_API_KEY manquante dans .env (voir README, « Accès Google »).")

    # -- compteur de gratuité --
    def _compter(self, sku: str):
        if self.hors_ligne:
            return
        donnees = {}
        if self.fichier_compteur.exists():
            donnees = json.loads(self.fichier_compteur.read_text(encoding="utf-8"))
        mois = donnees.setdefault(self.mois, {})
        if mois.get(sku, 0) >= config.PLACES_PLAFOND_MENSUEL:
            raise PlafondAtteint(
                f"Plafond mensuel atteint pour {sku} ({config.PLACES_PLAFOND_MENSUEL} appels). "
                "Arrêt pour rester dans la gratuité de Google Maps Platform.")
        mois[sku] = mois.get(sku, 0) + 1
        config.STATE.mkdir(parents=True, exist_ok=True)
        self.fichier_compteur.write_text(json.dumps(donnees, indent=1), encoding="utf-8")

    def compteur(self) -> dict:
        if self.fichier_compteur.exists():
            return json.loads(self.fichier_compteur.read_text(encoding="utf-8")).get(self.mois, {})
        return {}

    def _post(self, chemin: str, champs: str, corps: dict) -> dict:
        for essai in range(4):
            r = requests.post(f"{API}/{chemin}", json=corps, timeout=30, headers={
                "X-Goog-Api-Key": config.PLACES_KEY, "X-Goog-FieldMask": champs})
            if r.status_code in (429, 500, 503) and essai < 3:
                time.sleep(2 ** (essai + 1))
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"Places API {r.status_code} : {r.text[:300]}")
            return r.json()
        return {}

    def _get(self, place_id: str, champs: list[str]) -> dict:
        for essai in range(4):
            r = requests.get(f"{API}/places/{place_id}", timeout=30, params={"languageCode": "fr"},
                             headers={"X-Goog-Api-Key": config.PLACES_KEY,
                                      "X-Goog-FieldMask": ",".join(champs)})
            if r.status_code in (429, 500, 503) and essai < 3:
                time.sleep(2 ** (essai + 1))
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"Places API {r.status_code} : {r.text[:300]}")
            return r.json()
        return {}

    # -- recherche par catégorie et quartier --
    def rechercher(self, categorie: str, quartier: str, pages_max: int = 3) -> list[dict]:
        q = config.QUARTIERS[quartier]
        if self.hors_ligne:
            (la, lo), (ha, ho) = q["bas"], q["haut"]
            return [p for p in self.demo["recherche"].get(categorie, [])
                    if la <= p["location"]["latitude"] <= ha and lo <= p["location"]["longitude"] <= ho]
        corps = {
            "textQuery": f"{config.CATEGORIES[categorie]['requete']} Strasbourg",
            "languageCode": "fr", "regionCode": "FR", "pageSize": 20,
            "locationRestriction": {"rectangle": {
                "low": {"latitude": q["bas"][0], "longitude": q["bas"][1]},
                "high": {"latitude": q["haut"][0], "longitude": q["haut"][1]}}},
        }
        champs = ",".join("places." + c for c in CHAMPS_FICHE) + ",nextPageToken"
        resultats = []
        for _ in range(pages_max):
            self._compter(SKU_RECHERCHE)
            r = self._post("places:searchText", champs, corps)
            resultats.extend(r.get("places", []))
            if not r.get("nextPageToken"):
                break
            corps["pageToken"] = r["nextPageToken"]
            time.sleep(1)
        return resultats

    def avis(self, place_id: str) -> tuple[list[str], str]:
        """(textes des avis, résumé éditorial) — en mémoire seulement."""
        if self.hors_ligne:
            d = self.demo["details"].get(place_id, {})
        else:
            self._compter(SKU_AVIS)
            d = self._get(place_id, CHAMPS_AVIS)
        textes = []
        for a in d.get("reviews", []):
            t = (a.get("originalText") or a.get("text") or {}).get("text", "")
            if t:
                textes.append(t)
        resume = (d.get("editorialSummary") or {}).get("text", "")
        return textes, resume

    def fiche(self, place_id: str) -> dict:
        """Données fraîches pour la maquette ou le rafraîchissement à 30 jours."""
        if self.hors_ligne:
            for liste in self.demo["recherche"].values():
                for p in liste:
                    if p["id"] == place_id:
                        return p
            return {}
        self._compter(SKU_FICHE)
        return self._get(place_id, CHAMPS_FICHE)


def nom(place: dict) -> str:
    return (place.get("displayName") or {}).get("text", "")
