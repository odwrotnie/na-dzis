# Skrót iOS "Na dziś" (przypomnienia z arkusza udostępniania)

Opis, działanie, instalacja i testy: [README.md](README.md). Pułapki samych Skrótów
(URL-e, obrazy, typ URL, tytuł z HTML-a, klucz `text`): sekcja "Pułapki" w README.
Tu tylko to, czego tam nie ma.

## Źródło kluczy parametrów

Definicje akcji (klucze, wartości enumów) są w dyld shared cache:
`/System/Volumes/Preboot/Cryptexes/OS/System/Library/dyld/dyld_shared_cache_arm64e.05`
(szukaj `is.workflow.actions.<akcja>\0` i czytaj napisy za nim). Nie zgadywać.

## Dodatkowo sprawdzone (macOS 26 / Skróty 7.0)

- Lista przypomnień: `WFCalendarDescriptor` z samym `Title` wystarcza.
- `WFTags` nie działa ani jako tablica napisów, ani tokenów (odczyt "Tags" pusty).
- Wynik bloku Jeżeli = wynik ostatniej akcji gałęzi; po niej nic nie dokładać,
  nawet śladu. Stąd `Skrot.tekst_jezeli` dopisuje gałęzie przez `_dopisz`.

## Generator

- UUID-y akcji są deterministyczne: refaktor sprawdzaj sha1 z
  `plistlib.dumps(na_dzis(...), fmt=plistlib.FMT_BINARY)` przed i po (ma wyjść identycznie).
- `plistlib` w trybie binarnym deduplikuje obiekty po `id()`: wspólny słownik wstawiony
  w dwa miejsca zmienia bajty (nie treść). Przy DRY budować nowe słowniki.

## Środowisko

- `shortcuts sign` zapisuje plik z nazwą w NFD ("ś" rozłożone), Skróty biorą nazwę
  z pliku, a CLI szuka jej dosłownie (stąd normalizacja w `testy.py`).
- Import nieraz dodaje kopię ("… 1") zamiast zastąpić, stąd `TEST Na dziś vN`
  (`wersja-testowa.json`: numer, sha1, tryb z przypomnieniami).
- `shortcuts run -i plik.txt` podaje typ Tekst, nie plik ani URL.
- Ślady i raporty testów: `SLADY` w `skroty.py` (iCloud Drive/Skróty/na-dzis-testy);
  działa też dla uruchomień z iPhone'a. Odczyt z iCloud bywa wolny.
- Importu nie da się zrobić z CLI: `open plik.shortcut` i klik "Dodaj skrót".
- Podpisany plik ma w certyfikacie tylko anonimowy identyfikator Apple (bez Apple ID),
  można go publikować.
