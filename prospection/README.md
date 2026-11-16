# BRUNFRAME — machine de prospection (Sprint 1)

Ce que fait le système : chaque matin à 7h, l'onglet **Appels du jour** du Sheet « BRUNFRAME — Pipeline »
contient 10 commerces à appeler. Pour chacun : le numéro, quand appeler, le script de l'appel, le lien de la
maquette et les objections probables. Andy ne remplit que la ligne **Résultat**.

| Script | Rôle | Quand (PC Windows) |
|---|---|---|
| `liste_noire.py` | Envoyés de brunframe@gmail.com + « Mes appels de 14h » + « non »/« stop » → onglet Liste noire | tous les jours 6h00 |
| `prospects.py` | Google Places par catégorie × quartier, filtres, score → 50 fiches dans Prospects | dimanche 18h00 |
| `prospects.py --rafraichir` | remet à jour les fiches de plus de 30 jours (conditions Google) | dimanche 17h30 |
| `maquette.py` | page de chaque prospect, capture mobile 390×844, retrait à J+21, **1 déploiement par jour** | lun-ven 6h30 |
| `appels_du_jour.py` | archive les résultats de la veille, écrit les 10 appels du jour | lun-ven 7h00 |

Chaque script a `--test` (n'écrit rien dans le Sheet, ne déploie rien : tout va dans `sorties/test/`)
et `--hors-ligne` (données fictives de `fixtures/`, sans aucun accès réseau). Journal : `logs/`.
En cas d'échec, l'erreur est écrite en clair dans l'onglet Suivi.

## 1. Installation sur le PC Windows (une fois)

1. Installer **Python 3.12** (python.org, cocher « Add python.exe to PATH ») et **Node.js LTS** (pour le déploiement).
2. Récupérer le dépôt, puis dans PowerShell :
   ```powershell
   cd chemin\vers\BRUNFRAME\prospection
   py -3.12 -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   python -m playwright install chromium
   copy .env.example .env
   ```
3. Claude Code doit être connecté sur ce PC (`claude` dans un terminal, puis `/login`). Sans lui, les
   phrases d'observation sont écrites par un modèle fixe : ça marche, en moins personnalisé.

## 2. Accès à préparer (Claude Code les demande ici)

**Google Cloud** (avec brunframe@gmail.com) — console.cloud.google.com :
1. Nouveau projet « brunframe-prospection », **facturation activée** (obligatoire pour Places, même gratuit).
2. Activer : **Places API (New)**, **Google Sheets API**, **Gmail API**.
3. Identifiants → Créer une clé API → la restreindre à « Places API (New) » → la coller dans `.env`
   (`GOOGLE_PLACES_API_KEY`).
4. Facturation → Budgets → alerte à 5 €. Le script s'arrête de lui-même à 900 appels par mois et par
   type de requête (la gratuité Google est de 1 000).
5. Écran de consentement OAuth : type Externe, nom « BRUNFRAME prospection », puis **Publier l'application**
   (« En production »). En mode « Test », Google coupe l'accès tous les 7 jours. L'avertissement
   « application non validée » est normal : Paramètres avancés → Continuer.
6. Identifiants → ID client OAuth → **Application de bureau** → télécharger le JSON →
   l'enregistrer sous `prospection\state\client_secret.json`.

**Feuille « Mes appels de 14h »** (propriété d'andybrun260909) : la partager en lecture avec
brunframe@gmail.com, et mettre son ID dans `.env` (`FEUILLES_A_EXCLURE`).

**Cloudflare Pages** (gratuit) — dash.cloudflare.com :
1. Créer un compte, noter l'**Account ID** (colonne de droite) → `CLOUDFLARE_ACCOUNT_ID`.
2. Mon profil → Jetons d'API → Créer → modèle personnalisé, permission « Cloudflare Pages : Modifier »
   → `CLOUDFLARE_API_TOKEN`.
3. Une fois : `npx wrangler@4 pages project create brunframe-demo --production-branch main`
   puis mettre l'adresse donnée (ex. `https://brunframe-demo.pages.dev`) dans `DEMO_BASE_URL`.

Pourquoi pas Netlify : sur l'offre gratuite actuelle, chaque déploiement coûte 15 crédits sur 300 par mois,
soit 20 déploiements. Un par jour ne tient pas, et le site de Shemtov serait coupé si le quota était épuisé.
Cloudflare Pages : 500 déploiements par mois, bande passante sans limite.

## 3. Validation en mode test (avant toute écriture réelle)

```powershell
python -m unittest discover -s tests        # tests sans réseau
python init_sheet.py                          # crée le Sheet « BRUNFRAME — Pipeline » (navigateur : choisir brunframe@gmail.com)
python liste_noire.py --test                  # -> sorties\test\liste_noire.csv
python prospects.py --test --nombre 10        # -> sorties\test\prospects.csv (vraie recherche Google, rien écrit)
python maquette.py --test --max 3             # -> sorties\test\site\demo\...\index.html + sorties\test\captures\
python appels_du_jour.py --test               # -> sorties\test\appels_du_jour.csv
```
Andy ouvre ces fichiers. S'ils lui conviennent :

```powershell
python liste_noire.py
python prospects.py
python maquette.py
python appels_du_jour.py
powershell -ExecutionPolicy Bypass -File taches_windows\installer_taches.ps1
```

## 4. Au quotidien

- **Appels du jour** : une colonne par commerce, comme « Mes appels de 14h ». Ligne jaune **Résultat** :
  `RDV pris`, `À rappeler`, `Pas de réponse`, `Non`, `Déjà équipé` (ou texte libre, ex. « rappeler jeudi 17h »).
- Le lendemain à 7h : « Non » et « Déjà équipé » → Liste noire ; « Pas de réponse » → rappel le jour
  ouvré suivant (3 essais, puis « Injoignable ») ; « À rappeler » → 2 jours ouvrés ; « RDV pris » → statut RDV.
- Une maquette est retirée 21 jours après le premier contact, sauf si le statut est RDV, Présentation ou Signé.
- Personnaliser une maquette (logo, devanture, couleurs) : voir `personnalisation/README.md`.
- Ajouter un « stop » à la main : une ligne dans Liste noire avec Définitif = oui.

## 5. Règles tenues par le code

- Données : Places API officielle uniquement. Seul le place_id est gardé durablement. Les avis sont lus en
  mémoire, jamais stockés : on garde 2 mots (les spécialités), vérifiés présents dans les avis. Les fiches
  sont remises à jour tous les 30 jours.
- Exclus d'office : chaînes (`config/chaines.txt`), casher sauf accord écrit (`ACCORD_CASHER_PLACE_IDS`),
  Shemtov, commerces avec un outil de commande en ligne, Liste noire, contacts de moins de 60 jours.
- Maquettes : noindex (balise + en-tête + robots.txt), aucune ressource externe ni mesure d'audience,
  aucun prix, BRUNFRAME seulement en pied de page, « avis Google » + attribution Google Maps.
- `claude -p` : un lot par exécution (10 commerces par appel), sortie vérifiée (mots interdits, aucun
  chiffre absent des faits). En cas de doute, la phrase vient du modèle fixe.
