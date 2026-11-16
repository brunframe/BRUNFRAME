"""Rendu des maquettes : une page statique par commerce dans site/demo/<slug>/."""
from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path

from . import config
from .horaires import lignes_horaires, ouvert_json
from .textes import est_mobile, note_fr, tel_international

EXEMPLES = {
    "boucherie": "Ex. : 1 rôti de 1,2 kg et 6 saucisses",
    "traiteur": "Ex. : un plat pour 6 personnes",
    "patisserie": "Ex. : 1 entremets pour 8 personnes",
    "chocolatier": "Ex. : 1 ballotin de 500 g",
    "fromagerie": "Ex. : 1 plateau pour 6 personnes",
    "caviste": "Ex. : 3 bouteilles de crémant",
    "epicerie": "Ex. : 1 coffret cadeau",
    "boulangerie": "Ex. : 2 baguettes et 1 kougelhopf",
}


def _lum(hexa: str) -> float:
    h = hexa.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contraste(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def texte_sur(fond: str) -> str:
    return "#ffffff" if contraste(fond, "#ffffff") >= 4.5 else "#1c1918"


def personnalisation(slug: str) -> tuple[dict, Path | None]:
    """personnalisation/<slug>.json + dossier personnalisation/<slug>/ (logo, photo)."""
    fichier = config.PERSONNALISATION / f"{slug}.json"
    dossier = config.PERSONNALISATION / slug
    perso = json.loads(fichier.read_text(encoding="utf-8")) if fichier.exists() else {}
    return perso, dossier if dossier.is_dir() else None


def _json_script(v) -> str:
    return json.dumps(v, ensure_ascii=False).replace("</", "<\\/")


def rendre(fiche: dict, cat: str, accroche: dict, plages: dict, slug: str) -> tuple[str, list[Path]]:
    """fiche : nom, quartier, adresse, telephone, note, nb_avis, lien_maps, specialites.
    Retourne (html, fichiers à copier à côté de la page)."""
    perso, dossier = personnalisation(slug)
    couleurs = dict(config.CATEGORIES[cat]["couleurs"])
    couleurs.update({k: perso[k] for k in ("fond", "accent", "clair") if perso.get(k)})
    e = lambda v: html.escape(str(v or ""), quote=True)
    copies, classe_photo, style_photo, credit = [], "", "", ""

    if perso.get("logo") and dossier and (dossier / perso["logo"]).exists():
        logo = f'<img class="logo" src="{e(perso["logo"])}" alt="{e(fiche["nom"])}">'
        copies.append(dossier / perso["logo"])
    else:
        initiales = "".join(m[0] for m in re.findall(r"[A-Za-zÀ-ÿ]+", fiche["nom"])[:2]).upper() or "•"
        logo = f'<span class="mono" aria-hidden="true">{e(initiales)}</span>'
    if perso.get("photo") and dossier and (dossier / perso["photo"]).exists():
        if not perso.get("credit_photo"):
            raise ValueError(f"{slug} : photo sans « credit_photo » (attribution obligatoire)")
        classe_photo = " photo"
        style_photo = f'style="--photo:url(\'{e(perso["photo"])}\')"'
        credit = f" Photo : {e(perso['credit_photo'])}."
        copies.append(dossier / perso["photo"])

    specs = [s for s in (perso.get("specialites") or fiche.get("specialites") or []) if s][:2]
    if specs:
        cartes = "".join(f'<div class="spec"><strong>{e(s[:1].upper() + s[1:])}</strong><span>Prix en boutique</span></div>'
                         for s in specs)
        source = "Mise en avant choisie par la boutique." if perso.get("specialites") else \
            "Citées par nos clients dans les avis Google."
        bloc_specs = (f'<section class="bloc" aria-labelledby="t-specs"><h2 id="t-specs">Nos incontournables</h2>'
                      f'<div class="specs">{cartes}</div><p class="mention">{source}</p></section>')
    else:
        bloc_specs = ""

    tel = fiche.get("telephone", "")
    whatsapp = tel_international(perso.get("whatsapp") or (tel if est_mobile(tel) else "")).lstrip("+")
    bouton_tel = (f'<a class="bouton2" href="tel:{e(tel_international(tel))}">Appeler</a>' if tel else "")
    lignes = "".join(f'<tr data-jour="{j}"><td>{e(n)}</td><td>{e(h)}</td></tr>'
                     for j, (n, h) in enumerate(lignes_horaires(plages)))
    valeurs = {
        "nom": e(fiche["nom"]), "categorie": e(config.CATEGORIES[cat]["label"]),
        "quartier": e(fiche.get("quartier", "Strasbourg")), "fond": couleurs["fond"],
        "accent": couleurs["accent"], "sur_accent": texte_sur(couleurs["accent"]), "clair": couleurs["clair"],
        "classe_photo": classe_photo, "style_photo": style_photo, "logo": logo,
        "note": e(note_fr(fiche.get("note"))), "nb_avis": e(fiche.get("nb_avis")),
        "accroche_bouton": e(accroche["bouton"]), "accroche_titre": e(accroche["titre"]),
        "accroche_pour": e(accroche["pour"]), "bloc_specialites": bloc_specs,
        "exemple_commande": e(EXEMPLES.get(cat, "Ex. : votre commande")),
        "lignes_horaires": lignes, "adresse": e(fiche.get("adresse")), "lien_maps": e(fiche.get("lien_maps")),
        "bouton_tel": bouton_tel, "credit_photo": credit,
        "horaires_json": _json_script(ouvert_json(plages)), "nom_json": _json_script(fiche["nom"]),
        "wa_json": _json_script(whatsapp),
    }
    gabarit = (config.GABARITS / "commerce_de_bouche.html").read_text(encoding="utf-8")
    page = re.sub(r"\{\{ (\w+) \}\}", lambda m: str(valeurs[m.group(1)]), gabarit)
    return page, copies


def ecrire_page(racine: Path, slug: str, page: str, copies: list[Path]) -> Path:
    dossier = racine / "demo" / slug
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "index.html").write_text(page, encoding="utf-8")
    for f in copies:
        shutil.copy2(f, dossier / f.name)
    return dossier / "index.html"


def preparer_racine(racine: Path):
    """Fichiers communs : noindex partout, robots.txt, accueil neutre (aucune liste de prospects)."""
    racine.mkdir(parents=True, exist_ok=True)
    (racine / "_headers").write_text(
        "/*\n  X-Robots-Tag: noindex, nofollow, noarchive\n  Referrer-Policy: no-referrer\n"
        "  X-Content-Type-Options: nosniff\n", encoding="utf-8")
    (racine / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    (racine / "index.html").write_text(
        '<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="robots" content="noindex">'
        '<meta name="viewport" content="width=device-width, initial-scale=1"><title>BRUNFRAME</title>'
        '<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#14171a;color:#e8e6e1;'
        'font:16px/1.5 system-ui,sans-serif;text-align:center;padding:24px}</style></head>'
        f'<body><p>BRUNFRAME — maquettes privées.<br>{config.ANDY_TEL}</p></body></html>', encoding="utf-8")
    (racine / "404.html").write_text(
        '<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="robots" content="noindex">'
        '<meta name="viewport" content="width=device-width, initial-scale=1"><title>Page retirée</title></head>'
        '<body style="font:16px system-ui;padding:24px">Cette maquette n\'est plus en ligne.</body></html>',
        encoding="utf-8")
