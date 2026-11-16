"""Spécialités citées dans les avis : dictionnaire déterministe, sans invention.

Les avis ne sont jamais stockés : ils sont lus en mémoire, on ne garde que
les 2 mots trouvés.
"""
from __future__ import annotations

import re

from .textes import normaliser

# (forme affichée, [variantes normalisées]) — du plus spécifique au plus général.
DICO: dict[str, list[tuple[str, list[str]]]] = {
    "boulangerie": [
        ("kougelhopf", ["kougelhopf", "kouglof", "kugelhopf", "kougelhof"]),
        ("bretzels", ["bretzel"]), ("bredele", ["bredele", "bredala", "bredles"]),
        ("mannele", ["mannele", "manala", "mannala"]), ("pain d'épices", ["pain d epice"]),
        ("christstollen", ["stollen"]), ("galette des rois", ["galette"]),
        ("streusel", ["streusel"]), ("pain au levain", ["levain"]),
        ("baguette tradition", ["tradition"]), ("croissants", ["croissant"]),
        ("pains au chocolat", ["pain au chocolat", "pains au chocolat"]),
        ("flan", ["flan"]), ("brioche", ["brioche"]), ("pain de seigle", ["seigle"]),
        ("viennoiseries", ["viennoiserie"]), ("tartes", ["tarte"]),
    ],
    "patisserie": [
        ("forêt-noire", ["foret noire"]), ("paris-brest", ["paris brest"]),
        ("mille-feuille", ["mille feuille", "millefeuille"]), ("saint-honoré", ["saint honore", "st honore"]),
        ("tarte au citron", ["tarte au citron", "tartes au citron"]), ("macarons", ["macaron"]),
        ("éclairs", ["eclair"]), ("kougelhopf", ["kougelhopf", "kouglof", "kugelhopf"]),
        ("bredele", ["bredele", "bredala"]), ("bûches", ["buche"]), ("baba au rhum", ["baba"]),
        ("fraisier", ["fraisier"]), ("opéra", ["opera"]), ("religieuses", ["religieuse"]),
        ("tarte au fromage blanc", ["tarte au fromage", "kaskueche"]), ("cheesecake", ["cheesecake"]),
        ("entremets", ["entremet"]), ("galette des rois", ["galette"]), ("flan", ["flan"]),
        ("choux", ["chou a la creme", "choux"]), ("tartes aux fruits", ["tarte aux fruits"]),
        ("chocolat chaud", ["chocolat chaud"]), ("glaces", ["glace"]),
    ],
    "chocolatier": [
        ("pralinés", ["praline"]), ("ganaches", ["ganache"]), ("truffes", ["truffe"]),
        ("orangettes", ["orangette"]), ("mendiants", ["mendiant"]), ("florentins", ["florentin"]),
        ("chocolat chaud", ["chocolat chaud"]), ("bouchées", ["bouchee"]), ("macarons", ["macaron"]),
        ("pâte à tartiner", ["pate a tartiner"]), ("guimauves", ["guimauve"]), ("nougat", ["nougat"]),
        ("caramels", ["caramel"]), ("tablettes", ["tablette"]), ("calendriers de l'Avent", ["calendrier de l avent"]),
        ("œufs de Pâques", ["oeufs de paques", "oeuf de paques"]), ("bredele", ["bredele"]),
    ],
    "boucherie": [
        ("presskopf", ["presskopf"]), ("pâté en croûte", ["pate en croute"]),
        ("fleischschnacka", ["fleischschnacka", "fleischnaka"]), ("knacks", ["knack"]),
        ("côte de bœuf", ["cote de boeuf"]), ("tartare", ["tartare"]), ("foie gras", ["foie gras"]),
        ("chapons", ["chapon"]), ("merguez", ["merguez"]), ("saucisses", ["saucisse"]),
        ("lard", ["lard"]), ("jambon", ["jambon"]), ("terrines", ["terrine"]),
        ("boudin", ["boudin"]), ("cervelas", ["cervelas"]), ("rôtis", ["roti"]),
        ("gigot", ["gigot"]), ("volailles", ["volaille", "poulet"]), ("agneau", ["agneau"]),
        ("veau", ["veau"]), ("steaks hachés", ["steak hache", "steaks haches"]),
        ("choucroute", ["choucroute"]), ("baeckeoffe", ["baeckeoffe", "baekeoffe"]),
        ("tourtes", ["tourte"]), ("quiches", ["quiche"]), ("plats du jour", ["plat du jour"]),
    ],
    "fromagerie": [
        ("munster", ["munster"]), ("mont d'or", ["mont d or"]), ("comté", ["comte"]),
        ("beaufort", ["beaufort"]), ("raclette", ["raclette"]), ("fondue", ["fondue"]),
        ("plateaux de fromages", ["plateau"]), ("reblochon", ["reblochon"]), ("brie", ["brie"]),
        ("roquefort", ["roquefort"]), ("chèvres", ["chevre"]), ("burrata", ["burrata"]),
        ("tommes", ["tomme"]), ("époisses", ["epoisses"]), ("vacherin", ["vacherin"]),
        ("parmesan", ["parmesan"]), ("camembert", ["camembert"]), ("morbier", ["morbier"]),
        ("crèmerie", ["creme", "beurre"]),
    ],
    "caviste": [
        ("crémants", ["cremant"]), ("rieslings", ["riesling"]), ("gewurztraminer", ["gewurz"]),
        ("pinot noir", ["pinot noir"]), ("pinot gris", ["pinot gris"]), ("sylvaner", ["sylvaner"]),
        ("champagnes", ["champagne"]), ("vins nature", ["vin nature", "vins nature", "vin naturel"]),
        ("whiskies", ["whisky", "whiskies"]), ("rhums", ["rhum"]), ("bières artisanales", ["biere"]),
        ("vins bio", ["vin bio", "vins bio"]), ("bourgognes", ["bourgogne"]), ("bordeaux", ["bordeaux"]),
        ("spiritueux", ["spiritueux"]), ("coffrets cadeaux", ["coffret"]),
    ],
    "epicerie": [
        ("huiles d'olive", ["huile d olive"]), ("truffes", ["truffe"]), ("foie gras", ["foie gras"]),
        ("caviar", ["caviar"]), ("saumon fumé", ["saumon fume"]), ("pâtes fraîches", ["pates fraiches"]),
        ("produits italiens", ["italien"]), ("épices", ["epice"]), ("thés", ["the "]),
        ("cafés", ["cafe"]), ("miels", ["miel"]), ("confitures", ["confiture"]),
        ("terrines", ["terrine"]), ("olives", ["olive"]), ("vinaigres", ["vinaigre"]),
        ("biscuits", ["biscuit"]), ("coffrets cadeaux", ["coffret"]), ("charcuterie", ["charcuterie"]),
        ("fromages", ["fromage"]), ("vins", ["vin "]),
    ],
    "traiteur": [
        ("bouchées à la reine", ["bouchee a la reine", "bouchees a la reine"]),
        ("baeckeoffe", ["baeckeoffe", "baekeoffe"]), ("choucroute", ["choucroute"]),
        ("pâté en croûte", ["pate en croute"]), ("foie gras", ["foie gras"]), ("couscous", ["couscous"]),
        ("paella", ["paella"]), ("lasagnes", ["lasagne"]), ("tajines", ["tajine"]),
        ("mezzés", ["mezze"]), ("houmous", ["houmous", "hummus"]), ("falafels", ["falafel"]),
        ("canapés", ["canape"]), ("verrines", ["verrine"]), ("buffets", ["buffet"]),
        ("plateaux repas", ["plateau"]), ("quiches", ["quiche"]), ("tourtes", ["tourte"]),
        ("terrines", ["terrine"]), ("salades", ["salade"]), ("plats du jour", ["plat du jour"]),
        ("plats à emporter", ["a emporter"]),
    ],
}


def _trouve(variante: str, texte: str) -> bool:
    """Début de mot ; une variante finie par une espace exige le mot entier (pluriel admis)."""
    if variante.endswith(" "):
        motif = r"(?<![a-z0-9])" + re.escape(variante.strip()) + r"[sx]?(?![a-z0-9])"
    else:
        motif = r"(?<![a-z0-9])" + re.escape(variante)
    return re.search(motif, texte) is not None


def extraire(avis: list[str], categorie: str, nombre: int = 2) -> list[str]:
    """Les `nombre` spécialités les plus citées (un avis compte une fois par terme)."""
    textes = [normaliser(a) for a in avis if a]
    if not textes:
        return []
    scores = []
    for rang, (forme, variantes) in enumerate(DICO.get(categorie, [])):
        n = sum(1 for t in textes if any(_trouve(v, t) for v in variantes))
        if n:
            scores.append((n, -rang, forme))
    scores.sort(reverse=True)
    return [forme for _, _, forme in scores[:nombre]]


def citee_dans(terme: str, avis: list[str]) -> bool:
    """Garde-fou anti-invention : le terme apparaît-il vraiment dans un avis ?"""
    t = normaliser(terme)
    if len(t) < 3:
        return False
    racine = t[:-1] if t.endswith("s") else t
    return any(racine in normaliser(a) for a in avis)
