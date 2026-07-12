# Book extraction suitability audit

Generated deterministically by `scripts/audit_textbooks.py` using `pypdf`. PDF page numbers are one-based and no page is discarded.

## Biology – Class 10

### A. Basic metadata

- File: `X Biology EM 2025-26.pdf`
- `book_id`: `biology`
- Detected title: Biology – Class 10
- Total PDF pages: 257
- Text extraction: works on 256/257 pages with at least 100 cleaned characters; median cleaned length is 1898 characters.
- PDF type: digital text layer with mixed raster/vector page assets; full-page OCR is not required for ordinary prose. Biology's producer metadata mentions ABBYY, while Physical Sciences identifies PageMaker/Acrobat Distiller, but both expose searchable text on essentially all pages.

### B. Index and chapter extraction

| Chapter | Index page | PDF start–end | Confidence |
|---|---:|---:|---|
| 1. Nutrition | 1 | 10–34 | high |
| 2. Respiration | 26 | 35–59 | high |
| 3. Circulation | 51 | 60–86 | high |
| 4. Excretion | 78 | 87–108 | high |
| 5. Coordination | 100 | 109–131 | high |
| 6. Reproduction | 123 | 132–161 | high |
| 7. Coordination in Life Processes | 153 | 162–184 | high |
| 8. Heredity - Evolution | 176 | 185–213 | high |
| 9. Our Environment | 205 | 214–233 | high |
| 10. Natural Resources | 225 | 234–257 | high |

The index mapping is internally consistent: printed content page 1 is PDF page 10, so chapter starts use a +9 offset. Start-page title checks are recorded per chapter in the chapter-map JSON.

### C. Page mapping quality

PDF pages 1–9 are cover/QR/front matter. Printed Arabic page 1 begins at PDF page 10. For content, `pdf_page_number = textbook_page_number + 9`. Roman-numbered front matter begins at PDF page 3; cover/QR pages remain null.
The constant offset is high-confidence across all indexed chapter boundaries. The final chapter continues beyond the index's stated instructional range, so its detected end is the PDF's last page.

### D. Text extraction quality

- First chapter, PDF 10 / printed 1: `Nutrition 1 Food is needed by all living organisms mainly for growth and repair. Several organisms need food to maintain body temperature as well. A variety of substances are taken as food by organisms from single cellua`
- Middle-book, PDF 137 / printed 128: `128 Reproduction 6.3 Spore formation: Generally we may notice whitish thread like structures and blackish powder like substance on rotten fruits, bread slices and other food materials. When you touch it, the blackish pow`
- Later chapter, PDF 239 / printed 230: `230 Natural Resources x How can wells be recharged? x How would recharging of dried up wells help farmers of V addicherla? x What does the case study tell us about a water resource and its effect on farmers? 10.1.1 Water`
- Diagram-bearing sample, PDF 133: text and labels are partly extractable; `124 Reproduction Take a tea spoonful of curd and mix it thoroughly with around 60 tea spoonsful of (half of the glass) luke warm milk in a bowl. Take another tea spoonful of curd and mix it with same quantity of cold mil`
- Table sample, PDF 154: table words extract, but row/column structure is flattened; `Reflection of light at curved surfacesReproduction145 Hence meiosis is also called as Reduction Division. The daughter cells are haploid in condition. You will learn more about this in further classes. x What differences`

### E. Noise analysis

- Repeated running text such as `Government's Gift for Students' Progress` is removed from `cleaned_text` but retained in `raw_text`.
- No actual Unicode replacement glyphs were detected. Curly apostrophes and other valid Unicode punctuation are preserved.
- Chapter names and printed page numbers are sometimes concatenated with body text because the PDF reading order lacks separators.
- QR/front matter is retained and explicitly marked; no low-text page is silently dropped.
- Line-break hyphenation is repaired only for alphabetic word breaks. Spelling and source wording are otherwise preserved.

### F. Formula/equation extraction audit

Equation-like text is flagged on 152 content pages. Plain inline equations and chemical formula characters are often searchable, but fractions become linearized, superscripts/subscripts frequently become spaced baseline digits, and diagram-positioned symbols may be reordered.
- PDF 10 / printed 1: `NutritionGovernment’s Gift for Students’ Progress 1 Food is needed by all living organisms mainly for growth and repair. Several organisms need food to maintain body temperature as well. A variety of substances are taken`
- PDF 11 / printed 2: `NutritionGovernment’s Gift for Students’ Progress 2 Most of the food that we eat is obtained from plants. Even if we depend on animal products, we would find that those animals usually depend on plants for their food. Bu`
- PDF 12 / printed 3: `NutritionGovernment’s Gift for Students’ Progress 3 CO2 + 2H2O CH2O + H2O + O2 What would be the reaction to show that glucose (C6H12O6) is being synthesized? Write down a balanced equation to show this. (Refer the lesso`

### G. Diagram and table dependency

- 159/248 content pages contain at least one embedded image object; 28 pages have explicit table text; 129 pages explicitly reference a figure/diagram.
- Figure captions and many diagram labels are extractable, but spatial relationships are not represented in plain text. Table contents are flattened rather than reconstructed.
- Pages marked `diagram_reference_present` should be candidates for page-image or multimodal augmentation when questions depend on geometry, circuits, anatomy, experimental apparatus, or graph interpretation.

### H. Suitability verdict

**Suitable with caveats.** Prose coverage, deterministic page mapping, and chapter boundaries are strong enough for Milestone 1 page-aware retrieval experiments. Caveats are equation fidelity, flattened tables, lost diagram geometry, concatenated running headers/page numbers, and imperfect section-heading detection.

## Physical Sciences – Class 10

### A. Basic metadata

- File: `X Physics EM 2025-26.pdf`
- `book_id`: `physical_sciences`
- Detected title: Physical Sciences – Class 10
- Total PDF pages: 327
- Text extraction: works on 323/327 pages with at least 100 cleaned characters; median cleaned length is 1655 characters.
- PDF type: digital text layer with mixed raster/vector page assets; full-page OCR is not required for ordinary prose. Biology's producer metadata mentions ABBYY, while Physical Sciences identifies PageMaker/Acrobat Distiller, but both expose searchable text on essentially all pages.

### B. Index and chapter extraction

| Chapter | Index page | PDF start–end | Confidence |
|---|---:|---:|---|
| 1. Reflection of Light at Curved Surfaces | 1 | 11–31 | high |
| 2. Chemical Equations | 22 | 32–44 | high |
| 3. Acids, Bases and Salts | 35 | 45–71 | high |
| 4. Refraction of Light at Curved Surfaces | 62 | 72–95 | high |
| 5. Human Eye and Colourful World | 86 | 96–121 | high |
| 6. Structure of Atom | 112 | 122–138 | high |
| 7. Classification of Elements - The Periodic Table | 129 | 139–166 | medium |
| 8. Chemical Bonding | 157 | 167–194 | medium |
| 9. Electric Current | 185 | 195–228 | medium |
| 10. Electromagnetism | 219 | 229–258 | medium |
| 11. Principles of Metallurgy | 249 | 259–275 | medium |
| 12. Carbon and its Compounds | 266 | 276–327 | medium |

The index mapping is internally consistent: printed content page 1 is PDF page 11, so chapter starts use a +10 offset. Start-page title checks are recorded per chapter in the chapter-map JSON.

### C. Page mapping quality

PDF pages 1–10 are cover/QR/front matter. Printed Arabic page 1 begins at PDF page 11. For content, `pdf_page_number = textbook_page_number + 10`. Roman-numbered front matter begins at PDF page 3; cover/QR pages remain null.
The constant offset is high-confidence across all indexed chapter boundaries. The final chapter continues beyond the index's stated instructional range, so its detected end is the PDF's last page.

### D. Text extraction quality

- First chapter, PDF 11 / printed 1: `Reflection of light at curved surfaces 1 In class 7 and 8 you have learnt about the image formation in plane mirrors. You also discussed about the spherical mirrors. You know that why the curved surfaces are known as sph`
- Middle-book, PDF 144 / printed 134: `129 Classification of Elements - The Periodic Table A medical shop contains a vast number of medicines. The shop keeper finds it difficult to remember all the names of medicines that he has. When you go to a medical shop`
- Later chapter, PDF 281 / printed 271: `Carbon and its Compounds 266 The food you eat, the clothes you wear, the cosmetics you use, the fuels you use to run automobiles are all the compounds of carbon. Carbon was discovered in prehistory and it was known to th`
- Diagram-bearing sample, PDF 182: text and labels are partly extractable; `167 Chemical Bonding Formation of cation: aluminium ion (Al3+): 13Al(g) g Al3+ (g) + 3e- Electronic configuration 2, 8, 3 2, 8 or [Ne] 3s23p1 [Ne] Formation of anion: chloride ion (C l-): 3Cl(g) + 3e- g 3Cl– (g) Electron`
- Table sample, PDF 161: table words extract, but row/column structure is flattened; `146 Classification of Elements - The Periodic Table Atomic radius of an element is not possible to measure in its isolated state. This is because it is not possible to determine the location of the electron that surround`

### E. Noise analysis

- Repeated running text such as `Government's Gift for Students' Progress` is removed from `cleaned_text` but retained in `raw_text`.
- No actual Unicode replacement glyphs were detected. Curly apostrophes and other valid Unicode punctuation are preserved.
- Chapter names and printed page numbers are sometimes concatenated with body text because the PDF reading order lacks separators.
- QR/front matter is retained and explicitly marked; no low-text page is silently dropped.
- Line-break hyphenation is repaired only for alphabetic word breaks. Spelling and source wording are otherwise preserved.

### F. Formula/equation extraction audit

Equation-like text is flagged on 261 content pages. Plain inline equations and chemical formula characters are often searchable, but fractions become linearized, superscripts/subscripts frequently become spaced baseline digits, and diagram-positioned symbols may be reordered.
- PDF 13 / printed 3: `Reflection of light at curved surfacesGovernment’s Gift for Students’ Progress 3 This gives us an idea of what is likely to happen with a spherical mirror. A concave mirror will be like the rubber sole bent inwards (fig-`
- PDF 15 / printed 5: `Reflection of light at curved surfacesGovernment’s Gift for Students’ Progress 5 Measure the distance of this spot from the pole of the mirror. This distance is the focal length (f) of the mirror. The radius of curvature`
- PDF 16 / printed 6: `6 Reflection of light at curved surfacesGovernment’s Gift for Students’ Progress 1 2 3 4 Lab Activity fig-6 Aim: Observing the types of images and measuring the object distance and image distance from the mirror. Materia`
- Reliability warning: Ω is sometimes rendered as `W`, exponents may appear as separate digits (for example `I2 R`), reaction arrows and charge signs can degrade, and displayed fractions lose numerator/denominator layout. Formula-sensitive retrieval should retain page images or add layout-aware extraction.

### G. Diagram and table dependency

- 191/317 content pages contain at least one embedded image object; 41 pages have explicit table text; 123 pages explicitly reference a figure/diagram.
- Figure captions and many diagram labels are extractable, but spatial relationships are not represented in plain text. Table contents are flattened rather than reconstructed.
- Pages marked `diagram_reference_present` should be candidates for page-image or multimodal augmentation when questions depend on geometry, circuits, anatomy, experimental apparatus, or graph interpretation.

### H. Suitability verdict

**Suitable with caveats.** Prose coverage, deterministic page mapping, and chapter boundaries are strong enough for Milestone 1 page-aware retrieval experiments. Caveats are equation fidelity, flattened tables, lost diagram geometry, concatenated running headers/page numbers, and imperfect section-heading detection.

## Cross-book recommendation

Use these page records as the immutable source layer. Next, create a small retrieval benchmark with questions labeled by `book_id`, chapter, printed page(s), answer span, and a `visual_dependency` flag. Evaluate page retrieval first, then section/chunk retrieval; keep formula- and diagram-dependent questions as a separately reported slice.

## Reproduction

```powershell
python -m pip install pypdf
python scripts/audit_textbooks.py
```
