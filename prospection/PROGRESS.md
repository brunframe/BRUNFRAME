# PROGRESS — machine de prospection (mis à jour le 16/11/2026)

## Fait (Sprint 1, code)
- `liste_noire.py` : Envoyés Gmail (destinataires, nom tiré de l'objet, site cité dans le mail, réponses,
  « non »/« stop », rejets), « Mes appels de 14h » (format en colonnes), fusion sans perte des lignes manuelles.
- `prospects.py` : Places API (New) 8 catégories × 5 quartiers du centre, puis 6 quartiers voisins si besoin ;
  filtres (30 avis / 4,3, ouvert, chaînes, casher, Shemtov, outil de commande, liste noire, 60 jours) ;
  état du site (aucun, réseau social, cassé, Wix/gratuit, pas mobile, sans commande) ; score ;
  2 spécialités vérifiées dans les avis ; meilleur créneau d'appel ; observation par `claude -p` (vérifiée).
  Compteur mensuel par SKU (900) ; `--rafraichir` à 30 jours.
- `maquette.py` : gabarit « commerce de bouche » (mobile, noindex, sans ressource externe, aperçu du message
  WhatsApp, lien wa.me si mobile), capture 390×844, retrait à J+21, 1 déploiement Cloudflare Pages par jour.
- `appels_du_jour.py` : archive la veille → Suivi / Prospects / Liste noire ; 10 colonnes au format
  « Mes appels de 14h » ; menu Résultat.
- `init_sheet.py`, tâches Windows (`taches_windows/installer_taches.ps1`), README, `.env.example`.
- Tests : `python -m unittest discover -s tests` (17, dont un Sheet simulé sur 2 jours), chaîne `--hors-ligne` complète.

## Reste à faire
- Andy : accès Google Cloud (facturation, 3 API, clé, OAuth « En production »), partage de « Mes appels de 14h »
  avec brunframe@gmail.com, compte Cloudflare + jeton, puis la validation en `--test` (README § 3).
- Premier passage réel, contrôle de 5 maquettes à la main avant les premiers appels.
- Sprint 2 : `mails.py` (J0 / J+5, 10 par jour, 8 à 20 min d'écart), `dm.py`, `suivi.py`, tableau de bord.
- Niche suivante (retouches, opticiens, fleuristes) : catégories prêtes à ajouter dans `config.py`, mais
  les textes d'appel restent ceux des commerces de bouche.

## Prochaine commande
```powershell
cd prospection; .venv\Scripts\activate; python init_sheet.py
```
