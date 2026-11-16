# Personnaliser une maquette (facultatif)

Par défaut, la maquette prend les couleurs de sa catégorie et n'a pas de photo de produit.
Pour l'habiller aux couleurs du commerce :

1. Créez `personnalisation/<slug>.json` (le slug est dans la colonne Slug du Sheet) :

```json
{
  "fond": "#2B0E12",
  "accent": "#B3263A",
  "clair": "#F7ECEC",
  "logo": "logo.png",
  "photo": "devanture.jpg",
  "credit_photo": "Boucherie X (page Instagram de la boutique)",
  "whatsapp": "06 12 34 56 78",
  "specialites": ["presskopf", "côte de bœuf"]
}
```

2. Mettez les fichiers dans `personnalisation/<slug>/` (logo.png, devanture.jpg).
3. `python maquette.py --refaire <slug>`

Règles : seulement des photos publiées par le commerce lui-même, toujours avec `credit_photo`
(la maquette refuse une photo sans crédit). Aucune image générée présentée comme un vrai produit.
Ce dossier n'est pas versionné dans Git.
