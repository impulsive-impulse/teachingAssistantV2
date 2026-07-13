# Hierarchy Detection Audit

No gold evidence was used during structure detection.

| Book | Chapters | Sections | High | Medium | Low | Paragraph groups | Avg tokens | p50 | p95 | Fallback chapters |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| biology | 10 | 180 | 180 | 0 | 0 | 384 | 203.3 | 253 | 304 | 0 |
| physical_sciences | 12 | 229 | 229 | 0 | 0 | 464 | 200.2 | 251 | 298 | 0 |

## Representative successes

- `biology` / Nutrition: “1.1 Autotrophic Nutrition” (high).
- `biology` / Nutrition: “1.2 Photosynthesis” (high).
- `biology` / Nutrition: “1.2.1 Factors (Materials) essential for the process of Photosynthesis” (high).
- `biology` / Nutrition: “1.2.2 Water and Photosynthesis” (high).
- `biology` / Nutrition: “1.2.3 Air and Photosynthesis” (high).
- `biology` / Nutrition: “1.2.4 Light and Photosynthesis” (high).
- `biology` / Nutrition: “1.2.5 Chlorophyll and Photosynthesis” (high).
- `biology` / Nutrition: “1.3 Mechanism of Photosynthesis” (high).
- `physical_sciences` / Reflection of Light at Curved Surfaces: “1.1 Reflection of light by spherical mirrors” (high).
- `physical_sciences` / Reflection of Light at Curved Surfaces: “1.1.1 Verifying your drawing” (high).
- `physical_sciences` / Reflection of Light at Curved Surfaces: “1.2 Ray diagrams (Image formation by concave mirror)” (high).
- `physical_sciences` / Reflection of Light at Curved Surfaces: “1.3 Ray Diagrams: (Image formation by convex mirror)” (high).
- `physical_sciences` / Reflection of Light at Curved Surfaces: “1.4 Derivation of mirror formula for spherical mirrors” (high).
- `physical_sciences` / Reflection of Light at Curved Surfaces: “1.5 Sign convention for the parameters related to the mirror equation” (high).
- `physical_sciences` / Reflection of Light at Curved Surfaces: “1.6 Magnification (m)” (high).
- `physical_sciences` / Reflection of Light at Curved Surfaces: “1.7 Making of solar cooker” (high).

## Representative failures

No chapter required the chapter-only fallback.

## Interpretation

Numbered headings are high confidence; conservative short title-like lines are medium confidence. Low-confidence candidates remain content and are therefore counted as zero detected headings. Detection is useful for retrieval experiments but remains heuristic because PDF text lacks font and indentation metadata.
