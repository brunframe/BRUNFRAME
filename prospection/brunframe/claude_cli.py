"""`claude -p` en mode non interactif, seulement pour les phrases personnalisées.

Le prompt passe par l'entrée standard (fiable sous Windows), dans un dossier
vide pour ne charger aucun contexte de projet. Toute réponse est validée ;
en cas de doute, le code déterministe prend le relais.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile

from . import config


def disponible() -> bool:
    return shutil.which(config.CLAUDE_CMD) is not None


def demander_json(prompt: str, timeout: int = 240):
    exe = shutil.which(config.CLAUDE_CMD)
    if not exe:
        return None
    with tempfile.TemporaryDirectory() as vide:
        try:
            r = subprocess.run([exe, "-p", "--output-format", "text"], input=prompt, text=True,
                               encoding="utf-8", capture_output=True, timeout=timeout, cwd=vide)
        except (subprocess.TimeoutExpired, OSError):
            return None
    if r.returncode != 0:
        return None
    texte = r.stdout.strip()
    texte = re.sub(r"^```(?:json)?|```$", "", texte, flags=re.M).strip()
    debut = min([i for i in (texte.find("{"), texte.find("[")) if i >= 0], default=-1)
    if debut < 0:
        return None
    try:
        return json.loads(texte[debut:])
    except json.JSONDecodeError:
        try:
            return json.JSONDecoder().raw_decode(texte[debut:])[0]
        except json.JSONDecodeError:
            return None
