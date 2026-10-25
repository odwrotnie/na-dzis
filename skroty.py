#!/usr/bin/env python3
"""Generator skrótu iOS "Na dziś" (arkusz udostępniania) dodającego przypomnienia.

Jeden skrót, trzy gałęzie; każda pyta o tytuł (z podpowiedzią do zatwierdzenia)
i dodaje przypomnienie do listy "Urgent" z alertem na bieżącą datę:
  link  - podpowiedź: tytuł strony (fallback: URL); URL w polu URL
  obraz - bez podpowiedzi; dołącza obrazy
  tekst - podpowiedź: udostępniony tekst

Najpierw link, dopiero potem obraz: Chrome na iOS udostępnia link razem ze
zrzutem strony, więc odwrotna kolejność gubiła URL.

  python3 skroty.py                         # Na dziś.shortcut - do importu (w repo)
  python3 skroty.py --test                  # dist/test/TEST Na dziś vN.shortcut - zamiast
                                            # przypomnienia zapisuje JSON (patrz testy.py)
  python3 skroty.py --test --przypomnienia  # wersja testowa z prawdziwymi przypomnieniami
                                            # i ich szczegółami w JSON-ie
"""
import argparse
import hashlib
import json
import plistlib
import subprocess
import uuid
from pathlib import Path

NAZWA = "Na dziś"
LISTA = "Urgent"
TYTUL_OBRAZU_TESTOWEGO = "TEST obraz"  # testy nie mają okna z pytaniem o tytuł
# raporty testów w iCloud Drive/Skróty, na Macu: ~/Library/Mobile Documents/
# iCloud~is~workflow~my~workflows/Documents (widać tam też uruchomienia z iPhone'a)
KATALOG_TESTOW = "na-dzis-testy"
KATALOG = Path(__file__).resolve().parent
DIST = KATALOG / "dist"
PLIK_WERSJI = KATALOG / "wersja-testowa.json"
OBJ = "\ufffc"  # znak-zaślepka, w którego miejsce Shortcuts wstawia zmienną

WEJSCIE = {"Type": "ExtensionInput"}
TERAZ = {"Type": "CurrentDate"}
SLAD = {"Type": "Variable", "VariableName": "Ślad"}
MA_WARTOSC = 100  # WFCondition
# adres WWW w tekście, bez interpunkcji zamykającej zdanie ("zobacz https://x.pl/.")
WZOR_ADRESU = r"https?://[^\s<>\"']*[^\s<>\"'.,;:!?)\]]"
WZOR_OBRAZU = r"(?m)^(png|jpe?g|heic|heif|gif|webp|tiff?|bmp)$"

# bez stron Safari i artykułów: wtedy Safari podaje sam URL, a nie treść strony,
# w której pierwszy znaleziony adres nie musi być adresem strony
KLASY_WEJSCIA = [
    "WFURLContentItem", "WFStringContentItem", "WFRichTextContentItem", "WFImageContentItem",
    "WFGenericFileContentItem", "WFPDFContentItem", "WFContactContentItem",
    "WFLocationContentItem", "WFDCMapsLinkContentItem", "WFAppStoreAppContentItem",
]


def zalacznik(zmienna):
    """Parametr, który przyjmuje samą zmienną (WFInput, WFImages)."""
    return {"Value": zmienna, "WFSerializationType": "WFTextTokenAttachment"}


def tekst(*czesci):
    """Parametr tekstowy: napisy przeplatane zmiennymi."""
    napis, zmienne = "", {}
    for czesc in czesci:
        if isinstance(czesc, str):
            napis += czesc
        else:
            pozycja = len(napis.encode("utf-16-le")) // 2  # zakresy liczone w UTF-16
            zmienne[f"{{{pozycja}, 1}}"] = czesc
            napis += OBJ
    return {"Value": {"string": napis, "attachmentsByRange": zmienne},
            "WFSerializationType": "WFTextTokenString"}


def wlasciwosc(zmienna, nazwa):
    """Zmienna z wybraną właściwością, np. URL przypomnienia."""
    return {**zmienna, "Aggrandizements": [
        {"Type": "WFPropertyVariableAggrandizement", "PropertyName": nazwa}]}


def jako_url(zmienna):
    """Zmienna wymuszona na typ URL. Tylko dla tekstu, który na pewno jest adresem:
    wymuszenie na tekście bez adresu albo obrazku przerywa skrót błędem."""
    return {**zmienna, "Aggrandizements": [
        {"Type": "WFCoercionVariableAggrandizement", "CoercionItemClass": "WFURLContentItem"}]}


class Skrot:
    def __init__(self, slad=False):
        """`slad` (testy): każdy wynik akcji trafia do śladu, który raport zapisuje."""
        self.akcje = []
        self.uuidy = 0
        self.slad = slad
        self.krok = 0
        if slad:
            self.czas = self._dopisz("format.date", "Sformatowana data",
                                     WFDateFormatStyle="Custom", WFDateFormat="yyyyMMdd-HHmmss",
                                     WFDate=tekst(TERAZ))
            self.loguj("wejście", WEJSCIE)

    def uuid(self):
        """Kolejny UUID, ale stały między budowaniami: ta sama treść, ten sam plik."""
        self.uuidy += 1
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"na-dzis/{self.uuidy}")).upper()

    def _dopisz(self, ident, wynik=None, **parametry):
        """Dodaje akcję bez śladu; z `wynik` zwraca zmienną wskazującą jej wynik."""
        if wynik:
            parametry["UUID"] = self.uuid()
        self.akcje.append({"WFWorkflowActionIdentifier": f"is.workflow.actions.{ident}",
                           "WFWorkflowActionParameters": parametry})
        if not wynik:
            return None
        return {"Type": "ActionOutput", "OutputUUID": parametry["UUID"], "OutputName": wynik}

    def akcja(self, ident, wynik=None, **parametry):
        """Jak `_dopisz`, a w testach wynik trafia też do śladu."""
        zmienna = self._dopisz(ident, wynik, **parametry)
        if zmienna:
            self.loguj(f"{ident} → {wynik}", zmienna)
        return zmienna

    def napis(self, *czesci):
        return self.akcja("gettext", "Tekst", WFTextActionText=tekst(*czesci))

    def loguj(self, etykieta, zmienna=None):
        """Dopisuje linię do śladu (zmienna w pamięci). Plik zapisuje dopiero raport:
        każdy zapis to pytanie Skrótów o zgodę, więc zapis po każdym kroku to kilkanaście
        kliknięć na przebieg. Gdy coś padnie po drodze, Skróty i tak podają, która akcja."""
        if not self.slad:
            return
        self.krok += 1
        linia = [f"\n{self.krok:02}. {etykieta}"] + ([": ", zmienna] if zmienna else [])
        calosc = self._dopisz("gettext", "Tekst", WFTextActionText=tekst(SLAD, *linia))
        self._dopisz("setvariable", WFVariableName=SLAD["VariableName"], WFInput=zalacznik(calosc))

    def jezeli_ma_wartosc(self, zmienna, tak, inaczej):
        """If/Otherwise; zwraca wynik bloku (wynik ostatniej akcji wykonanej gałęzi)."""
        grupa = self.uuid()
        self._dopisz("conditional", GroupingIdentifier=grupa, WFControlFlowMode=0,
                     WFCondition=MA_WARTOSC,
                     WFInput={"Type": "Variable", "Variable": zalacznik(zmienna)})
        self.loguj(f"jeżeli {zmienna['OutputName']} ma wartość: TAK")
        tak()
        self._dopisz("conditional", GroupingIdentifier=grupa, WFControlFlowMode=1)
        self.loguj(f"jeżeli {zmienna['OutputName']} ma wartość: NIE")
        inaczej()
        return self.akcja("conditional", "Jeżeli wynik", GroupingIdentifier=grupa,
                          WFControlFlowMode=2)

    def tekst_jezeli(self, zmienna, tak, inaczej):
        """Tekst `tak`, gdy `zmienna` ma wartość, inaczej `inaczej`. Wynikiem bloku jest
        wynik ostatniej akcji gałęzi, więc po tekście nic się nie dopisuje, nawet śladu."""
        return self.jezeli_ma_wartosc(
            zmienna,
            lambda: self._dopisz("gettext", "Tekst", WFTextActionText=tekst(tak)),
            lambda: self._dopisz("gettext", "Tekst", WFTextActionText=tekst(inaczej)))

    def plist(self):
        return {
            "WFWorkflowActions": self.akcje,
            "WFWorkflowClientVersion": "4711",
            "WFWorkflowMinimumClientVersion": 900,
            "WFWorkflowMinimumClientVersionString": "900",
            "WFWorkflowHasShortcutInputVariables": True,
            "WFWorkflowIcon": {"WFWorkflowIconGlyphNumber": 59511,
                               "WFWorkflowIconStartColor": 4282601983},
            "WFWorkflowImportQuestions": [],
            "WFWorkflowInputContentItemClasses": KLASY_WEJSCIA,
            "WFWorkflowOutputContentItemClasses": [],
            "WFWorkflowTypes": ["ActionExtension"],
            "WFWorkflowNoInputBehavior": {"Name": "WFWorkflowNoInputBehaviorGetClipboard",
                                          "Parameters": {}},
        }


def dodaj_przypomnienie(s, tytul, url=None, obrazy=None):
    parametry = {
        "WFCalendarItemTitle": tekst(tytul),
        "WFCalendarDescriptor": {"Title": LISTA, "IsAllCalendar": False},
        "WFAlertEnabled": "Alert",
        "WFAlertCondition": "At Time",
        "WFAlertCustomTime": tekst(TERAZ),
    }
    if url:
        parametry["WFURL"] = tekst(url)
    if obrazy:
        parametry["WFImages"] = zalacznik(obrazy)
    return s.akcja("addnewreminder", "Przypomnienie", **parametry)


def pobierz_tekst(s, zmienna):
    return s.akcja("detect.text", "Tekst", WFInput=zalacznik(zmienna))


def dopasuj(s, wzor, zmienna):
    """Dopasowania wyrażenia regularnego w tekście zmiennej (Match Text)."""
    return s.akcja("text.match", "Dopasowania", WFMatchTextPattern=wzor,
                   WFMatchTextCaseSensitive=False, text=tekst(zmienna))


def liczba(s, zmienna):
    return s.akcja("count", "Liczba", WFCountType="Items", Input=zalacznik(zmienna))


def raport(s, pola):
    """Tylko testy: pola i ślad jako JSON, jednym zapisem do KATALOG_TESTOW
    i jako wynik skrótu (dla `shortcuts run -o`)."""
    slownik = s.akcja("dictionary", "Słownik", WFItems={
        "Value": {"WFDictionaryFieldValueItems": [
            {"WFItemType": 0, "WFKey": tekst(klucz), "WFValue": tekst(wartosc)}
            for klucz, wartosc in {**pola, "slad": SLAD}.items() if wartosc is not None]},
        "WFSerializationType": "WFDictionaryFieldValue"})
    s.akcja("documentpicker.save", WFInput=zalacznik(slownik), WFAskWhereToSave=False,
            WFSaveFileOverwrite=True,
            WFFileDestinationPath=tekst(f"{KATALOG_TESTOW}/", s.czas, ".json"))
    s.akcja("output", WFOutput=tekst(slownik))


def diagnozuj(s):
    """Tylko testy: co Skróty widzą w wejściu (pola raportu)."""
    return {
        "wejscie": s.akcja("getitemtype", "Typ", WFInput=zalacznik(WEJSCIE)),
        "wejscie_rozszerzenia": wlasciwosc(WEJSCIE, "File Extension"),
    }


def na_dzis(test=False, przypomnienia=True):
    """`test`: zamiast pytać bierze podpowiedź, raportuje JSON-em i zapisuje ślad;
    `przypomnienia`: tworzy przypomnienie (w testach raport ma wtedy jego szczegóły)."""
    s = Skrot(slad=test)
    diagnostyka = diagnozuj(s) if test else {}

    def zapisz(metoda, tytul, url=None, obrazy=None):
        przyp = dodaj_przypomnienie(s, tytul, url, obrazy) if przypomnienia else None
        if not test:
            return
        if przyp:
            pola = dict(
                tytul=wlasciwosc(przyp, "Name"), url=wlasciwosc(przyp, "URL"),
                lista=wlasciwosc(przyp, "List"), alarm=wlasciwosc(przyp, "Has Alarms"),
                termin=wlasciwosc(przyp, "Due Date"),
                obrazy=liczba(s, wlasciwosc(przyp, "Images")))
        else:
            pola = dict(tytul=tytul, url=url, obrazy=liczba(s, obrazy) if obrazy else "0")
        raport(s, {"metoda": metoda, **diagnostyka, **pola})

    def zapytaj_o_tytul(podpowiedz=None):
        """Okno z tytułem do zatwierdzenia; testy (bez okna) biorą od razu podpowiedź."""
        if test:
            return s.napis(podpowiedz or TYTUL_OBRAZU_TESTOWEGO)
        domyslna = {"WFAskActionDefaultAnswer": tekst(podpowiedz)} if podpowiedz else {}
        return s.akcja("ask", "Podane dane wejściowe", WFAskActionPrompt="Tytuł przypomnienia",
                       WFInputType="Text", **domyslna)

    def link():
        # jeden adres: lista adresów wstawiona w pole URL daje pusty URL
        url = jako_url(s.akcja("getitemfromlist", "Element z listy",
                               WFItemSpecifier="First Item", WFInput=zalacznik(adresy)))
        nazwa = s.akcja("getitemname", "Nazwa", WFInput=zalacznik(url), GetWebPageTitle=True)
        # tytuł przychodzi surowy z HTML-a ("&amp;"): odczyt jako plik .html go dekoduje
        # ("Utwórz tekst sformatowany z HTML" zwraca pusto). Bez deklaracji kodowania
        # iOS czyta ten plik jako Windows-1252 ("szybkoÅ›ci" zamiast "szybkości")
        html_tytulu = s.napis('<meta charset="utf-8">', nazwa)
        plik_html = s.akcja("setitemname", "Plik HTML", WFInput=zalacznik(html_tytulu),
                            WFName=tekst("tytul.html"))
        tytul_strony = pobierz_tekst(s, plik_html)
        podpowiedz = s.tekst_jezeli(tytul_strony, tytul_strony, url)
        zapisz("link", zapytaj_o_tytul(podpowiedz), url=url)

    def bez_linku():
        obrazy = dopasuj(s, WZOR_OBRAZU, wlasciwosc(WEJSCIE, "File Extension"))
        s.jezeli_ma_wartosc(obrazy,
                            lambda: zapisz("obraz", zapytaj_o_tytul(), obrazy=WEJSCIE),
                            lambda: zapisz("tekst", zapytaj_o_tytul(tekst_wejscia)))

    # "Pobierz URL-e z wejścia" nic nie zwraca, a "Pobierz obrazy z wejścia" robi obrazek
    # nawet z tekstu - stąd adres z tekstu wejścia i obraz rozpoznawany po rozszerzeniu
    tekst_wejscia = pobierz_tekst(s, WEJSCIE)
    adresy = dopasuj(s, WZOR_ADRESU, tekst_wejscia)
    s.jezeli_ma_wartosc(adresy, link, bez_linku)
    return s.plist()


def wersja_testowa():
    """Ostatnio zbudowana wersja testowa: numer, sha1 treści i czy tworzy przypomnienia."""
    stan = {"wersja": 0, "sha1": "", "przypomnienia": False}
    if PLIK_WERSJI.exists():
        stan.update(json.loads(PLIK_WERSJI.read_text()))
    return stan


def nazwa_testowa(wersja):
    return f"TEST {NAZWA} v{wersja}"


def podbij_wersje_testowa(tresc, przypomnienia):
    """Nowy numer tylko przy zmianie treści: import czasem dodaje kopię ("... 1")
    zamiast zastąpić skrót, więc każda wersja ma własną nazwę."""
    stan, sha1 = wersja_testowa(), hashlib.sha1(tresc).hexdigest()
    if sha1 != stan["sha1"]:
        stan = {"wersja": stan["wersja"] + 1, "sha1": sha1, "przypomnienia": przypomnienia}
        PLIK_WERSJI.write_text(json.dumps(stan) + "\n")
    return nazwa_testowa(stan["wersja"])


def zbuduj(test, przypomnienia):
    tresc = plistlib.dumps(na_dzis(test, przypomnienia), fmt=plistlib.FMT_BINARY)
    # docelowy leży w repo: release na GitHubie zmienia nazwę pliku ("Na.dzis"),
    # a z niej Skróty biorą nazwę skrótu
    nazwa, cel = ((podbij_wersje_testowa(tresc, przypomnienia), DIST / "test") if test
                  else (NAZWA, KATALOG))
    roboczy = KATALOG / "build" / "roboczy.shortcut"  # sign wymaga rozszerzenia .shortcut
    roboczy.parent.mkdir(parents=True, exist_ok=True)
    cel.mkdir(parents=True, exist_ok=True)
    for stary in cel.glob("*.shortcut"):  # w katalogu tylko bieżąca wersja
        stary.unlink()
    roboczy.write_bytes(tresc)
    podpisany = cel / f"{nazwa}.shortcut"
    subprocess.run(["shortcuts", "sign", "-m", "anyone", "-i", roboczy, "-o", podpisany],
                   check=True, capture_output=True)
    print(podpisany.relative_to(KATALOG))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--test", action="store_true",
                        help="wersja testowa: wynik w JSON-ie zamiast przypomnienia")
    parser.add_argument("--przypomnienia", action="store_true",
                        help="z --test: twórz prawdziwe przypomnienia (tytuły z TEST)")
    argumenty = parser.parse_args()
    zbuduj(argumenty.test, argumenty.przypomnienia or not argumenty.test)
