#!/usr/bin/env python3
"""Test baseline2.py against the 12 labeled episodes (May 4-5) and the official format.

python submission/test_baseline2.py --data data

1. Scores May 4-5 with the page-4 rules (time overlap >= 0.30, tractor overlap >= 0.50,
   macro-F1 over the five causes, onset credit). Also scores the original baseline.
2. Builds the May 6 submission and runs the official validator on it.
3. Moves every threshold 25% up and down and re-scores, to show results are not fragile.
Exits 1 if any required check fails.
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import baseline  # noqa: E402
import baseline2  # noqa: E402
from validate_submission import validate  # noqa: E402

CLASSES = ["SPACE_WEATHER", "JAMMING", "SPOOFING", "EQUIPMENT_FAULT", "MULTIPATH"]
DEV_START = pd.Timestamp("2026-05-04T00:00:00Z")
DEV_END = pd.Timestamp("2026-05-06T00:00:00Z")


def time_iou(a0, a1, b0, b1):
    inter = (min(a1, b1) - max(a0, b0)).total_seconds()
    union = (max(a1, b1) - min(a0, b0)).total_seconds()
    return max(inter, 0) / union


def onset_credit(minutes_off):
    if minutes_off <= 5:
        return 1.0
    return max(0.0, (60 - minutes_off) / 55)


def score(detections, labels):
    """Page-4 diagnostic: 25 x macro-F1 + 15 x mean onset credit (out of 40)."""
    dets = [dict(d, s=pd.Timestamp(d["start"]), e=pd.Timestamp(d["end"])) for d in detections]
    used, rows = set(), []
    for lab in labels:
        best = None
        for i, d in enumerate(dets):
            if i in used or d["class"] != lab["class"]:
                continue
            ti = time_iou(d["s"], d["e"], lab["s"], lab["e"])
            si = len(set(d["tractors"]) & set(lab["tractors"])) / len(set(d["tractors"]) | set(lab["tractors"]))
            if ti >= 0.30 and si >= 0.50 and (best is None or ti > best[1]):
                best = (i, ti)
        if best:
            used.add(best[0])
            d = dets[best[0]]
            off = abs((d["s"] - lab["s"]).total_seconds()) / 60
            rows.append(dict(id=lab["id"], cls=lab["class"], hit=True, onset=onset_credit(off),
                             off_min=round(off, 1), iou=round(best[1], 2), ours=d))
        else:
            rows.append(dict(id=lab["id"], cls=lab["class"], hit=False, onset=0.0,
                             off_min=None, iou=None, ours=None))
    reps = [l for l in labels if l["class"] == "MULTIPATH"]
    f1s, extras = {}, []
    for c in CLASSES:
        tp = sum(r["hit"] for r in rows if r["cls"] == c)
        fn = sum(not r["hit"] for r in rows if r["cls"] == c)
        fp_list = [d for i, d in enumerate(dets) if d["class"] == c and i not in used]
        if c == "MULTIPATH":   # short recurrent multipath is exempt unless it overlaps a
            # representative in time AND shares a tractor with it (same as the official scorer)
            fp_list = [d for d in fp_list if (d["e"] - d["s"]).total_seconds() > 180
                       or any(d["s"] < l["e"] and d["e"] > l["s"]
                              and set(d["tractors"]) & set(l["tractors"]) for l in reps)]
        extras += fp_list
        f1s[c] = 2 * tp / (2 * tp + len(fp_list) + fn) if tp + fn + len(fp_list) else 0.0
    macro = sum(f1s.values()) / len(CLASSES)
    onset = sum(r["onset"] for r in rows) / len(rows)
    return dict(rows=rows, f1=f1s, macro=macro, onset=onset, total=25 * macro + 15 * onset, extras=extras)


def run_baseline(data):
    baseline.EVAL_START, baseline.EVAL_END = DEV_START, DEV_END
    try:
        return baseline.detect(data)
    finally:
        baseline.EVAL_START = pd.Timestamp("2026-05-06T00:00:00Z")
        baseline.EVAL_END = pd.Timestamp("2026-05-07T00:00:00Z")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data")
    parser.add_argument("--skip-sweep", action="store_true", help="skip the threshold sweep")
    args = parser.parse_args()
    failures = []

    labels = json.load(open(Path(args.data) / "labels/train_episodes.json"))["episodes"]
    for l in labels:
        l["s"], l["e"] = pd.Timestamp(l["start"]), pd.Timestamp(l["end"])
    frames = baseline2.load(args.data)

    # ---- 1. development days ----
    dev = baseline2.detect(None, DEV_START, DEV_END, frames=frames)
    s = score(dev, labels)
    print("== 1. baseline2 on May 4-5 vs the 12 labels ==")
    print(f"{'id':7} {'class':16} {'result':6} {'start off':>9} {'time IoU':>8}  our detection")
    for r in s["rows"]:
        ours = (f"{r['ours']['start'][5:16]} to {r['ours']['end'][11:16]} {','.join(r['ours']['tractors'])}"
                if r["hit"] else "")
        off = f"{r['off_min']} min" if r["hit"] else "-"
        print(f"{r['id']:7} {r['cls']:16} {'HIT' if r['hit'] else 'MISS':6} {off:>9} "
              f"{str(r['iou'] or '-'):>8}  {ours}")
    for c in CLASSES:
        print(f"  F1 {c:16} {s['f1'][c]:.2f}")
    for d in s["extras"]:
        print(f"  counted false alarm: {d['class']} {d['start']} {','.join(d['tractors'])}")
    print(f"  macro-F1 {s['macro']:.3f}  onset {s['onset']:.3f}  diagnostic {s['total']:.1f} / 40")
    hits = sum(r["hit"] for r in s["rows"])
    if hits != len(labels):
        failures.append(f"only {hits} of {len(labels)} labels matched")
    big_extras = [d for d in s["extras"] if d["class"] != "MULTIPATH"]
    if big_extras:
        failures.append(f"{len(big_extras)} non-multipath false alarms on May 4-5")

    b = score(run_baseline(args.data), labels)
    print(f"\n   original baseline: {sum(r['hit'] for r in b['rows'])} of {len(labels)} matched, "
          f"{len(b['extras'])} false alarms, diagnostic {b['total']:.1f} / 40")

    # ---- 2. evaluation day, official format ----
    print("\n== 2. May 6 submission ==")
    may6 = baseline2.detect(None, frames=frames)
    sub = {"participant": {"github_handle": "Ayanleaideed"},
           "repository_url": "https://github.com/Ayanleaideed/bluestaq-ndsu-straight-rows-hackathon",
           "detections": may6}
    problems = validate(json.loads(json.dumps(sub)))
    print("  validator:", "OK" if not problems else problems[:5])
    failures += problems
    counts = pd.Series([d["class"] for d in may6]).value_counts().to_dict()
    print(f"  {len(may6)} detections (limit 500): {counts}")
    for d in may6:
        if d["class"] != "MULTIPATH":
            print(f"  {d['start'][11:16]}-{d['end'][11:16]} {d['class']:16} {','.join(d['tractors']):9} "
                  f"conf {d['confidence']}")
    text = json.dumps(sub)
    if "@" in text:
        failures.append("submission contains '@' (possible email address)")
    if any(len(d["evidence"]) < 2 for d in may6):
        failures.append("some detection has fewer than 2 evidence lines")
    if sum(c != "MULTIPATH" for c in counts) < 1 or counts.get("MULTIPATH", 0) > 495:
        failures.append("unexpected detection counts")

    # ---- 3. threshold sweep ----
    if not args.skip_sweep:
        print("\n== 3. each threshold moved 25% down and up (labels matched / non-multipath false alarms) ==")
        names = ["STORM_S4", "STORM_SIGNAL", "JAM_DROP_DB", "SPOOF_EXTRA_M", "SPOOF_SIGNAL_DB",
                 "ANTENNA_DB", "MULTIPATH_DB"]
        for name in names:
            orig = getattr(baseline2, name)
            cells = []
            for factor in (0.75, 1.25):
                setattr(baseline2, name, orig * factor)
                try:
                    r = score(baseline2.detect(None, DEV_START, DEV_END, frames=frames), labels)
                    fa = sum(d["class"] != "MULTIPATH" for d in r["extras"])
                    cells.append(f"x{factor}: {sum(x['hit'] for x in r['rows'])}/12, {fa} FA, {r['total']:.1f}")
                finally:
                    setattr(baseline2, name, orig)
            print(f"  {name:16} {orig:<7} " + " | ".join(cells))

    print("\nRESULT:", "PASS" if not failures else "FAIL")
    for f in failures:
        print("  -", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
