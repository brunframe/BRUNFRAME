"""Génère la page de chaque prospect qualifié, fait la capture mobile (390×844),
retire les maquettes arrivées à J+21 sans suite, et déploie UNE fois par jour.

    python maquette.py --test               # pages + captures dans sorties/test/, aucun déploiement
    python maquette.py                      # pages + captures + déploiement Cloudflare Pages
    python maquette.py --max 5              # au plus 5 nouvelles maquettes
    python maquette.py --refaire <slug>     # régénère une maquette (après personnalisation)
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys

from brunframe import accroches, config, journal
from brunframe import pipeline as pl
from brunframe.horaires import plages_depuis_places
from brunframe.places import PlafondAtteint, Places, nom
from brunframe.rendu import ecrire_page, preparer_racine, rendre
from brunframe.textes import lire_date, slugifier, tel_national

ETAT_DEPLOIEMENT = config.STATE / "deploiement.json"


def capturer(pages: list[tuple[str, object]], dossier, log) -> dict[str, str]:
    """Captures Playwright au format mobile 390×844 (densité 2 pour le mail)."""
    if not pages:
        return {}
    from playwright.sync_api import sync_playwright
    dossier.mkdir(parents=True, exist_ok=True)
    res = {}
    with sync_playwright() as pw:
        navigateur = pw.chromium.launch(executable_path=config.CHROMIUM_PATH or None)
        ctx = navigateur.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                     is_mobile=True, has_touch=True, locale="fr-FR",
                                     timezone_id="Europe/Paris", reduced_motion="reduce")
        page = ctx.new_page()
        for slug, chemin in pages:
            page.goto(chemin.as_uri())
            page.wait_for_load_state("load")
            sortie = dossier / f"{slug}.png"
            page.screenshot(path=str(sortie))
            res[slug] = str(sortie)
            log.info("capture %s", sortie.name)
        navigateur.close()
    return res


def empreinte(racine) -> str:
    h = hashlib.sha256()
    for f in sorted(racine.rglob("*")):
        if f.is_file():
            h.update(str(f.relative_to(racine)).encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def deployer(racine, log, forcer: bool = False) -> bool:
    """Cloudflare Pages via wrangler. Un seul déploiement par jour, et seulement s'il y a du nouveau."""
    etat = json.loads(ETAT_DEPLOIEMENT.read_text(encoding="utf-8")) if ETAT_DEPLOIEMENT.exists() else {}
    emp = empreinte(racine)
    if not forcer and etat.get("empreinte") == emp:
        log.info("déploiement inutile : rien n'a changé depuis le %s", etat.get("date"))
        return True
    if not forcer and etat.get("date") == str(dt.date.today()):
        log.info("déjà déployé aujourd'hui : les nouvelles maquettes partiront demain (ou --forcer-deploiement)")
        return False
    for v in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
        if not os.environ.get(v):
            raise RuntimeError(f"{v} manquant dans .env (voir README, « Hébergement »).")
    npx = shutil.which("npx")
    if not npx:
        raise RuntimeError("npx introuvable : installez Node.js LTS (voir README).")
    cmd = [npx, "--yes", "wrangler@4", "pages", "deploy", str(racine), "--project-name", config.CF_PROJET,
           "--branch", "main", "--commit-dirty=true"]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    log.info("wrangler : %s", (r.stdout + r.stderr).strip()[-600:])
    if r.returncode != 0:
        raise RuntimeError(f"déploiement Cloudflare échoué (code {r.returncode}) : {(r.stderr or r.stdout)[-300:]}")
    config.STATE.mkdir(parents=True, exist_ok=True)
    ETAT_DEPLOIEMENT.write_text(json.dumps({"date": str(dt.date.today()), "empreinte": emp}), encoding="utf-8")
    return True


def principal(args, log):
    jour = dt.date.today()
    c = None if args.hors_ligne else pl.classeur()
    lignes = pl.charger_prospects(args, c)
    racine = (config.SORTIES_TEST / "site") if args.test else config.SITE
    captures = (config.SORTIES_TEST / "captures") if args.test else config.CAPTURES
    preparer_racine(racine)
    places = Places(hors_ligne=args.hors_ligne, log=log)
    modifiees: dict[int, dict] = {}

    # 1. Retrait à J+21 sans suite
    for l in lignes:
        retrait = lire_date(l.get("Retrait prévu"))
        if (retrait and retrait <= jour and l.get("Slug") and l.get("Statut") not in config.STATUTS_PROTEGES
                and l.get("Statut") != "Maquette retirée"):
            dossier = racine / "demo" / l["Slug"]
            if dossier.exists():
                shutil.rmtree(dossier)
            l["Statut"] = "Maquette retirée"
            modifiees[id(l)] = l
            log.info("retirée (J+21) : %s", l["Nom"])

    # 2. Nouvelles maquettes
    pris = {l.get("Slug") for l in lignes if l.get("Slug")}
    if args.refaire:
        selection = [l for l in lignes if l.get("Slug") == args.refaire]
    else:
        selection = [l for l in lignes if l.get("Statut") == "Qualifié"
                     and not (l.get("Slug") and (racine / "demo" / l["Slug"] / "index.html").exists())]
        selection.sort(key=lambda l: -pl.flottant(l.get("Score")))
        selection = selection[:args.max]
    a_capturer = []
    for l in selection:
        try:
            p = places.fiche(l["place_id"])
        except PlafondAtteint as e:
            log.warning("%s", e)
            break
        if not p:
            log.warning("fiche introuvable : %s", l["Nom"])
            continue
        if p.get("businessStatus", "OPERATIONAL") != "OPERATIONAL":
            l["Statut"] = "Fermé"
            modifiees[id(l)] = l
            continue
        cat = pl.cle_categorie(l.get("Catégorie", ""))
        slug = l.get("Slug") or slugifier(nom(p) or l["Nom"])
        if slug in pris and slug != l.get("Slug"):
            slug = slugifier(f"{slug}-{l.get('Quartier', '')}")
        pris.add(slug)
        plages = plages_depuis_places(p.get("regularOpeningHours"))
        fiche = {"nom": nom(p) or l["Nom"], "quartier": l.get("Quartier", ""),
                 "adresse": p.get("formattedAddress") or l.get("Adresse", ""),
                 "telephone": tel_national(p.get("nationalPhoneNumber", "")) or l.get("Téléphone", ""),
                 "note": p.get("rating", l.get("Note")), "nb_avis": p.get("userRatingCount", l.get("Nb avis")),
                 "lien_maps": p.get("googleMapsUri") or l.get("Lien Google Maps", ""),
                 "specialites": [l.get("Spécialité 1", ""), l.get("Spécialité 2", "")]}
        page, copies = rendre(fiche, cat, accroches.accroche(jour, cat), plages, slug)
        chemin = ecrire_page(racine, slug, page, copies)
        l.update({"Slug": slug, "Maquette le": str(jour), "Note": fiche["note"], "Nb avis": fiche["nb_avis"]})
        modifiees[id(l)] = l
        a_capturer.append((slug, chemin))
        log.info("maquette : %s -> demo/%s/", l["Nom"], slug)

    for slug, png in capturer(a_capturer, captures, log).items():
        for l in lignes:
            if l.get("Slug") == slug:
                l["Capture"] = png

    # 3. Déploiement (un par jour), puis seulement « Maquette prête »
    en_attente = [l for l in lignes if l.get("Slug") and l.get("Statut") == "Qualifié"
                  and (racine / "demo" / l["Slug"] / "index.html").exists()]
    if args.test:
        log.info("TEST : aucun déploiement. %d pages dans %s", len(a_capturer), racine / "demo")
        publie = True
    elif args.sans_deploiement:
        publie = False
    else:
        publie = deployer(racine, log, args.forcer_deploiement) if (en_attente or modifiees) else True
    if publie:
        for l in en_attente:
            l["Statut"] = "Maquette prête"
            l["Lien maquette"] = ((racine / "demo" / l["Slug"] / "index.html").as_uri() if args.test
                                  else f"{config.DEMO_BASE_URL}/demo/{l['Slug']}/")
            modifiees[id(l)] = l
    log.info("%d nouvelles maquettes, %d en ligne ce jour", len(a_capturer), len(en_attente) if publie else 0)

    if args.test:
        pl.enregistrer_test(lignes)  # enchaîne avec appels_du_jour.py --test
        return
    if modifiees:
        c.mettre_a_jour("Prospects", config.ONGLETS["Prospects"], list(modifiees.values()))


if __name__ == "__main__":
    p = journal.arguments(__doc__)
    p.add_argument("--max", type=int, default=20, help="nouvelles maquettes au plus (défaut 20)")
    p.add_argument("--refaire", default="", help="slug d'une maquette à régénérer")
    p.add_argument("--sans-deploiement", action="store_true")
    p.add_argument("--forcer-deploiement", action="store_true")
    a = p.parse_args()
    sys.exit(journal.lancer("maquette", principal, a))
