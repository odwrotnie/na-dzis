#!/usr/bin/env python3
"""Testy end-to-end: uruchamia zainstalowany "TEST Na dziś vN" (ostatnio zbudowaną
wersję testową) poleceniem `shortcuts run` z różnymi wejściami i sprawdza JSON,
który skrót zwraca.

Wersja z `skroty.py --test` tylko raportuje, co by zapisała. Wersja z
`--test --przypomnienia` tworzy przypomnienia (tytuły z "TEST") i raportuje ich
szczegóły; wtedy testy sprawdzają też listę i alert (tryb czytają z wersja-testowa.json).
"""
import argparse
import functools
import html
import http.server
import json
import re
import struct
import subprocess
import sys
import textwrap
import threading
import unicodedata
import zlib

from skroty import KATALOG, LISTA, TYTUL_OBRAZU_TESTOWEGO, nazwa_testowa, wersja_testowa

DANE = KATALOG / "build" / "testy"
PORT = 8765
SERWER = f"http://127.0.0.1:{PORT}"
TYTUL_STRONY = "TEST strona - zażółć gęślą jaźń & co"

STRONY = {
    "strona.html": f'<!doctype html><html><head><meta charset="utf-8">'
                   f'<title>{html.escape(TYTUL_STRONY)}</title></head>'
                   f'<body><p>Strona testowa</p></body></html>',
    "bez-tytulu.html": '<!doctype html><html><head><meta charset="utf-8"></head>'
                       '<body><p>Bez tytułu</p></body></html>',
}


def png(sciezka):
    """Minimalny czerwony PNG 32x32 bez zależności."""
    rozmiar = 32
    wiersz = b"\x00" + b"\xff\x00\x00" * rozmiar

    def blok(typ, dane):
        return (struct.pack(">I", len(dane)) + typ + dane
                + struct.pack(">I", zlib.crc32(typ + dane) & 0xFFFFFFFF))
    sciezka.write_bytes(b"\x89PNG\r\n\x1a\n"
                        + blok(b"IHDR", struct.pack(">IIBBBBB", rozmiar, rozmiar, 8, 2, 0, 0, 0))
                        + blok(b"IDAT", zlib.compress(wiersz * rozmiar))
                        + blok(b"IEND", b""))
    return sciezka


def plik(nazwa, tresc):
    sciezka = DANE / nazwa
    sciezka.write_text(tresc, encoding="utf-8")
    return sciezka


def oczekuj(metoda, tytul, url="", obrazy="0"):
    return {"metoda": metoda, "tytul": tytul, "url": url, "obrazy": obrazy}


def przygotuj():
    """Serwer ze stronami testowymi i scenariusze: (nazwa, pliki wejścia, oczekiwane pola)."""
    DANE.mkdir(parents=True, exist_ok=True)
    for nazwa, tresc in STRONY.items():
        plik(nazwa, tresc)

    class Cichy(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *argumenty):
            pass

    serwer = http.server.ThreadingHTTPServer(
        ("127.0.0.1", PORT), functools.partial(Cichy, directory=str(DANE)))
    threading.Thread(target=serwer.serve_forever, daemon=True).start()
    obraz = png(DANE / "obraz.png")

    url = f"{SERWER}/strona.html"
    url_bez = f"{SERWER}/bez-tytulu.html"
    url_martwy = "http://127.0.0.1:9/nie-ma.html"
    return [
        ("tekst", [plik("tekst.txt", "TEST tekst zwykły")],
         oczekuj("tekst", "TEST tekst zwykły")),
        ("link", [plik("link.txt", url)],
         oczekuj("link", TYTUL_STRONY, url)),
        # strona bez <title>: "Pobierz nazwę" daje końcówkę adresu, nie pusty wynik
        ("link bez tytułu", [plik("link-bez.txt", url_bez)],
         oczekuj("link", "bez-tytulu", url_bez)),
        ("link martwy", [plik("link-martwy.txt", url_martwy)],
         oczekuj("link", url_martwy, url_martwy)),
        ("link w tekście", [plik("tekst-z-linkiem.txt", f"TEST zobacz to {url} koniecznie")],
         oczekuj("link", TYTUL_STRONY, url)),
        ("link na końcu zdania", [plik("tekst-z-kropka.txt", f"TEST zobacz ({url}).")],
         oczekuj("link", TYTUL_STRONY, url)),
        ("link + zrzut (Chrome)", [plik("chrome.txt", url), obraz],
         oczekuj("link", TYTUL_STRONY, url)),
        ("link + tytuł + zrzut (Chrome)",
         [plik("chrome2-url.txt", url), plik("chrome2.txt", "Tytuł z Chrome"), obraz],
         oczekuj("link", TYTUL_STRONY, url)),
        ("obraz", [obraz],
         oczekuj("obraz", TYTUL_OBRAZU_TESTOWEGO, obrazy="1")),
        ("link z internetu", [plik("example.txt", "https://example.com/")],
         oczekuj("link", "Example Domain", "https://example.com/")),
    ]


def identyfikator(nazwa):
    """UUID zainstalowanego skrótu. Po nazwie się nie da: Skróty trzymają ją w NFD
    ("s" + kreska), a dwa importy dają dwa skróty o tej samej nazwie, których CLI
    wtedy nie znajduje. Ta sama nazwa vN to ta sama treść, więc wystarczy pierwszy."""
    lista = subprocess.run(["shortcuts", "list", "--show-identifiers"],
                           capture_output=True, text=True, check=True).stdout
    for linia in lista.splitlines():
        dopasowanie = re.fullmatch(r"(.*) \(([0-9A-F-]{36})\)", linia)
        if dopasowanie and unicodedata.normalize("NFC", dopasowanie[1]) == nazwa:
            return dopasowanie[2]
    sys.exit(f"Nie ma skrótu „{nazwa}”: zaimportuj plik z dist/test/")


def uruchom(skrot, wejscia):
    wyjscie = DANE / "wynik.json"
    wyjscie.unlink(missing_ok=True)
    polecenie = ["shortcuts", "run", skrot, "-o", str(wyjscie)]
    for w in wejscia:
        polecenie += ["-i", str(w)]
    proces = subprocess.run(polecenie, capture_output=True, text=True, timeout=120)
    if proces.returncode or not wyjscie.is_file():
        return None, (proces.stderr or proces.stdout or f"kod {proces.returncode}").strip()
    return json.loads(wyjscie.read_text()), None


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("filtry", nargs="*", help="tylko scenariusze zawierające ten fragment nazwy")
    parser.add_argument("-v", action="store_true", help="ślad krok po kroku także dla udanych")
    argumenty = parser.parse_args()

    stan = wersja_testowa()
    nazwa = nazwa_testowa(stan["wersja"])
    skrot = identyfikator(nazwa)
    wspolne = {"lista": LISTA, "alarm": ("Tak", "Yes")} if stan["przypomnienia"] else {}
    scenariusze = [s for s in przygotuj()
                   if not argumenty.filtry or any(f in s[0] for f in argumenty.filtry)]
    print(f"{nazwa}{' (z przypomnieniami)' if stan['przypomnienia'] else ''}\n")
    bledy = 0
    for scenariusz, wejscia, oczekiwane in scenariusze:
        raport, blad = uruchom(skrot, wejscia)
        if blad:  # Skróty podają w błędzie, która akcja padła
            bledy += 1
            print(f"BŁĄD  {scenariusz}: {blad}")
            continue
        slad = raport.pop("slad", "").strip()
        rozne = {k: w for k, w in {**wspolne, **oczekiwane}.items()
                 if raport.get(k, "") not in (w if isinstance(w, tuple) else (w,))}
        bledy += bool(rozne)
        print(f"{'ŹLE ' if rozne else 'OK  '}  {scenariusz}")
        for klucz in {**raport, **rozne}:
            uwaga = f"   <- oczekiwano {rozne[klucz]!r}" if klucz in rozne else ""
            print(f"        {klucz}={raport.get(klucz, '')!r}{uwaga}")
        if rozne or argumenty.v:
            print("        ślad:")
            print(textwrap.indent(slad, " " * 10))
    print(f"\n{len(scenariusze) - bledy}/{len(scenariusze)} OK")
    return 1 if bledy else 0


if __name__ == "__main__":
    sys.exit(main())
