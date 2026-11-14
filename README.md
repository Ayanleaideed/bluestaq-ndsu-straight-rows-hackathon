# Straight Rows: why is the tractor drifting?

My entry for the Bluestaq x NDSU Straight Rows Hackathon. Three tractors (T1, T2, T3) steer
by GPS. When guidance degrades, the detector says when it happened, which tractors were hit,
which of five causes it was, and what the operator should do.

The detector is `submission/baseline2.py`. The official event guide is in `docs/`.

## Reproduce my results

Python 3.11 or newer, from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/get_data.py
```

Write `submission.json` for the scored day (May 6) and check its format:

```bash
python submission/baseline2.py --data data --output submission.json \
  --github-handle Ayanleaideed \
  --repo-url https://github.com/Ayanleaideed/bluestaq-ndsu-straight-rows-hackathon
python submission/validate_submission.py submission.json
```

Score the detector against the 12 labeled episodes of May 4-5:

```bash
python submission/test_baseline2.py --data data
```

## How I got here

**1. Measured normal.** A working tractor on a calm day has mean signal about 45 dB-Hz,
weakest satellite about 40, 11 to 13 satellites, `RTK_FIXED`, correction link up, and
cross-track error about 0.02 m.

**2. Ran the starter baseline against the labels.** It found 7 of 12 with 5 false alarms.
The misses had clear reasons:

- It separates storm from jamming with Kp. Kp falls while the storm is still affecting the
  farm, so the tail of each storm was reported as jamming.
- It gives each tractor one cause per minute, so jamming or spoofing inside a storm is lost.
- Its link rule (`link < 0.7`) sits exactly at the faulty link's average uptime.
- It has no multipath rule and never checks whether a tractor is parked.

**3. Changed the question.** Instead of "is this value bad?", `baseline2.py` asks "does this
tractor look different from what it should look like right now?". "Should" comes from the
other two tractors and from S4 (scintillation), which follows the storm on the farm far
better than Kp.

## The five checks

Each check runs on its own, so two causes can be reported at the same time.

| Cause | Rule | Action |
|---|---|---|
| Space weather | All three working tractors below 40 dB-Hz in the same minute while S4 >= 0.2, for at least 30 minutes. | Halt or degraded mode |
| Jamming | Signal at least 4 dB below normal. Normal is the calm level, or the storm's own level during a storm. Only tractors that average a 4 dB drop are listed. | Halt and report |
| Spoofing | One tractor drifts more than 1 m beyond the fleet median while its signal stays within 2 dB of the fleet's. | Halt, cross-check, report |
| Equipment fault | One tractor only: weakest satellite at least 8 dB below the fleet's (antenna), or correction link up less than 98% of a minute while the others' links are up. At least 10 minutes. | Service that machine, others continue |
| Multipath | The weakest satellite drops at least 4 dB on a pass through the north 40 m of the field. | Continue |

Every detection carries the measured values it was based on (signal drop per tractor,
satellites, share of `RTK_FIXED`, drift, link uptime, S4, Kp). Interference reports are
quoted when one falls near a jamming event, but never decide the class: they arrive late and
one of the four looks false. Confidence is a fixed value per cause, not a calibrated
probability.

## How the labels were used

The 12 labeled episodes were used to choose the thresholds and to score the result. The
detector never reads the label file, and no time, date or tractor ID is hard-coded.

## Results

| Test | Result |
|---|---|
| May 4-5, 12 labeled episodes | 12 of 12 found, 0 false alarms |
| Start times | 9 exact; the three spoofs start 1, 1 and 4 minutes late |
| Organizers' scorer (`score_submission.py`) | 40.0 / 40. Starter baseline: 20.1 / 40 |
| Each threshold moved 25% down and up | 13 of 14 runs unchanged |
| May 6 output | 7 episodes plus 486 multipath dips; 493 detections (limit 500) |

40/40 is a score on the same two days the thresholds were chosen from. May 6 is unlabeled,
so the result there is not confirmed.

## Limitations

- **Thresholds come from two days** of synthetic data with three tractors.
- **Storm signal cut-off:** storm signal sits at 29 to 35 dB-Hz. With the cut-off at 30
  instead of 40, storms are missed (the one failing run in the threshold test).
- **Multipath is tied to this field.** The rule looks at the north strip, where the dip
  recurs on every pass, and reports every dip: 486 short "continue" reports on May 6. A real
  product would show them as one recurring note.
- **Spoofs start 1 to 4 minutes late** because the drift ramps up slowly from zero.
- **Spoofing relies on the guidance monitor**, an idealized measurement. A real receiver
  does not know its own error.
- **The fleet comparison needs healthy neighbours.** Two tractors with the same fault at the
  same time would look like the norm.

## Extra data that would help

- Per-satellite signal: which satellite dips separates multipath from an antenna fault.
- Inertial or wheel odometry: an independent position check for spoofing.
- AGC or noise-floor readings: direct evidence of jamming.
- A reference station or local S4 on the farm.
- More tractors, for a steadier fleet median.

## Files

| File | What it is |
|---|---|
| `submission/baseline2.py` | The detector |
| `submission/test_baseline2.py` | Scores May 4-5 against the labels, validates May 6, runs the threshold test |
| `submission/baseline.py` | The organizers' starter baseline, unchanged, kept for comparison |
| `submission/validate_submission.py` | The organizers' format check |
| `notebooks/approach.ipynb` | The same approach step by step, with plots |
| `submission.json` | The May 6 output that was submitted |

## AI assistance

I used Claude, an AI coding assistant, to help write and check the code and this README, as
the event rules allow. I reviewed the work and can explain and defend all of it.
