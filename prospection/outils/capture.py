"""Capture d'une page locale (Playwright).

    python outils/capture.py page.html sortie.png             # 390×844, densité 2 (pour le mail)
    python outils/capture.py page.html sortie.png --full      # page entière, densité 1 (pour relire)
    python outils/capture.py page.html sortie.png --desktop   # 1280×800

Affiche aussi les erreurs JavaScript et toute requête qui sortirait de la page (interdit).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    page_html = Path(sys.argv[1]).resolve()
    sortie = Path(sys.argv[2]).resolve()
    full, desktop = "--full" in sys.argv, "--desktop" in sys.argv
    sortie.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        nav = pw.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        ctx = nav.new_context(
            viewport={"width": 1280, "height": 800} if desktop else {"width": 390, "height": 844},
            device_scale_factor=1 if (full or desktop) else 2, is_mobile=not desktop, has_touch=not desktop,
            locale="fr-FR", timezone_id="Europe/Paris", reduced_motion="reduce")
        page = ctx.new_page()
        problemes = []
        page.on("pageerror", lambda e: problemes.append(f"ERREUR JS : {e}"))
        page.on("request", lambda r: problemes.append(f"REQUÊTE EXTERNE : {r.url}")
                if not r.url.startswith(("file:", "data:", "blob:")) else None)
        page.goto(page_html.as_uri())
        page.wait_for_load_state("networkidle")
        page.evaluate("document.fonts && document.fonts.ready")
        page.wait_for_timeout(400)
        page.screenshot(path=str(sortie), full_page=full)
        nav.close()
    print(f"capture : {sortie}")
    print("\n".join(problemes) if problemes else "aucune erreur, aucune requête externe")


if __name__ == "__main__":
    main()
