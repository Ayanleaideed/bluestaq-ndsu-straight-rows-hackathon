# Session context: Straight Rows Hackathon

Handoff note for a new Claude session. Read this first, then `README.md` and
`docs/Bluestaq_NDSU_Straight_Rows_Hackathon_Official.pdf` (page 4 has the scoring rules).

## Deadline

**Saturday, November 14, 2026, 4:00 pm Central Time.** By then: repository public, and a
pull request open on `Bluestaq/ndsu-hackathon-submissions` adding
`submissions/Ayanleaideed/submission.json`. A five-minute demo plus three minutes of Q&A follows.

## How to work with me (the user)

- **Explain and ask first. Do not edit or run code unless I say so in plain words.**
  "ok" is not a go-ahead. I want to type the code changes myself so I can defend them in the demo.
- Use plain, specific language. Start with the files and the code, not theory. Short answers.
- My goal is deep understanding: judges may ask me to explain or modify the implementation.
- Act as a concise senior engineering partner: challenge weak assumptions, never invent
  columns, thresholds or test results, and say plainly what was and was not verified.
  (The `hackathon-engineering-partner` skill is local to my Windows machine and not in git.)

## Where we stopped

I now understand the files and the dataset. **No rules have been changed yet.**
`submission/baseline.py` is the original starter code. `submission.json` is the unmodified
baseline output (7 detections, passes the validator).

**The next step:** check the baseline against the 12 known answers on May 4-5 before
changing any rules.

Simplest way (my preferred way): in `submission/baseline.py` lines 23-24, temporarily set

```python
EVAL_START = pd.Timestamp("2026-05-04T00:00:00Z")
EVAL_END   = pd.Timestamp("2026-05-06T00:00:00Z")
```

run the baseline, and compare with `data/labels/train_episodes.json`. While the dates are
changed the validator reports FAIL (expected). **Set the dates back to May 6 / May 7 before
submitting.**

After that, in order:

1. Fix the rules in `classify()` (`baseline.py` line 45), one failure at a time, re-checking against the 12 labels.
2. Decide the multipath question (below).
3. Write real evidence text and confidence values (currently boilerplate and a fixed 0.5).
4. Rewrite `README.md`: approach, exact reproduce command, how labels were used, failure modes, limitations.
5. Prepare the demo.

## Setup on a new machine

`data/`, `.venv/` and the uv files (`pyproject.toml`, `uv.lock`) are not in git.
Dependencies are pinned in `requirements.txt`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/get_data.py
python submission/baseline.py --data data --output submission.json --github-handle Ayanleaideed --repo-url https://github.com/Ayanleaideed/bluestaq-ndsu-straight-rows-hackathon
python submission/validate_submission.py submission.json
```

## The files

| File | Role |
|---|---|
| `submission/baseline.py` | The detector. The main file to edit. `detect()` loads data, `classify()` holds the rules, the loop after it merges minutes into episodes. |
| `submission.json` | The answer handed in. Overwritten on every run of `baseline.py`. |
| `submission/validate_submission.py` | Format check only. Says nothing about correctness. Do not edit. |
| `data/labels/train_episodes.json` | The 12 true answers for May 4-5. |
| `notebooks/main.ipynb` | My own exploration notebook. |
| `notebooks/starter_notebook.ipynb` | Organizer's notebook; runs the same baseline. |

## The data

One telemetry file covers all three days at 1 Hz for tractors T1, T2, T3 (777,600 rows, no
missing values). Dates are year-month-day.

| Dates | What | Episodes |
|---|---|---|
| 2026-05-04 and 2026-05-05 | Development (practice) | 12, labeled |
| 2026-05-06 | Evaluation (scored) | 8, unlabeled |

Tractors work 11:00Z-03:00Z and park 03:00Z-11:00Z. Only working tractors count.

Normal working values: mean signal about 45, weakest-satellite signal about 40, 11-13
satellites, `RTK_FIXED`, link up, cross-track error about 0.02 m.

`data/sda/` is context, not the signal itself: Kp and Dst (magnetic storm level), S4
(scintillation, every 15 min, about 0.06 calm and 0.45-0.8 in storms), 4 interference
reports (late by 10-30 min, incomplete, one probably false), 2 advisories.

## What each cause looks like (measured on the labeled days)

| Cause | Signature |
|---|---|
| Space weather | All three tractors degrade by the same amount (signal 30-35, 10-11 satellites, fix drops). S4 is high for exactly the labeled span. |
| Jamming | Signal and satellite count collapse by a different amount per tractor, sharp onset, S4 calm. A mildly affected tractor is left out of the label. |
| Spoofing | Cross-track error ramps to 4-12 m on one tractor while signal, satellites and fix stay healthy. |
| Equipment fault (antenna) | One tractor: weakest-satellite signal below 25 for about 90 s in every 10 min; mean signal barely moves. |
| Equipment fault (link) | One tractor: `base_link_ok` true only about 70% of the time; fix state follows it. |
| Multipath | Weakest-satellite signal drops about 8 dB for about 17 s at the north headland turn; mean signal unchanged. |

Causes overlap in the labels: jamming and a spoof occur inside a storm, and a spoof occurs
inside an antenna fault.

## Baseline versus the 12 labels (matched by hand, approximate)

| Label | Truth | Baseline | Verdict |
|---|---|---|---|
| TRN-01 | Space weather, 05-05 11:00-16:00 | Space weather 09:45-15:00 | Found; starts early while parked, ends short |
| TRN-02 | Space weather, 05-05 19:00-22:00 | Space weather 19:00-21:00 | Found; ends short |
| TRN-03 | Jamming, 05-04 16:30-17:12, all | Same | Exact |
| TRN-04 | Jamming, 05-04 21:00-21:36, T1+T3 | Jamming 21:00-21:34, T3 | Found; T1 missing |
| TRN-05 | Jamming, 05-05 20:00-20:36, all | nothing | Missed (inside the storm) |
| TRN-06 | Spoofing T2, 05-04 13:12-13:54 | Spoofing 13:19-13:54 | Found |
| TRN-07 | Spoofing T1, 05-05 00:30-01:18 | Spoofing 00:34-01:18 | Found |
| TRN-08 | Spoofing T3, 05-05 21:30-22:06 | Spoofing 22:00-22:06 | Missed (inside the storm) |
| TRN-09 | Equipment T2, 05-04 12:00-14:00 | Equipment 12:00-13:17 | Found; cut short by the spoof |
| TRN-10 | Equipment T1 (link), 05-05 02:00-02:48 | nothing | Missed |
| TRN-11, TRN-12 | Multipath, 17 s each | nothing | Missed (no rule) |

About 7 of 12 found, 5 missed, 4 false alarms: two fake "jamming" hours where a storm
continues after Kp drops, one "space weather" at 07:00 while parked, one 5-minute leftover
equipment fault.

Known weaknesses in the baseline rules:

- Storm versus jamming is decided by Kp alone. Kp drops while the storm is still labeled; S4 follows the labels.
- Signal rules do not check whether the tractor is parked.
- One label per tractor-minute, so overlapping causes are lost.
- The link rule (`link < 0.7`) sits right at the fault's average and misses it.
- No multipath rule. S4, interference reports, advisories, `fix_state` and `num_sats` are unused.
- Confidence is always 0.5 and the evidence text is boilerplate.

## Evaluation day (May 6): my reading of the data, not confirmed

| Time (Z) | Tractors | Likely cause | Baseline |
|---|---|---|---|
| 01:00-02:00 | T1 | Equipment fault (antenna) | Found |
| ~02:10-03:00 | All three | Jamming; interference report at 02:39 | Found |
| 13:00-16:00 | All three | Space weather (S4 about 0.45) | Split; 15:00-16:00 mislabeled as jamming |
| ~16:30-17:15 | T1 | Spoofing | Found |
| 18:30-19:00 | T3 strong, T1 moderate, T2 mild | Jamming, no report | Found |
| ~19:40-20:30 | T2 | Equipment fault (link) | Missed |
| ~21:50-22:25 | T3 | Spoofing | Found |
| unknown | one tractor | Multipath representative | Not attempted |

## Open decision: multipath

The dip happens about 162 times per tractor per day (every north-headland turn, all three
tractors at once). Each labeled day has only one "representative" and nothing found so far
distinguishes it. The scoring rules exempt multipath reports of three minutes or less from
false-alarm penalties, but credit needs a match on the representative.

- Report every dip (about 486 detections, limit is 500): likely earns the multipath class, one fifth of macro-F1, at the cost of a very long submission.
- Report none or few: clean submission, multipath likely scores zero.

Not decided yet.

## Scoring reminders

- Judges: technical execution 30, decision quality 25, innovation 20, rigor 15, demo 10.
- Automated diagnostic (supporting evidence only): 25 x macro-F1 over the five causes + 15 x onset credit. A match needs time overlap of at least 0.30 and tractor-set overlap of at least 0.50. Onset credit is full within 5 minutes of the true start and zero at 60 minutes.
- Never put an email address or student ID in `submission.json`.
