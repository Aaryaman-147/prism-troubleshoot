# Retrieval calibration — 99 probes (92 should link, 7 must not)

Ranked by fewest WRONG deeplinks, then most correct. Compared across search-text versions.
(Full per-probe table: `python scripts/calibrate_retrieval.py --probes all --detail`.)

## Search text v1

| alpha | floor | margin | correct | wrong | abstain |
|---|---|---|---|---|---|
| 0.75 | 0.6 | 0.08 | 73 | 0 | 26 |
| 0.75 | 0.65 | 0.08 | 70 | 0 | 29 |
| 0.75 | 0.7 | 0.08 | 63 | 0 | 36 |
| 0.75 | 0.75 | 0.08 | 51 | 0 | 48 |
| 1.0 | 0.75 | 0.08 | 51 | 0 | 48 |
| 1.0 | 0.8 | 0.05 | 44 | 0 | 55 |
| 1.0 | 0.8 | 0.08 | 41 | 0 | 58 |
| 0.75 | 0.8 | 0.08 | 35 | 0 | 64 |

## Search text v2

| alpha | floor | margin | correct | wrong | abstain |
|---|---|---|---|---|---|
| 0.75 | 0.6 | 0.08 | 71 | 0 | 28 |
| 0.75 | 0.65 | 0.08 | 65 | 0 | 34 |
| 0.75 | 0.7 | 0.08 | 51 | 0 | 48 |
| 0.75 | 0.75 | 0.08 | 37 | 0 | 62 |
| 1.0 | 0.8 | 0.05 | 29 | 0 | 70 |
| 1.0 | 0.8 | 0.08 | 28 | 0 | 71 |
| 0.75 | 0.8 | 0.08 | 26 | 0 | 73 |
| 0.75 | 0.6 | 0.05 | 79 | 1 | 19 |

## Chosen settings (code defaults)
```
RETRIEVAL_TEXT_VERSION=v1
DEEPLINK_ALPHA=0.75
DEEPLINK_MIN_CONFIDENCE=0.6
DEEPLINK_MARGIN=0.08
```
