# Messung: Anschluss Linie 908 → Bahnhof am ZOB Bamberg

Misst werktags, ob man mit der 908 aus dem Babenberger Viertel am ZOB den Bus zum Bahnhof erreicht.

- **Zeitfenster:** Mo–Fr 6–10, 11:30–14 und 17–20 Uhr
- **Gemessen wird:** Verspätung der 908 am ZOB, geplanter und tatsächlicher Anschluss, verpasst ja/nein, Mehrzeit bis Bahnhof
- **Ergebnisse:** `data/messungen.csv`, wird nach jedem Zeitfenster automatisch gespeichert

## Einrichten (einmalig, ca. 5 Minuten)

1. Auf GitHub ein **neues öffentliches Repository** anlegen, z. B. `bus908-messung`.
2. Die Dateien `monitor.py`, `auswertung.py`, `requirements.txt`, `README.md` und `.gitignore` hochladen („Add file“ → „Upload files“).
3. Die Zeitplan-Datei extra anlegen, weil versteckte Ordner beim Hochladen oft fehlen: „Add file“ → „Create new file“, als Namen `.github/workflows/messung.yml` eintippen und den Inhalt der Datei `messung.yml` hineinkopieren.
4. Reiter **Actions** öffnen und die Workflows aktivieren, falls GitHub danach fragt.
5. Testlauf: **Actions** → „Messung 908-Anschluss“ → **Run workflow**, „Testlauf“ angehakt lassen. Nach etwa 2 Minuten sollte der Lauf grün sein.

Danach läuft die Messung von selbst.

## Auswertung

Nach etwa 4 Wochen: `data/messungen.csv` herunterladen und auswerten lassen, oder `python auswertung.py` ausführen.

Zeilen mit `echtzeit_908 = nein` werden nicht ausgewertet. Dort lagen keine Echtzeitdaten vor.

## Hinweise

- GitHub kann geplante Läufe um bis zu 15 Minuten verzögern. Deshalb startet jeder Lauf 20–50 Minuten vor dem Zeitfenster.
- Bei öffentlichen Repositories stoppt GitHub geplante Läufe nach 60 Tagen ohne Aktivität. Jede gespeicherte Messung zählt als Aktivität.
- Gemessen wird die Prognose des Echtzeit-Feeds kurz vor der Ankunft. Das ist nah an der tatsächlichen Ankunft, aber keine exakte Messung.

## Datenquelle

gtfs.de – GTFS für Deutschland, Daten bereitgestellt von DELFI e.V.,
Lizenz CC BY 4.0. Fahrplan: https://download.gtfs.de/germany/nv_free/latest.zip,
Echtzeit: https://realtime.gtfs.de/realtime-free.pb
