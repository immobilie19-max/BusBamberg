"""
Misst, ob der Anschluss Linie 908 -> Bahnhof am ZOB Bamberg klappt.

Ablauf pro Lauf (ein Zeitfenster):
1. Fahrplan (gtfs.de, Nahverkehr) laden und auf ZOB/Bahnhof/Linie 908 filtern.
2. Zu jeder Ankunft der 908 am ZOB im Zeitfenster den Echtzeit-Feed
   (GTFS-Realtime, gtfs.de) mehrfach abfragen.
3. Ergebnis je Ankunft in data/messungen.csv schreiben:
   Verspaetung 908, geplanter und tatsaechlicher Anschluss, verpasst ja/nein,
   Mehrzeit bis Bahnhof.

Daten: gtfs.de - GTFS fuer Deutschland, Daten bereitgestellt von DELFI e.V.
Lizenz: CC BY 4.0.
"""
import argparse
import csv
import datetime as dt
import io
import os
import sys
import time
import urllib.request
import zipfile
from zoneinfo import ZoneInfo

from google.transit import gtfs_realtime_pb2

TZ = ZoneInfo("Europe/Berlin")
STATIC_URL = "https://download.gtfs.de/germany/nv_free/latest.zip"
RT_URL = "https://realtime.gtfs.de/realtime-free.pb"
AGENCY_NAME = "Stadtverkehr Bamberg"
LINIE = os.environ.get("LINIE", "908")
UMSTIEG_MIN = 2.0          # Fussweg zwischen den Steigen am ZOB

FENSTER = {  # lokale Zeit Mo-Fr
    "morgens": ("06:00", "10:00"),
    "mittags": ("11:30", "14:00"),
    "abends": ("17:00", "20:00"),
}

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CACHE_ZIP = os.environ.get("GTFS_ZIP", "")


def log(*a):
    print(dt.datetime.now(TZ).strftime("%H:%M:%S"), *a, flush=True)


def hms(s):
    h, m, x = s.split(":")
    return int(h) * 3600 + int(m) * 60 + int(x)


def fmt(sec):
    sec = int(round(sec))
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}"


import math

ZOB = (49.8933, 10.8920)
BHF = (49.9008, 10.8990)
URBAN = (49.87604, 10.87705)
KIND = {}  # stop_id -> "zob" | "bhf" | "start"


def dist(a, b):
    dy = (a[0] - b[0]) * 111320
    dx = (a[1] - b[1]) * 111320 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def is_zob(sid):
    return KIND.get(sid) == "zob"


def is_bhf(sid):
    return KIND.get(sid) == "bhf"


# ---------------------------------------------------------------- Fahrplan
def load_static(today):
    if CACHE_ZIP and os.path.exists(CACHE_ZIP):
        zf = zipfile.ZipFile(CACHE_ZIP)
    else:
        log("lade Fahrplan", STATIC_URL)
        path = os.path.join(DATA_DIR, "_gtfs.zip")
        urllib.request.urlretrieve(STATIC_URL, path)
        zf = zipfile.ZipFile(path)

    def rows(name):
        with zf.open(name) as f:
            yield from csv.DictReader(io.TextIOWrapper(f, "utf-8-sig"))

    agencies = {r["agency_id"] for r in rows("agency.txt") if r["agency_name"].strip() == AGENCY_NAME}
    routes = {}
    for r in rows("routes.txt"):
        routes[r["route_id"]] = (r["route_short_name"], r["agency_id"])
    ds = today.strftime("%Y%m%d")
    wd = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][today.weekday()]
    active = set()
    for r in rows("calendar.txt"):
        if r["start_date"] <= ds <= r["end_date"] and r[wd] == "1":
            active.add(r["service_id"])
    for r in rows("calendar_dates.txt"):
        if r["date"] == ds:
            (active.add if r["exception_type"] == "1" else active.discard)(r["service_id"])

    stops = {}
    for r in rows("stops.txt"):
        try:
            pos = (float(r["stop_lat"]), float(r["stop_lon"]))
        except ValueError:
            continue
        if abs(pos[0] - 49.89) > 0.03:
            continue
        n = r["stop_name"]
        if dist(pos, ZOB) <= 130 and "Gericht" not in n:
            KIND[r["stop_id"]] = "zob"
        elif dist(pos, BHF) <= 250:
            KIND[r["stop_id"]] = "bhf"
        elif dist(pos, URBAN) <= 60:
            KIND[r["stop_id"]] = "start"
        else:
            continue
        stops[r["stop_id"]] = n

    trips = {}
    linie_trips = set()
    for r in rows("trips.txt"):
        if r["service_id"] not in active:
            continue
        line, ag = routes.get(r["route_id"], ("?", ""))
        trips[r["trip_id"]] = line
        if line == LINIE and ag in agencies:
            linie_trips.add(r["trip_id"])
    log("aktive Fahrten heute:", len(trips), "| Linie", LINIE, ":", len(linie_trips))

    # stop_times streamen (sehr gross): nur relevante Zeilen behalten
    st = {}
    with zf.open("stop_times.txt") as f:
        it = io.TextIOWrapper(f, "utf-8-sig")
        header = next(it).strip().split(",")
        ix = {k: i for i, k in enumerate(header)}
        for line in it:
            p = line.rstrip("\n").split(",")
            tid = p[ix["trip_id"]]
            if tid not in trips:
                continue
            sid = p[ix["stop_id"]]
            if sid in stops:
                arr = p[ix["arrival_time"]] or p[ix["departure_time"]]
                dep = p[ix["departure_time"]] or arr
                st.setdefault(tid, []).append((int(p[ix["stop_sequence"]]), hms(arr), hms(dep), sid))
    for v in st.values():
        v.sort()

    ankuenfte = []   # 908 aus St. Urban -> ZOB
    anschluesse = []  # ZOB -> Bahnhof (alle Linien ausser 908)
    for tid, lst in st.items():
        kinds = [KIND[x[3]] for x in lst]
        if tid in linie_trips:
            if "start" in kinds:
                i = kinds.index("start")
                z = [x for x in lst[i + 1:] if is_zob(x[3])]
                if z:
                    ankuenfte.append({"trip": tid, "seq": z[0][0], "stop": z[0][3], "plan": z[0][1]})
            continue
        for i, x in enumerate(lst):
            if is_zob(x[3]):
                b = [y for y in lst[i + 1:] if is_bhf(y[3])]
                if b:
                    anschluesse.append({"trip": tid, "linie": trips[tid],
                                        "zob_seq": x[0], "zob_stop": x[3], "ab": x[2],
                                        "bhf_seq": b[0][0], "bhf_stop": b[0][3], "an": b[0][1]})
                break
    ankuenfte.sort(key=lambda a: a["plan"])
    anschluesse.sort(key=lambda a: a["ab"])
    log("908-Ankuenfte ZOB:", len(ankuenfte), "| Abfahrten ZOB->Bahnhof:", len(anschluesse))
    return ankuenfte, anschluesse


# ---------------------------------------------------------------- Echtzeit
def poll():
    for versuch in range(3):
        try:
            with urllib.request.urlopen(RT_URL, timeout=60) as r:
                data = r.read()
            fm = gtfs_realtime_pb2.FeedMessage()
            fm.ParseFromString(data)
            return fm
        except Exception as e:  # Netzfehler: kurz warten, erneut
            log("Abruf fehlgeschlagen:", e)
            time.sleep(10)
    return None


def delay_at(tu, seq, stop_id, plan_sec, day0):
    """Verspaetung in Sekunden an einem Halt, None wenn keine Echtzeit."""
    best = None
    for u in tu.stop_time_update:
        same = (u.stop_sequence == seq and u.HasField("stop_sequence")) or u.stop_id == stop_id
        before = u.HasField("stop_sequence") and u.stop_sequence <= seq
        if not (same or before):
            continue
        ev = u.arrival if u.HasField("arrival") else u.departure
        if ev.HasField("delay"):
            d = ev.delay
        elif ev.HasField("time") and same:
            d = ev.time - (day0 + plan_sec)
        else:
            continue
        if same:
            return d
        best = d  # letzte bekannte Verspaetung davor (wird weitergetragen)
    if best is None and tu.HasField("delay"):
        best = tu.delay
    return best


# ---------------------------------------------------------------- Messung
def run_window(name, today, ankuenfte, anschluesse, dry=False):
    a_von, a_bis = FENSTER[name]
    t0, t1 = hms(a_von + ":00"), hms(a_bis + ":00")
    mine = [a for a in ankuenfte if t0 <= a["plan"] < t1]
    if not mine:
        log("keine 908-Ankunft im Fenster", name)
        return []
    day0 = int(dt.datetime(today.year, today.month, today.day, tzinfo=TZ).timestamp())
    # Abfragezeitpunkte: 6 und 1 Min vor, 4 und 10 Min nach geplanter Ankunft
    polls = sorted({a["plan"] + o for a in mine for o in (-360, -60, 240, 600)})
    beob = {}  # (trip, seq) -> (delay, abrufzeit)
    rel = {a["trip"]: [(a["seq"], a["stop"], a["plan"])] for a in mine}
    for c in anschluesse:
        rel.setdefault(c["trip"], []).extend([(c["zob_seq"], c["zob_stop"], c["ab"]),
                                               (c["bhf_seq"], c["bhf_stop"], c["an"])])
    for p in polls:
        now = time.time() - day0
        if not dry and p > now:
            time.sleep(p - now)
        fm = poll()
        if fm is None:
            continue
        stamp = time.time() - day0
        n = 0
        for e in fm.entity:
            if not e.HasField("trip_update"):
                continue
            tid = e.trip_update.trip.trip_id
            if tid not in rel:
                continue
            for seq, sid, plan in rel[tid]:
                d = delay_at(e.trip_update, seq, sid, plan, day0)
                if d is not None:
                    beob[(tid, seq)] = (d, stamp)
                    n += 1
        log(f"Abruf {fmt(stamp)}: {n} Werte")
        if dry:
            break

    out = []
    for a in mine:
        d908 = beob.get((a["trip"], a["seq"]), (None, None))[0]
        ist = a["plan"] + (d908 or 0)
        kand = [c for c in anschluesse if c["ab"] >= a["plan"] + UMSTIEG_MIN * 60][:10]
        geplant = min(kand, key=lambda c: c["an"]) if kand else None  # schnellste geplante Verbindung

        def ist_ab(c):
            return c["ab"] + (beob.get((c["trip"], c["zob_seq"]), (0, 0))[0] or 0)

        def ist_an(c):
            return c["an"] + (beob.get((c["trip"], c["bhf_seq"]), (0, 0))[0] or 0)

        moegl = [c for c in anschluesse if ist_ab(c) >= ist + UMSTIEG_MIN * 60][:10]
        tats = min(moegl, key=ist_an) if moegl else None
        if geplant is None:
            continue
        verpasst = ist_ab(geplant) < ist + UMSTIEG_MIN * 60
        out.append({
            "datum": today.isoformat(), "fenster": name,
            "ankunft_plan": fmt(a["plan"]),
            "verspaetung_908_min": "" if d908 is None else round(d908 / 60, 1),
            "echtzeit_908": "ja" if d908 is not None else "nein",
            "anschluss_plan": f"{geplant['linie']} {fmt(geplant['ab'])}",
            "bahnhof_plan": fmt(geplant["an"]),
            "anschluss_verpasst": "ja" if verpasst else "nein",
            "anschluss_ist": f"{tats['linie']} {fmt(ist_ab(tats))}" if tats else "",
            "bahnhof_ist": fmt(ist_an(tats)) if tats else "",
            "mehrzeit_min": round((ist_an(tats) - geplant["an"]) / 60, 1) if tats else "",
        })
    return out


def write(rows):
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, "messungen.csv")
    neu = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        if neu:
            w.writeheader()
        w.writerows(rows)
    log("geschrieben:", len(rows), "Zeilen ->", path)


def aktuelles_fenster(now):
    m = now.hour * 60 + now.minute
    for name, (a, b) in FENSTER.items():
        ah, am = map(int, a.split(":"))
        bh, bm = map(int, b.split(":"))
        if ah * 60 + am - 45 <= m < bh * 60 + bm:
            return name
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fenster", choices=list(FENSTER), help="sonst automatisch nach Uhrzeit")
    ap.add_argument("--test", action="store_true", help="nur ein Abruf, nichts speichern")
    args = ap.parse_args()
    now = dt.datetime.now(TZ)
    if now.weekday() >= 5 and not args.test:
        log("Wochenende - keine Messung")
        return
    name = args.fenster or aktuelles_fenster(now) or ("abends" if args.test else None)
    if not name:
        log("kein Zeitfenster aktiv")
        return
    ankuenfte, anschluesse = load_static(now.date())
    rows = run_window(name, now.date(), ankuenfte, anschluesse, dry=args.test)
    for r in rows:
        print(r)
    if rows and not args.test:
        write(rows)


if __name__ == "__main__":
    main()
