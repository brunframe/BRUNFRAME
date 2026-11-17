"""Rend une page HTML 100 % ASCII sans changer son rendu : les caractères accentués
deviennent &#x..; (HTML), \\uXXXX (JavaScript) ou \\XXXX (CSS). Ainsi une pièce
jointe s'affiche correctement même si la messagerie se trompe d'encodage.

    python outils/html_ascii.py page.html [sortie.html]
"""
import re
import sys


def js(s):
    out = []
    for c in s:
        o = ord(c)
        if o < 128:
            out.append(c)
        elif o > 0xFFFF:
            o -= 0x10000
            out.append("\\u%04X\\u%04X" % (0xD800 + (o >> 10), 0xDC00 + (o & 0x3FF)))
        else:
            out.append("\\u%04X" % o)
    return "".join(out)


def css(s):
    return "".join(c if ord(c) < 128 else "\\%06X" % ord(c) for c in s)


def html(s):
    return "".join(c if ord(c) < 128 else "&#x%X;" % ord(c) for c in s)


def convertir(t):
    morceaux = re.split(r"(<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>)", t, flags=re.S | re.I)
    res = []
    for m in morceaux:
        if m.lower().startswith("<script"):
            res.append(js(m))
        elif m.lower().startswith("<style"):
            res.append(css(m))
        else:
            res.append(html(m))
    return "".join(res)


if __name__ == "__main__":
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else src
    t = open(src, encoding="utf-8").read()
    out = convertir(t)
    assert all(ord(c) < 128 for c in out)
    open(dst, "w", encoding="ascii").write(out)
    print(f"{dst} : ASCII pur")
