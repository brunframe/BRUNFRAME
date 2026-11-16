"""Tests sans réseau : python -m unittest discover -s tests -v"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from brunframe import accroches, config, filtres, horaires, listenoire, specialites, textes  # noqa: E402
from brunframe.google_api import Classeur  # noqa: E402
from faux_sheets import FauxSheets  # noqa: E402

LOG = logging.getLogger("tests")


def periodes(*jours):
    """jours : (jour Google 0=dimanche, [(h1, m1, h2, m2)])"""
    return {"periods": [{"open": {"day": d, "hour": a, "minute": b}, "close": {"day": d, "hour": c, "minute": e}}
                        for d, ps in jours for a, b, c, e in ps]}


BOUCHERIE = periodes(*[(d, [(8, 0, 12, 30), (14, 30, 19, 0)]) for d in (2, 3, 4, 5)], (6, [(7, 30, 13, 0)]))


class Horaires(unittest.TestCase):
    def test_format_et_relecture(self):
        p = horaires.plages_depuis_places(BOUCHERIE)
        texte = horaires.format_horaires(p)
        self.assertEqual(texte, "Lun fermé · Mar–Ven 8h–12h30, 14h30–19h · Sam 7h30–13h · Dim fermé")
        from appels_du_jour import _plages_texte
        self.assertEqual(_plages_texte({"Horaires": texte}), p)

    def test_creneau_hors_rush_et_ouvert(self):
        p = horaires.plages_depuis_places(BOUCHERIE)
        # fermée à 14h, rush boucherie dès 17h -> 16h15–17h, mardi à vendredi
        self.assertEqual(horaires.meilleur_creneau(p, "boucherie"), "16h15–17h (mar–ven)")

    def test_quand_appeler_lendemain_si_ferme(self):
        p = horaires.plages_depuis_places(BOUCHERIE)
        texte, jour = horaires.quand_appeler(p, "boucherie", dt.date(2026, 11, 16))  # lundi
        self.assertTrue(texte.startswith("Demain (mardi) 16h15"), texte)
        self.assertEqual(jour, dt.date(2026, 11, 17))

    def test_nuit_et_inconnu(self):
        p = horaires.plages_depuis_places({"periods": [{"open": {"day": 5, "hour": 18, "minute": 0},
                                                        "close": {"day": 6, "hour": 2, "minute": 0}}]})
        self.assertEqual(p[4], [(1080, 1440)])
        self.assertEqual(p[5], [(0, 120)])
        self.assertIn("inconnus", horaires.meilleur_creneau(horaires.plages_depuis_places(None), "traiteur"))


class Accroches(unittest.TestCase):
    def test_calendrier(self):
        self.assertEqual(accroches.cle_accroche(dt.date(2026, 11, 16), "boucherie"), "fetes")
        self.assertEqual(accroches.cle_accroche(dt.date(2026, 12, 20), "caviste"), "fetes")
        self.assertEqual(accroches.cle_accroche(dt.date(2027, 1, 8), "boulangerie"), "galette")
        self.assertEqual(accroches.cle_accroche(dt.date(2027, 1, 8), "boucherie"), "general")
        self.assertEqual(accroches.cle_accroche(dt.date(2027, 2, 10), "chocolatier"), "saint_valentin")
        self.assertEqual(accroches.paques(2027), dt.date(2027, 3, 28))
        self.assertEqual(accroches.cle_accroche(dt.date(2027, 3, 20), "boucherie"), "paques")


class Specialites(unittest.TestCase):
    def test_extraction_et_garde_fou(self):
        avis = ["La forêt noire est top", "Macarons divins, forêt-noire parfaite", "Accueil"]
        self.assertEqual(specialites.extraire(avis, "patisserie"), ["forêt-noire", "macarons"])
        self.assertTrue(specialites.citee_dans("macarons", avis))
        self.assertFalse(specialites.citee_dans("paris-brest", avis))

    def test_mot_entier(self):
        self.assertEqual(specialites.extraire(["super vinaigre balsamique"], "epicerie"), ["vinaigres"])


class Filtres(unittest.TestCase):
    def test_urls(self):
        self.assertEqual(filtres.classer_url(""), "aucun")
        self.assertEqual(filtres.classer_url("https://www.facebook.com/x"), "reseau_social")
        self.assertEqual(filtres.classer_url("https://x.wixsite.com/site"), "wix_gratuit")
        self.assertEqual(filtres.classer_url("https://www.ubereats.com/fr/store/x"), "commande_en_ligne")
        self.assertIsNone(filtres.classer_url("https://boucherie-muller.fr"))

    def test_html(self):
        corps = "<p>" + "Bienvenue chez nous, viande d'Alsace. " * 20 + "</p>"
        self.assertEqual(filtres.analyser_html("<html><head></head>" + corps), "pas_mobile")
        mobile = '<meta name="viewport" content="width=device-width">' + corps
        self.assertEqual(filtres.analyser_html(mobile), "sans_commande")
        self.assertEqual(filtres.analyser_html(mobile + "<a>Ajouter au panier</a>"), "commande_en_ligne")
        self.assertEqual(filtres.analyser_html(mobile + "Site en construction"), "casse")

    def test_chaines_casher_score(self):
        chaines = [textes.normaliser(c) for c in ("Paul", "Nicolas")]
        self.assertTrue(filtres.est_chaine("PAUL", chaines))
        self.assertTrue(filtres.est_chaine("Nicolas Kléber", chaines))
        self.assertFalse(filtres.est_chaine("Boucherie Paul Muller", chaines))
        self.assertTrue(filtres.est_casher("Boucherie cacher du centre"))
        self.assertFalse(filtres.est_casher("Boucherie du cachet"))
        self.assertGreater(filtres.score(100, 4.5, "aucun"), filtres.score(100, 4.5, "sans_commande"))


class ListeNoireTests(unittest.TestCase):
    def setUp(self):
        self.ln = listenoire.ListeNoire([
            {"Clé": "contact@boucherie-muller.fr", "Type": "email", "Nom": "Boucherie Muller",
             "Dernier contact": "2026-11-10", "A répondu": "non", "Définitif": "non"},
            {"Clé": "2000aiguilles67@gmail.com", "Type": "email", "Nom": "",
             "Dernier contact": "2026-11-10", "A répondu": "non", "Définitif": "non"},
            {"Clé": "vieux@gmail.com", "Type": "email", "Nom": "Vieille Cave",
             "Dernier contact": "2026-08-01", "A répondu": "non", "Définitif": "non"},
            {"Clé": "03 88 22 99 98", "Type": "appel", "Nom": "Les Mille Saveurs", "Téléphone": "03 88 22 99 98",
             "Définitif": "oui"},
        ], dt.date(2026, 11, 16))

    def test_correspondances(self):
        self.assertTrue(self.ln.motif(site="https://www.boucherie-muller.fr/accueil"))
        self.assertTrue(self.ln.motif(nom="Aux Mille Saveurs"))
        self.assertTrue(self.ln.motif(telephone="+33 3 88 22 99 98"))
        self.assertTrue(self.ln.motif(nom="2000 Aiguilles"))
        self.assertIsNone(self.ln.motif(nom="Vieille Cave"))  # contacté il y a plus de 60 jours, sans réponse
        self.assertIsNone(self.ln.motif(nom="Pâtisserie Kléber", telephone="03 88 00 00 00"))

    def test_gmail_et_feuille(self):
        fils = [{"messages": [
            {"internalDate": "1794725044000", "labelIds": ["SENT"], "snippet": "Votre site : https://www.google.com/url?q=http://x.wixsite.com/y&amp;sa=E",
             "payload": {"headers": [{"name": "From", "value": "Andy <moi@test>"}, {"name": "To", "value": "a@b.fr"},
                                     {"name": "Subject", "value": "Chez X : votre site"}]}},
            {"internalDate": "1794825044000", "labelIds": ["INBOX"], "snippet": "Non merci",
             "payload": {"headers": [{"name": "From", "value": "a@b.fr"}, {"name": "Subject", "value": "Re: Chez X"}]}}]}]
        e = listenoire.entrees_gmail(fils, "moi@test")["a@b.fr"]
        self.assertEqual((e["Nom"], e["Site"], e["Définitif"]), ("Chez X", "http://x.wixsite.com/y", "oui"))
        feuille = [["Appel", "1. Novatech (démo)", "2. RD"], ["Numéro", "07 68 51 71 28 (4 rue X)", "06 40 28 24 78"]]
        r = listenoire.entrees_feuille(feuille, "Mes appels")
        self.assertEqual([x["Nom"] for x in r], ["Novatech", "RD"])
        self.assertEqual(r[0]["Téléphone"], "07 68 51 71 28")


class Textes(unittest.TestCase):
    def test_divers(self):
        self.assertEqual(textes.tel_national("+33388229998"), "03 88 22 99 98")
        self.assertTrue(textes.est_mobile("06 30 83 59 78"))
        self.assertEqual(textes.slugifier("Pâtisserie Kléber & Fils"), "patisserie-kleber-fils")
        self.assertEqual(textes.possessif("macarons"), "vos macarons")
        self.assertTrue(textes.mots_interdits("N'hésitez pas à booster"))

    def test_validation_claude(self):
        from prospects import valider
        faits = {"note": "4,7", "avis": 120, "extraits": ["super"]}
        self.assertTrue(valider("« 120 avis à 4,7 : vos clients sont ravis. Mais pour commander, il faut appeler. »", faits))
        self.assertFalse(valider("« 500 avis à 4,7 : mais pour commander, il faut vous appeler. »", faits))
        self.assertFalse(valider("« 120 avis à 4,7. N'hésitez pas, je me permets de vous appeler. »", faits))


class Rendu(unittest.TestCase):
    def test_page(self):
        from brunframe.rendu import contraste, rendre, texte_sur
        p = horaires.plages_depuis_places(BOUCHERIE)
        fiche = {"nom": "Boucherie <Test>", "quartier": "Krutenau", "adresse": "1 rue X", "telephone": "06 39 98 00 11",
                 "note": 4.8, "nb_avis": 214, "lien_maps": "https://maps.google.com/?cid=1", "specialites": ["presskopf", ""]}
        page, _ = rendre(fiche, "boucherie", accroches.accroche(dt.date(2026, 11, 16), "boucherie"), p, "test")
        self.assertIn('name="robots" content="noindex', page)
        self.assertIn("214 avis Google", page)
        self.assertIn("Google Maps", page)
        self.assertEqual(page.count("BRUNFRAME"), 1)  # pied de page uniquement
        self.assertIn("Maquette préparée par BRUNFRAME", page)
        self.assertIn("Boucherie &lt;Test&gt;", page)
        self.assertIn('"33639980011"', page)
        self.assertNotIn("{{", page)
        self.assertIsNone(re.search(r'(src|href)="https?://(?!maps\.google)', page), "aucune ressource externe")
        self.assertNotRegex(page, r"\d+(,\d+)? ?€", "aucun prix")
        for cat, c in config.CATEGORIES.items():
            self.assertGreaterEqual(contraste(c["couleurs"]["accent"], texte_sur(c["couleurs"]["accent"])), 4.5, cat)


class CircuitSheet(unittest.TestCase):
    """Chemin réel (Sheet) simulé : liste du jour, résultats d'Andy, archivage le lendemain."""

    def test_deux_jours(self):
        import appels_du_jour as ad
        faux = FauxSheets()
        c = Classeur("faux", svc=faux)
        for onglet, entetes in config.ONGLETS.items():
            c.assurer_onglet(onglet, entetes)
        prospects = []
        for i in range(12):
            prospects.append({"place_id": f"P{i}", "Nom": f"Commerce {i}", "Catégorie": "Boucherie-charcuterie",
                              "Adresse": f"{i} rue X, Strasbourg", "Téléphone": f"01 99 00 02 {i:02d}",
                              "Horaires": "Lun fermé · Mar–Ven 8h–12h30, 14h30–19h · Sam 7h30–13h · Dim fermé",
                              "État du site": "Aucun site", "Note": 4.6, "Nb avis": 50 + i,
                              "Spécialité 1": "presskopf", "Observation": "« 50 avis à 4,6. »",
                              "Score": 100 + i, "Lien maquette": f"https://exemple/demo/c{i}/",
                              "Statut": "Maquette prête", "Nb appels": 0})
        c.ajouter("Prospects", config.ONGLETS["Prospects"], prospects)
        args = argparse.Namespace(test=False, hors_ligne=False, date="2026-11-17")
        with mock.patch("brunframe.pipeline.classeur", return_value=c):
            ad.principal(args, LOG)
            liste = ad.lire_liste(c)
            self.assertEqual(len(liste), 10)
            self.assertEqual(liste[0]["Appel"], "1. Commerce 11")  # meilleur score d'abord
            # Andy remplit la ligne Résultat
            grille = faux.grilles["Appels du jour"]
            ligne = ad.CHAMPS.index("Résultat")
            grille[ligne][1:4] = ["RDV pris", "Non", "Pas de réponse"]
            args.date = "2026-11-18"
            ad.principal(args, LOG)
        _, suivi = c.lire("Suivi")
        self.assertEqual(sorted(s["Résultat"] for s in suivi if s["Type"] == "appel"), ["Non", "Pas de réponse", "RDV pris"])
        _, noire = c.lire("Liste noire")
        self.assertEqual([n["Clé"] for n in noire], ["P10"])
        _, ps = c.lire("Prospects")
        etat = {p["place_id"]: p for p in ps}
        self.assertEqual(etat["P11"]["Statut"], "RDV")
        self.assertEqual(etat["P10"]["Statut"], "Non")
        self.assertEqual(etat["P9"]["Statut"], "À rappeler")
        self.assertEqual(etat["P9"]["Prochain appel"], "2026-11-18")
        self.assertEqual(etat["P11"]["Retrait prévu"], "2026-12-08")
        nouvelle = [x["Réf. (ne pas modifier)"] for x in ad.lire_liste(c)]
        self.assertEqual(nouvelle[0], "P9")  # le rappel passe en premier
        self.assertNotIn("P10", nouvelle)
        self.assertNotIn("P11", nouvelle)
        # validation du menu Résultat posée
        self.assertTrue(any("setDataValidation" in r for r in faux.requetes))


class CircuitMaquette(unittest.TestCase):
    """maquette.py en mode réel : Places et déploiement simulés, page écrite, statut mis à jour."""

    def test_maquette_puis_retrait(self):
        import tempfile
        import maquette as mq
        from brunframe.places import Places
        faux = FauxSheets()
        c = Classeur("faux", svc=faux)
        c.assurer_onglet("Prospects", config.ONGLETS["Prospects"])
        c.ajouter("Prospects", config.ONGLETS["Prospects"], [
            {"place_id": "DEMO_1", "Nom": "Boucherie Démo du Marché", "Catégorie": "Boucherie-charcuterie",
             "Quartier": "Grande Île", "Statut": "Qualifié", "Score": 900, "Spécialité 1": "presskopf"},
            {"place_id": "DEMO_9", "Nom": "Cave Fictive Esplanade", "Catégorie": "Caviste", "Quartier": "Esplanade",
             "Statut": "Maquette prête", "Slug": "cave-fictive-esplanade", "Retrait prévu": "2026-01-01"}])
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(config, "SITE", Path(tmp) / "site"), \
                mock.patch("brunframe.pipeline.classeur", return_value=c), \
                mock.patch.object(mq, "Places", lambda **kw: Places(hors_ligne=True)), \
                mock.patch.object(mq, "capturer", return_value={}), \
                mock.patch.object(mq, "deployer", return_value=True) as dep:
            (Path(tmp) / "site" / "demo" / "cave-fictive-esplanade").mkdir(parents=True)
            args = argparse.Namespace(test=False, hors_ligne=False, max=5, refaire="",
                                      sans_deploiement=False, forcer_deploiement=False)
            mq.principal(args, LOG)
            self.assertTrue((Path(tmp) / "site" / "demo" / "boucherie-demo-du-marche" / "index.html").exists())
            self.assertFalse((Path(tmp) / "site" / "demo" / "cave-fictive-esplanade").exists())
            self.assertTrue((Path(tmp) / "site" / "_headers").read_text().count("noindex"))
            dep.assert_called_once()
        _, ps = c.lire("Prospects")
        etat = {p["place_id"]: p for p in ps}
        self.assertEqual(etat["DEMO_1"]["Statut"], "Maquette prête")
        self.assertTrue(etat["DEMO_1"]["Lien maquette"].endswith("/demo/boucherie-demo-du-marche/"))
        self.assertEqual(etat["DEMO_9"]["Statut"], "Maquette retirée")


if __name__ == "__main__":
    unittest.main()
