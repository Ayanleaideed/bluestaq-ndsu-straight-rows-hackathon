# Presentation Prep

## The idea in one line

A tractor has a problem when it looks different from what it should look like right now.
"Should" = the other two tractors + the storm sensor (S4).

## Normal (working, calm)

| Measurement | Normal |
|---|---|
| Mean signal (`mean_cn0_dbhz`) | 45 dB-Hz |
| Weakest satellite (`min_cn0_dbhz`) | 40 dB-Hz |
| Satellites | 12 |
| Drift (`cross_track_error_m`) | 0.01-0.02 m |
| Fix / link | `RTK_FIXED`, link up |
| S4 | about 0.06 |
| Working hours | 11:00-03:00 UTC, speed 4.5. Parked = speed 0, ignored. |

## The numbers per cause

| Cause | Fires when | Measured on the labels | Minimum length |
|---|---|---|---|
| **Space weather** | S4 ≥ 0.2 **and** all 3 working tractors' signal < 40 | Signal 29-35 on all three, same drop; S4 0.42-0.80; RTK_FIXED about 0% | 30 min |
| **Jamming** | Signal ≥ 4 dB below normal (45, or the storm's level during a storm) | 45 → 22 / 32 / 27 in one minute (TRN-03); different drop per tractor | 5 min |
| **Spoofing** | One tractor drifts > 1 m more than the fleet median **and** its signal is within 2 dB of the others | Drift ramps 0.08 → 6 m on one tractor; the others stay at 0.02 | 5 min |
| **Equipment, antenna** | One tractor's weakest satellite ≥ 8 dB below the fleet's | T2 weakest 12-19 vs 27-38 on the others; mean signal barely moves | 10 min |
| **Equipment, link** | One tractor's link up < 98% of a minute, the others' ≥ 98% | Link up about 70% on average; RTK_FIXED follows it | 10 min |
| **Multipath** | Weakest satellite drops ≥ 4 dB at the north 40 m of the field | About 8 dB for 17 s, every turn there, mean signal unchanged | per pass |

## The order matters

1. **Storm first.** It sets "normal" for the storm period.
2. **Jamming second**, measured against that normal. Jammed minutes are marked.
3. **Spoofing and equipment skip jammed minutes**, so one jammer isn't reported three times.
4. **Multipath** runs on its own, per second.

## Why not just use Kp?

- Kp is a 3-hour index. On May 5 it fell from 9.0 to 3.0 at 15:00, while the labeled storm lasted until 16:00 and S4 stayed at 0.78.
- The baseline used Kp ≥ 5, so it split the storm and called the rest jamming.
- **S4 follows the labels; Kp does not.** Kp is kept only as evidence text.

## What each detection cites

- The time span, the tractors, and the measured values (signal drop, satellites, RTK_FIXED share, drift, link uptime).
- S4 and Kp.
- Any interference report from the start up to 30 min after the end (reports arrive 10-30 min late).
- Overlapping causes, as a separate detection each.

## Confidence (heuristic, not a probability)

| Cause | Confidence | Why |
|---|---|---|
| Space weather | 0.9 | Same drop on all + high S4: two independent sources agree |
| Jamming | 0.85 with an interference report, 0.7 without | Report is corroboration, not proof; some reports are false |
| Spoofing | 0.8 | Relies on the guidance monitor, which is simulated and idealized |
| Equipment | 0.8 | One machine only, the others normal |
| Multipath | 0.6 | Recurs every pass; which dip is "the" one can't be told apart |

## Results to quote

- **Labeled days:** 12 of 12 found, 0 false alarms. Starts exact except the 3 spoofs, which are 1, 1 and 4 min late.
- **Score:** 37.5 / 40 against the page-4 formula (my own implementation); the original baseline gets 20.1.
- **Threshold test:** each threshold moved ±25%, and 13 of 14 runs were unchanged.
- **May 6:** 7 episodes + 486 multipath dips; 493 detections, limit 500; validator OK.

## Limitations (say these before they ask)

- **May 6 has no labels**, so the result there is unconfirmed.
- **Storm signal cut-off:** at 30 instead of 40 the storm is missed (storm signal sits at 29-35).
- **Multipath:** every dip is reported, so 2 duplicates per day count as false alarms (multipath F1 0.5).
- **Spoofs start 1-4 min late:** the drift ramps up slowly from zero.
- **Thresholds were tuned on 2 days** of synthetic data with 3 tractors.
- **Spoofing depends on an independent guidance monitor.** A real receiver doesn't know its own error.

## Extra data that would help

- Per-satellite signal (which satellite dips: multipath vs antenna)
- Inertial or wheel odometry (independent check for spoofing)
- AGC / noise-floor readings (direct jamming evidence)
- Local S4 or a reference station on the farm
- More tractors (better fleet median)

## Likely questions, short answers

| Question | Answer |
|---|---|
| Storm vs jamming? | Storm: same drop on all three + high S4. Jamming: different drop per tractor, S4 calm, or extra drop on top of the storm. |
| Spoofing vs jamming? | Spoofing: signal is healthy but the tractor drifts. Jamming: the signal itself drops. |
| Why does one tractor alone not prove equipment? | Spoofing also hits one tractor. Equipment shows in the signal or link; spoofing shows in drift with a healthy signal. |
| Why 4 dB? | The smallest labeled jamming drop is about 5.5 dB (T1 in TRN-04). The tractor left out of TRN-04 dropped about 3 dB. 4 sits between them. |
| Why compare with the fleet median? | Shared effects (storm, drift) cancel; only what is different about one tractor remains. |
| How did you use the labels? | To pick thresholds and to test. The May 6 rules are the same, unchanged. |
| Overfitting? | Moving each threshold ±25% gives the same 12/12, except the storm signal cut-off. |
| What does the operator do? | One action per class: halt, report, cross-check, service the one machine, or continue. |
| Can you change X live? | Every threshold is a named constant at the top of `baseline2.py`. Change it, then run `test_baseline2.py`. |

## Plot ideas

| Plot | Shows | Data |
|---|---|---|
| `fleet_overview` | Signal of T1/T2/T3 over 3 days, S4 on a second axis, labels shaded | All days |
| `storm_vs_jam` | TRN-05: storm level at 35, jamming drops to 20-24, 4 dB line | May 5 19:30-21:00 |
| `spoof_drift` | TRN-06: T2 drift ramps to 6 m, T1/T3 flat, 1 m line | May 4 13:00-14:00 |
| `antenna_fault` | TRN-09: weakest satellite, T2 vs the others, 8 dB gap | May 4 11:50-14:10 |
| `link_fault` | TRN-10: link uptime per minute, T1 vs the others | May 5 01:50-02:55 |
| `multipath_map` | Field track coloured by weakest-satellite drop; the north strip lights up | One day, one tractor |
| `labels_vs_ours` | Timeline: 12 labels vs our detections vs the baseline | May 4-5 |
| `may6_timeline` | Timeline of the 7 May 6 episodes, coloured by cause | May 6 |
| `threshold_sweep` | Labels matched at ×0.75 / ×1 / ×1.25 for each threshold | Tester output |

## 5-minute demo flow

1. **Problem (30 s):** "Is it the Sun, an adversary, or my own hardware?"
2. **Idea (30 s):** compare each tractor with the others and with S4.
3. **One episode (90 s):** TRN-05, jamming inside a storm. Show `storm_vs_jam`, the evidence text and the action.
4. **Results (60 s):** 12/12 found, 37.5 vs 20.1, the threshold test.
5. **Ambiguous case (30 s):** multipath representative, or the 18:30 jamming with no report (0.7).
6. **Reproduce (30 s):** run `test_baseline2.py` live → PASS.
7. **Limitations (30 s):** the list above.
