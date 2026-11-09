# Historical artifact text identities v2

The old retrieval/generation manifests record exact raw SHA-256 values from
their original checkouts. Three text artifacts had CRLF bytes at freeze time,
but their LF Git checkout bytes differ. This is a checkout-format difference,
not permission to replace data or rewrite historical results.

`config\historical_text_identity_v2.json` is an **explicit read-only compatibility
profile**. Each named entry pins both its old expected raw hash and its
UTF-8/CRLF-to-LF identity. Verifiers still default to raw v1 checks. With the
profile selected, a raw mismatch may pass only when:

- The exact named path is a recognized text artifact.
- Its historical expected hash matches that manifest entry.
- Strict UTF-8 decoding succeeds, CRLF alone is replaced by LF, and the pinned
  normalized hash matches.

No whitespace, BOM, wording, JSON ordering, punctuation or lone carriage return
is removed. Substantive modifications still fail. The result lists every
artifact verified through v2 rather than hiding the compatibility path.

| Named text artifact | Historical raw SHA-256 | UTF-8/LF SHA-256 |
|---|---|---|
| `data/benchmarks/retrieval_benchmark_v1.jsonl` | `d333768b9c645cf0048a38356bfea69aa4a9e7220010e2cdf6340b91af38c046` | `10c622374f0a4a08475bc7af0014a18895191e2808a463066fb06d50786637be` |
| `reports/openai_generation_experiments/comparisons/full_40_labeled/comparison_report.md` | `d85a5ddabcfcd83dd5813244ce98439eba05eb03cbd3312f8a9a889e28268282` | `d227bc95995290bdd0c332a62aa581a99a52033d923d6ed102f510dd2c5d2c9c` |
| `reports/openai_generation_experiments/comparisons/full_40_labeled/local_vs_gpt4o_labeled_comparison.html` | `90af839f16c32d391c5af3416ddf0379ae9ede1da7b3ab342723c9480c416c0c` | `40a67886e31726b04dac2285ad9c1b0d3a2d57cc20d1dada375ef4edc46a936e` |

```powershell
.\.venv-assessment\Scripts\python.exe scripts\manage_retrieval_baseline_v1.py checksums `
  --text-identity-profile config\historical_text_identity_v2.json
.\.venv-assessment\Scripts\python.exe scripts\manage_generation_baseline_v1.py checksums `
  --text-identity-profile config\historical_text_identity_v2.json
```

These commands do not regenerate manifests or scores. Missing historical
artifacts remain explicit errors. Retrieval v1 additionally requires the
authorized PDFs and eight original ignored NPZ indexes; they are not inputs
to the separate open assessment run. An authorized owner can locally supply
the exact originals for historical byte regression. This profile does not
grant rights to publish them.

**Binary safety:** PDF, NPZ, GGUF, wheels, model weights and archives are never
newline-normalized. Replacing CRLF bytes inside a binary changes its content,
even if the resulting digest looks plausible. Their verification remains
exact raw SHA-256. Tests cover both newline-equivalent text acceptance and
binary/substantive-text rejection.

New source/text checkouts use the explicit LF rules in `.gitattributes`;
HTML is now included. No historical manifest, benchmark record or recorded
result was rewritten. The final assessment freeze already uses normalized-LF
execution-file identities and retains its original configuration/code hashes.
