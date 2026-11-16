"""Faux Google Sheets en mémoire (sous-ensemble de l'API utilisé par Classeur)."""
from __future__ import annotations

import re


class _Req:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


def _col(lettres: str) -> int:
    n = 0
    for c in lettres:
        n = n * 26 + ord(c) - 64
    return n - 1


def _plage(plage: str):
    m = re.match(r"'(.+?)'(?:!(.*))?$", plage)
    onglet, reste = m.group(1), m.group(2) or ""
    cellule = re.match(r"([A-Z]*)(\d*)", reste.split(":")[0]) if reste else None
    ligne = int(cellule.group(2)) - 1 if cellule and cellule.group(2) else 0
    colonne = _col(cellule.group(1)) if cellule and cellule.group(1) else 0
    seule_ligne = bool(reste) and re.fullmatch(r"(\d+):(\d+)", reste) is not None
    return onglet, ligne, colonne, seule_ligne


class FauxSheets:
    def __init__(self):
        self.grilles: dict[str, list[list]] = {"Feuille 1": []}
        self.ids = {"Feuille 1": 0}
        self.requetes: list[dict] = []

    # spreadsheets()
    def spreadsheets(self):
        return self

    def values(self):
        return self

    def get(self, spreadsheetId=None, fields=None, range=None, valueRenderOption=None):
        if range is None:
            return _Req(lambda: {"sheets": [{"properties": {"title": t, "sheetId": i}} for t, i in self.ids.items()]})

        def lire():
            onglet, ligne, _, seule = _plage(range)
            g = self.grilles[onglet]
            v = g[ligne:ligne + 1] if seule else g
            v = [list(l) for l in v]
            while v and not any(str(x) for x in v[-1]):
                v.pop()
            return {"values": [[("" if x is None else x) for x in l] for l in v]} if v else {}
        return _Req(lire)

    def _ecrire(self, plage, valeurs):
        onglet, ligne, colonne, _ = _plage(plage)
        g = self.grilles[onglet]
        for i, l in enumerate(valeurs):
            while len(g) <= ligne + i:
                g.append([])
            r = g[ligne + i]
            while len(r) < colonne + len(l):
                r.append("")
            r[colonne:colonne + len(l)] = l

    def update(self, spreadsheetId, range, valueInputOption, body):
        return _Req(lambda: self._ecrire(range, body["values"]))

    def append(self, spreadsheetId, range, valueInputOption, insertDataOption, body):
        def faire():
            onglet = _plage(range)[0]
            g = self.grilles[onglet]
            while g and not any(str(x) for x in g[-1]):
                g.pop()
            g.extend([list(l) for l in body["values"]])
        return _Req(faire)

    def clear(self, spreadsheetId, range):
        return _Req(lambda: self.grilles.__setitem__(_plage(range)[0], []))

    def batchUpdate(self, spreadsheetId, body):
        def faire():
            if "data" in body:  # values().batchUpdate
                for d in body["data"]:
                    self._ecrire(d["range"], d["values"])
                return
            for r in body["requests"]:
                self.requetes.append(r)
                if "addSheet" in r:
                    t = r["addSheet"]["properties"]["title"]
                    self.grilles[t] = []
                    self.ids[t] = max(self.ids.values(), default=0) + 1
                if "deleteSheet" in r:
                    t = next(k for k, v in self.ids.items() if v == r["deleteSheet"]["sheetId"])
                    del self.grilles[t], self.ids[t]
        return _Req(faire)
