"""Accès Google : un seul OAuth (brunframe@gmail.com) pour Gmail et Sheets.

Le jeton est gardé dans state/token.json (ignoré par Git).
"""
from __future__ import annotations

import time

from . import config
from .textes import cellule

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/gmail.readonly",
    # Sprint 2 (mails J0 / J+5). Demandé dès maintenant pour éviter une 2e autorisation.
    "https://www.googleapis.com/auth/gmail.send",
]


def identifiants():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = None
    if config.OAUTH_TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(config.OAUTH_TOKEN), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not config.OAUTH_CLIENT.exists():
            raise RuntimeError(
                f"Fichier OAuth absent : {config.OAUTH_CLIENT}. Voir README, étape « Accès Google ».")
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(str(config.OAUTH_CLIENT), SCOPES)
        creds = flow.run_local_server(port=0, login_hint=config.GMAIL_COMPTE)
    config.STATE.mkdir(parents=True, exist_ok=True)
    config.OAUTH_TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


def service(nom: str, version: str):
    from googleapiclient.discovery import build
    return build(nom, version, credentials=identifiants(), cache_discovery=False)


def executer(requete, essais: int = 4):
    """execute() avec reprise sur erreurs passagères (429/5xx)."""
    from googleapiclient.errors import HttpError
    for i in range(essais):
        try:
            return requete.execute()
        except HttpError as e:
            if e.resp.status in (429, 500, 502, 503) and i < essais - 1:
                time.sleep(2 ** (i + 1))
                continue
            raise


def col(n: int) -> str:
    """1 -> A, 27 -> AA."""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


class Classeur:
    """Petit client Google Sheets : lecture/écriture par en-têtes."""

    def __init__(self, sheet_id: str, svc=None):
        self.id = sheet_id
        self.svc = svc or service("sheets", "v4")
        self._onglets: dict[str, int] | None = None

    # -- structure --
    def onglets(self) -> dict[str, int]:
        if self._onglets is None:
            meta = executer(self.svc.spreadsheets().get(
                spreadsheetId=self.id, fields="sheets.properties(sheetId,title)"))
            self._onglets = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}
        return self._onglets

    def batch(self, requetes: list[dict]):
        if requetes:
            executer(self.svc.spreadsheets().batchUpdate(spreadsheetId=self.id, body={"requests": requetes}))
            self._onglets = None

    def assurer_onglet(self, titre: str, entetes: list[str]) -> bool:
        """Crée l'onglet s'il manque, pose les en-têtes. True si créé."""
        cree = False
        if titre not in self.onglets():
            self.batch([{"addSheet": {"properties": {"title": titre, "gridProperties": {"frozenRowCount": 1 if entetes else 0}}}}])
            cree = True
        if entetes:
            actuels = self.valeurs(f"'{titre}'!1:1")
            actuels = actuels[0] if actuels else []
            manquants = [e for e in entetes if e not in actuels]
            if manquants:
                nouveaux = actuels + manquants
                self.ecrire_valeurs(f"'{titre}'!A1", [nouveaux])
                sid = self.onglets()[titre]
                self.batch([{"repeatCell": {
                    "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
                    "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                    "fields": "userEnteredFormat.textFormat.bold"}}])
        return cree

    # -- valeurs --
    def valeurs(self, plage: str) -> list[list]:
        r = executer(self.svc.spreadsheets().values().get(
            spreadsheetId=self.id, range=plage, valueRenderOption="FORMATTED_VALUE"))
        return r.get("values", [])

    def ecrire_valeurs(self, plage: str, lignes: list[list]):
        executer(self.svc.spreadsheets().values().update(
            spreadsheetId=self.id, range=plage, valueInputOption="RAW",
            body={"values": [[cellule(v) for v in l] for l in lignes]}))

    def vider(self, titre: str):
        executer(self.svc.spreadsheets().values().clear(spreadsheetId=self.id, range=f"'{titre}'"))

    def lire(self, titre: str) -> tuple[list[str], list[dict]]:
        """(en-têtes, lignes en dict). Chaque dict garde son n° de ligne dans '_ligne'."""
        v = self.valeurs(f"'{titre}'")
        if not v:
            return [], []
        entetes = v[0]
        lignes = []
        for i, l in enumerate(v[1:], start=2):
            if not any(str(x).strip() for x in l):
                continue
            d = {e: (l[j] if j < len(l) else "") for j, e in enumerate(entetes)}
            d["_ligne"] = i
            lignes.append(d)
        return entetes, lignes

    def ajouter(self, titre: str, entetes: list[str], lignes: list[dict]):
        if not lignes:
            return
        executer(self.svc.spreadsheets().values().append(
            spreadsheetId=self.id, range=f"'{titre}'!A1", valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [[cellule(d.get(e, "")) for e in entetes] for d in lignes]}))

    def mettre_a_jour(self, titre: str, entetes: list[str], lignes: list[dict]):
        """Réécrit les lignes existantes (clé '_ligne')."""
        donnees = []
        for d in lignes:
            n = d["_ligne"]
            donnees.append({"range": f"'{titre}'!A{n}:{col(len(entetes))}{n}",
                            "values": [[cellule(d.get(e, "")) for e in entetes]]})
        for i in range(0, len(donnees), 200):
            executer(self.svc.spreadsheets().values().batchUpdate(
                spreadsheetId=self.id,
                body={"valueInputOption": "RAW", "data": donnees[i:i + 200]}))

    def remplacer(self, titre: str, entetes: list[str], lignes: list[dict]):
        self.vider(titre)
        self.ecrire_valeurs(f"'{titre}'!A1", [entetes] + [[d.get(e, "") for e in entetes] for d in lignes])


def creer_classeur(titre: str) -> str:
    svc = service("sheets", "v4")
    r = executer(svc.spreadsheets().create(body={"properties": {"title": titre, "locale": "fr_FR",
                                                                "timeZone": "Europe/Paris"}},
                                           fields="spreadsheetId"))
    return r["spreadsheetId"]
