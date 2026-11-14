#!/usr/bin/env python3
"""Straight Rows detector, version 2.

Idea: a tractor has a problem when it looks different from what it should look like
right now. "Should" comes from the other two tractors and the storm sensor (S4).
Five separate checks, so two causes can be reported at the same time.

python submission/baseline2.py --data data --output submission.json \
    --github-handle YOUR_GITHUB_USERNAME \
    --repo-url https://github.com/YOUR_GITHUB_USERNAME/YOUR_SOLUTION_REPO

Submissions are public: never add your email address or student ID.
"""
import argparse
import json
from pathlib import Path

import pandas as pd

ACTION = {
    "SPACE_WEATHER": "HALT_OR_DEGRADED_MODE",
    "JAMMING": "HALT_AND_REPORT",
    "SPOOFING": "HALT_CROSSCHECK_AND_REPORT",
    "EQUIPMENT_FAULT": "SERVICE_MACHINE_OTHERS_CONTINUE",
    "MULTIPATH": "CONTINUE_FALSE_ALARM",
}
EVAL_START = pd.Timestamp("2026-05-06T00:00:00Z")
EVAL_END = pd.Timestamp("2026-05-07T00:00:00Z")
TRACTORS = ["T1", "T2", "T3"]
ONE_MIN = pd.Timedelta(minutes=1)
ONE_SEC = pd.Timedelta(seconds=1)

# thresholds, chosen by looking at the labeled days (May 4-5)
STORM_S4 = 0.2          # S4 at or above this = storm conditions (calm is about 0.06)
STORM_SIGNAL = 40       # fleet signal below this during high S4 = storm is hitting the farm
JAM_DROP_DB = 4         # signal this far below normal = jamming
SPOOF_EXTRA_M = 1.0     # drift this much more than the other tractors = spoofing
SPOOF_EDGE_M = 0.15     # walk the spoof start back to where drift first passed this
SPOOF_SIGNAL_DB = 2     # spoofed tractor's signal must be within this of the others
ANTENNA_DB = 8          # weakest satellite this far below the fleet's = antenna fault
LINK_UP = 0.98          # correction link up less than this share of a minute = link fault
NORTH_STRIP_DEG = 0.00035   # north end of the field, about 40 m
MULTIPATH_DB = 4        # weakest satellite drop at the north end = multipath


def load(data):
    data = Path(data)
    tele = pd.read_csv(data / "farm/tractor_telemetry.csv.gz", parse_dates=["ts"])
    s4 = pd.DataFrame(json.load(open(data / "sda/scintillation_series.json"))["series"])
    s4["ts"] = pd.to_datetime(s4.ts, utc=True)
    kp = pd.DataFrame(json.load(open(data / "sda/sgi_indices.json"))["kp"])
    kp["ts"] = pd.to_datetime(kp.ts, utc=True)
    rfi = pd.DataFrame(json.load(open(data / "sda/rfi_reports.json"))["reports"])
    rfi["ts"] = pd.to_datetime(rfi.ts, utc=True, format="ISO8601")
    return tele, s4, kp, rfi


def to_episodes(flag, max_gap, min_length):
    """Join True minutes into (start, end) episodes; bridge short gaps, drop short episodes."""
    episodes = []
    for minute in flag.index[flag]:
        if episodes and minute - episodes[-1][1] <= max_gap * ONE_MIN:
            episodes[-1][1] = minute + ONE_MIN
        else:
            episodes.append([minute, minute + ONE_MIN])
    return [(a, b) for a, b in episodes if b - a >= min_length * ONE_MIN]


def find_all(tele, s4):
    """Run the five checks over all the data. Returns raw detections with measured facts."""
    tele = tele.copy()
    tele["xte"] = tele.cross_track_error_m.abs()      # drift left or right both count
    tele["link"] = tele.base_link_ok.astype(float)
    tele["fixed"] = tele.fix_state.eq("RTK_FIXED").astype(float)

    def per_minute(column, how):
        return tele.pivot_table(index=tele.ts.dt.floor("1min"), columns="tractor_id",
                                values=column, aggfunc=how)

    signal = per_minute("mean_cn0_dbhz", "mean")
    weakest = per_minute("min_cn0_dbhz", "min")
    drift = per_minute("xte", "mean")
    link = per_minute("link", "mean")
    sats = per_minute("num_sats", "mean")
    fixed = per_minute("fixed", "mean")
    working = per_minute("speed_mps", "mean") > 1
    minutes = signal.index
    s4_now = s4.set_index("ts").s4.reindex(minutes, method="ffill")
    found = []

    def span(a, b):
        return (minutes >= a) & (minutes < b)

    # 1. Space weather: all three working tractors weak together while S4 is high
    fleet_signal = signal.median(axis=1)
    storm_minute = working.all(axis=1) & (s4_now >= STORM_S4) & (fleet_signal < STORM_SIGNAL)
    storms = to_episodes(storm_minute, max_gap=5, min_length=30)
    calm_level = signal[working & (s4_now < STORM_S4).values[:, None]].stack().median()
    for a, b in storms:
        m = span(a, b)
        found.append(dict(start=a, end=b, cls="SPACE_WEATHER", tractors=TRACTORS, facts=dict(
            signal=fleet_signal[m].median(), calm=calm_level,
            spread=signal[m].median().max() - signal[m].median().min(),
            sats=sats[m].mean().mean(), fixed=fixed[m].mean().mean(),
            s4_mean=s4_now[m].mean(), s4_max=s4_now[m].max())))

    # 2. Jamming: signal at least JAM_DROP_DB below normal (calm level, or the storm's own level)
    normal = pd.Series(calm_level, index=minutes)
    for a, b in storms:
        normal[span(a, b)] = fleet_signal[span(a, b)].median()
    drop = -signal.sub(normal, axis=0)
    jammed = working & (drop >= JAM_DROP_DB)
    jam_minute = pd.Series(False, index=minutes)
    for a, b in to_episodes(jammed.any(axis=1), max_gap=3, min_length=5):
        m = span(a, b)
        hit = [t for t in TRACTORS if drop.loc[m, t].mean() >= JAM_DROP_DB]
        if hit:
            jam_minute[m] = True
            found.append(dict(start=a, end=b, cls="JAMMING", tractors=hit, facts=dict(
                drop=drop[m].mean().round(1).to_dict(), normal=normal[m].median(),
                sats=sats[m].mean().round(1).to_dict(), s4_max=s4_now[m].max(),
                in_storm=bool((normal[m] != calm_level).any()))))

    # 3. Spoofing: one tractor drifts much more than the others while its signal looks like theirs
    extra_drift = drift.sub(drift.median(axis=1), axis=0)
    signal_like_peers = signal.sub(fleet_signal, axis=0).abs() < SPOOF_SIGNAL_DB
    for t in TRACTORS:
        ok = working[t] & signal_like_peers[t] & ~jam_minute
        for a, b in to_episodes(ok & (extra_drift[t] > SPOOF_EXTRA_M), max_gap=2, min_length=5):
            while ok.get(a - ONE_MIN, False) and extra_drift[t][a - ONE_MIN] > SPOOF_EDGE_M:
                a -= ONE_MIN
            while ok.get(b, False) and extra_drift[t][b] > SPOOF_EDGE_M:
                b += ONE_MIN
            m = span(a, b)
            others = [o for o in TRACTORS if o != t]
            found.append(dict(start=a, end=b, cls="SPOOFING", tractors=[t], facts=dict(
                max_drift=drift.loc[m, t].max(), others_drift=drift.loc[m, others].max().max(),
                signal_gap=(signal.loc[m, t] - fleet_signal[m]).abs().mean(),
                sats=sats.loc[m, t].mean(), fixed=fixed.loc[m, t].mean(),
                in_storm=bool((normal[m] != calm_level).any()))))

    # 4. Equipment fault: only one tractor is bad (antenna or correction link), the others are fine
    weakest_vs_fleet = weakest.sub(weakest.median(axis=1), axis=0)
    for t in TRACTORS:
        others_link_up = link.drop(columns=t).min(axis=1) >= LINK_UP
        antenna = working[t] & ~jam_minute & (weakest_vs_fleet[t] <= -ANTENNA_DB)
        bad_link = working[t] & ~jam_minute & (link[t] < LINK_UP) & others_link_up
        for a, b in to_episodes(antenna | bad_link, max_gap=5, min_length=10):
            m = span(a, b)
            kind = "antenna" if antenna[m].sum() >= bad_link[m].sum() else "link"
            others = [o for o in TRACTORS if o != t]
            found.append(dict(start=a, end=b, cls="EQUIPMENT_FAULT", tractors=[t], facts=dict(
                kind=kind, weakest=weakest.loc[m, t].median(),
                others_weakest=weakest.loc[m, others].median().median(),
                bad_minutes=int(antenna[m].sum() if kind == "antenna" else bad_link[m].sum()),
                link=link.loc[m, t].mean(), fixed=fixed.loc[m, t].mean(),
                signal=signal.loc[m, t].mean(), others_signal=signal.loc[m, others].mean().mean())))

    # 5. Multipath: short weakest-satellite dip on each pass through the north end of the field
    north_strip = tele.lat.max() - NORTH_STRIP_DEG
    for t in TRACTORS:
        one = tele[tele.tractor_id == t].set_index("ts")
        in_strip = (one.lat >= north_strip) & (one.speed_mps > 1)
        pass_id = (in_strip != in_strip.shift()).cumsum()
        for _, visit in one[in_strip].groupby(pass_id[in_strip]):
            a, b = visit.index[0], visit.index[-1] + ONE_SEC
            before = one.min_cn0_dbhz[a - ONE_MIN: a - ONE_SEC].median()
            dip = before - visit.min_cn0_dbhz.median()
            if dip >= MULTIPATH_DB:
                found.append(dict(start=a, end=b, cls="MULTIPATH", tractors=[t], facts=dict(
                    dip=dip, before=before, mean_change=visit.mean_cn0_dbhz.median()
                    - one.mean_cn0_dbhz[a - ONE_MIN: a - ONE_SEC].median(),
                    lat=visit.lat.max())))
    return found


def iso(ts):
    return ts.isoformat()


def explain(d, kp, rfi, overlaps):
    """Measured evidence strings and a heuristic confidence (not a calibrated probability)."""
    f, a, b, trs = d["facts"], d["start"], d["end"], ",".join(d["tractors"])
    when = f"{iso(a)} to {iso(b)}"
    kp_max = kp[(kp.ts > a - pd.Timedelta(hours=3)) & (kp.ts < b)].kp.max()
    if d["cls"] == "SPACE_WEATHER":
        ev = [f"{when}: all three working tractors degraded together; median mean C/N0 "
              f"{f['signal']:.1f} dB-Hz vs calm {f['calm']:.1f}, spread between tractors only "
              f"{f['spread']:.1f} dB.",
              f"Satellites in use about {f['sats']:.1f} (normal 12); RTK_FIXED only "
              f"{f['fixed']:.0%} of the time.",
              f"SDA: regional S4 {f['s4_mean']:.2f} average, {f['s4_max']:.2f} peak "
              f"(calm about 0.06); Kp up to {kp_max:.1f}.",
              "Same drop on every machine plus high S4 points to the ionosphere, not a local source."]
        conf = 0.9 if f["spread"] < 1.5 else 0.75
    elif d["cls"] == "JAMMING":
        drops = ", ".join(f"{t} {v:.1f} dB" for t, v in f["drop"].items())
        sats = ", ".join(f"{t} {v:.1f}" for t, v in f["sats"].items())
        ev = [f"{when}: sharp loss of signal on {trs}; drop below expected level "
              f"({f['normal']:.1f} dB-Hz): {drops}.",
              f"Satellites in use: {sats}. Different drop per machine fits distance from a local "
              "transmitter, not a regional cause."]
        if f["in_storm"]:
            ev.append(f"Occurs inside a storm (S4 {f['s4_max']:.2f}); the drop is measured "
                      "against the storm's own level, so it is extra loss on top of the storm.")
        else:
            ev.append(f"S4 calm ({f['s4_max']:.2f}), so space weather does not explain it.")
        left_out = [t for t in TRACTORS if t not in d["tractors"]]
        if left_out:
            ev.append(f"{','.join(left_out)} dropped less than {JAM_DROP_DB} dB on average and is "
                      "not listed.")
        near = rfi[(rfi.ts >= a) & (rfi.ts <= b + pd.Timedelta(minutes=30))]
        for r in near.itertuples():
            ev.append(f"SDA: {r.id} at {iso(r.ts)} (confidence {r.confidence}) reports possible "
                      f"L1 interference near {r.centerLat:.3f},{r.centerLon:.3f}.")
        if near.empty:
            ev.append("No interference report matches; reports are incomplete, so this is "
                      "attributed from telemetry alone.")
        conf = 0.85 if not near.empty else 0.7
    elif d["cls"] == "SPOOFING":
        ev = [f"{when}: {trs} drifted up to {f['max_drift']:.2f} m off the line while the other "
              f"tractors stayed under {f['others_drift']:.2f} m.",
              f"Its GNSS looks healthy: C/N0 within {f['signal_gap']:.1f} dB of the fleet, "
              f"{f['sats']:.1f} satellites, RTK_FIXED {f['fixed']:.0%} of the time.",
              "Healthy signal with a growing position error on one machine fits a false signal, "
              "not jamming or a storm.",
              "Cross-check: the guidance monitor is independent of the GNSS fix; confirm with "
              "inertial or visual position before resuming."]
        if f["in_storm"]:
            ev.append("Occurs inside a storm; drift is measured relative to the other tractors, "
                      "so shared storm drift is removed.")
        conf = 0.8
    elif d["cls"] == "EQUIPMENT_FAULT":
        if f["kind"] == "antenna":
            ev = [f"{when}: {trs} weakest-satellite C/N0 median {f['weakest']:.1f} dB-Hz vs "
                  f"{f['others_weakest']:.1f} on the other tractors ({f['bad_minutes']} bad minutes).",
                  f"Mean C/N0 barely changes ({f['signal']:.1f} vs {f['others_signal']:.1f}), so "
                  "one weak channel on one machine: antenna or cable.",
                  "Other tractors normal at the same time and place, so not regional."]
        else:
            ev = [f"{when}: {trs} RTK correction link up only {f['link']:.0%} of the time; "
                  "the other tractors' links stay up.",
                  f"RTK_FIXED {f['fixed']:.0%} of the time and follows the link; signal normal "
                  f"({f['signal']:.1f} dB-Hz), so the receiver hears satellites fine.",
                  "Fault is in this machine's correction radio or modem."]
        conf = 0.8
    else:  # MULTIPATH
        ev = [f"{when}: {trs} weakest-satellite C/N0 fell {f['dip']:.1f} dB (from {f['before']:.1f}) "
              f"for {(b - a).total_seconds():.0f} s at the north end of the field (lat {f['lat']:.5f}).",
              f"Mean C/N0 changed {f['mean_change']:+.1f} dB: one reflected satellite, not loss of all.",
              "Recurs on every pass at the same place; guidance unaffected, continue."]
        conf = 0.6
    for o in overlaps:
        ev.append(f"Overlaps {o['cls']} on {','.join(o['tractors'])} ({iso(o['start'])} to "
                  f"{iso(o['end'])}); reported as a separate cause within the same operational event.")
    return ev, conf


def detect(data, start=EVAL_START, end=EVAL_END, frames=None):
    tele, s4, kp, rfi = frames if frames is not None else load(data)
    out = []
    for d in find_all(tele, s4):
        if d["end"] <= start or d["start"] >= end:
            continue
        out.append(dict(d, start=max(d["start"], start), end=min(d["end"], end)))
    out.sort(key=lambda d: (d["start"], d["cls"]))
    big = [d for d in out if d["cls"] != "MULTIPATH"]
    result = []
    for d in out:
        overlaps = [] if d["cls"] == "MULTIPATH" else [
            o for o in big if o is not d and o["cls"] != d["cls"]
            and o["start"] < d["end"] and o["end"] > d["start"]]
        evidence, confidence = explain(d, kp, rfi, overlaps)
        result.append({"start": iso(d["start"]), "end": iso(d["end"]), "class": d["cls"],
                       "tractors": list(d["tractors"]), "action": ACTION[d["cls"]],
                       "confidence": confidence, "evidence": evidence})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data")
    parser.add_argument("--output", default="submission.json")
    parser.add_argument("--github-handle", required=True, help="your GitHub username")
    parser.add_argument("--repo-url", required=True, help="https://github.com/<you>/<your solution repo>")
    parser.add_argument("--display-name", default=None, help="optional name for the results page")
    args = parser.parse_args()
    participant = {"github_handle": args.github_handle}
    if args.display_name:
        participant["display_name"] = args.display_name
    submission = {
        "participant": participant,
        "repository_url": args.repo_url,
        "detections": detect(args.data),
    }
    with open(args.output, "w") as f:
        json.dump(submission, f, indent=2)
    print(f"Wrote {len(submission['detections'])} detections to {args.output}")


if __name__ == "__main__":
    main()
