# Cache false-hit risk: 2524 (complaint, other complaint's cluster) pairs

Highest cross-complaint similarity: 0.847 (reference-less CACHE_HIT_THRESHOLD 0.75)

| threshold | complaint pairs that would be served ANOTHER complaint's plan |
|---|---|
| 0.65 | 62 |
| 0.68 | 47 |
| 0.7 | 36 |
| 0.72 | 24 |
| 0.75 | 12 |
| 0.78 | 7 |
| 0.8 | 7 |
| 0.85 | 0 |

With a SIIS reference supplied (Samsung's evaluation format), a cached plan is
reused only for the same document at >= 0.90, above every distinct-query pair
measured with the real model (max 0.858).
