"""Auswertung von data/messungen.csv. Aufruf: python auswertung.py"""
import csv
import os
import statistics as S
from collections import defaultdict

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "messungen.csv")
rows = list(csv.DictReader(open(path, encoding="utf-8")))
mit = [r for r in rows if r["echtzeit_908"] == "ja"]
print(f"Messungen gesamt: {len(rows)}, davon mit Echtzeit der 908: {len(mit)}")
if not mit:
    raise SystemExit("Keine Messungen mit Echtzeit - Auswertung nicht moeglich.")


def block(name, rs):
    v = [float(r["verspaetung_908_min"]) for r in rs]
    verp = sum(r["anschluss_verpasst"] == "ja" for r in rs)
    mehr = [float(r["mehrzeit_min"]) for r in rs if r["mehrzeit_min"] not in ("", None)]
    print(f"\n{name}: {len(rs)} Ankuenfte am ZOB")
    print(f"  Verspaetung 908: Durchschnitt {S.mean(v):.1f} Min, Median {S.median(v):.1f} Min, max {max(v):.1f} Min")
    print(f"  mehr als 3 Min zu spaet: {sum(x > 3 for x in v) / len(v):.0%}")
    print(f"  Anschluss zum Bahnhof verpasst: {verp} von {len(rs)} ({verp / len(rs):.0%})")
    if mehr:
        print(f"  spaeter am Bahnhof als geplant: Durchschnitt {S.mean(mehr):.1f} Min, max {max(mehr):.1f} Min")


block("Alle Zeitfenster", mit)
by = defaultdict(list)
for r in mit:
    by[r["fenster"]].append(r)
for k in ("morgens", "mittags", "abends"):
    if by[k]:
        block(k.capitalize(), by[k])
