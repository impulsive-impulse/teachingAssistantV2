# Source and textbook verification

## Method

- Navigated the two public seed pages in the browser and copied their visible chapter-navigation links (10 Biology, 12 Physical Sciences).
- Performed a controlled extraction only from those 22 allow-listed pages; original wording and website answer material remain in the raw temporary JSONL.
- Located candidate evidence in processed page artifacts, then independently re-extracted the cited pages from the original PDFs with pypdf.
- Rendered selected original PDF pages for formula, table, circuit, ray, molecular, experiment, and diagram checks; page contact sheets are under `rendered_pdf_checks/`.
- Accepted textbook page labels were read from rendered pages when layout mattered; offsets were not treated as authoritative.

## Important page-mapping finding

The processed Physical Sciences metadata uses a constant +10 textbook/PDF offset. Rendered originals show a later +15 relationship. For example, PDF page 274 is printed textbook page 259 in Chapter 11 (Principles of Metallurgy), although the processed record labels it textbook page 264. Proposal evidence for later chapters uses the printed page labels from the rendered PDF.

## Per-question evidence and rubric

### GEN-BIO-001 — Nutrition

- Source: https://www.manabadi.co.in/ts-scert-10th-class-Biology-Lesson-1-Nutrition/278 (question 22)
- Accepted evidence: textbook pages [3, 4]; PDF pages [12, 13]
- Required: Use a sun-exposed leaf and boil it in water; Remove chlorophyll using alcohol in a water bath; Add iodine solution; A blue-black colour shows starch
- Optional: State the safety precaution not to heat alcohol directly
- Unsupported: Iodine produces starch rather than merely testing for it
- Dependencies: formula=False, visual=False, table=False, multiple_passages=False
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=accept

### GEN-BIO-002 — Nutrition

- Source: https://www.manabadi.co.in/ts-scert-10th-class-Biology-Lesson-1-Nutrition/278 (question 13)
- Accepted evidence: textbook pages [16, 17]; PDF pages [25, 26]
- Required: Bile emulsifies fats into small globules; Pancreatic lipase acts on fats; Digestion is completed in the small intestine; End products include fatty acids and glycerol
- Optional: The intestinal medium becomes alkaline
- Unsupported: Fats are completely digested in the stomach
- Dependencies: formula=False, visual=False, table=False, multiple_passages=False
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=accept

### GEN-BIO-003 — Respiration

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-2-Respiration&chpid=279 (question 8)
- Accepted evidence: textbook pages [30, 31]; PDF pages [39, 40]
- Required: Alveoli are extremely numerous microscopic air sacs; Their folding/number gives an enormous moist surface area; They are closely associated with blood capillaries; These features support rapid gas exchange by diffusion
- Optional: The textbook estimates a total area near 160 m²
- Unsupported: Gas exchange occurs only in bronchi
- Dependencies: formula=False, visual=False, table=False, multiple_passages=False
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=accept

### GEN-BIO-004 — Respiration

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-2-Respiration&chpid=279 (question 17)
- Accepted evidence: textbook pages [40, 41]; PDF pages [49, 50]
- Required: Use yeast supplied with glucose solution; Remove/exclude oxygen and prevent its re-entry; Maintain an experimental setup and an appropriate comparison; Detect carbon dioxide and/or a temperature rise; Infer that yeast releases energy and CO₂ without oxygen
- Optional: Liquid paraffin excludes air; bicarbonate indicator detects CO₂
- Unsupported: Oxygen must be continuously bubbled through the anaerobic setup
- Dependencies: formula=False, visual=False, table=False, multiple_passages=False
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=accept

### GEN-BIO-005 — Circulation

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-3-Circulation&chpid=280 (question 2)
- Accepted evidence: textbook pages [58, 63, 64]; PDF pages [67, 72, 73]
- Required: Blood passes through the heart twice in one complete circulation; Describe the pulmonary circuit; Describe the systemic circuit; Explain efficient separation/delivery of oxygenated and deoxygenated blood
- Optional: Trace the named heart chambers and major vessels
- Unsupported: Humans have single circulation
- Dependencies: formula=False, visual=False, table=False, multiple_passages=True
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=accept

### GEN-BIO-006 — Circulation

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-3-Circulation&chpid=280 (question 4)
- Accepted evidence: textbook pages [60, 61]; PDF pages [69, 70]
- Required: Arteries carry blood away from the heart; veins carry it toward the heart; Arteries have thicker, more elastic muscular walls; Veins have thinner walls, wider lumen, and valves; State pulmonary-vessel exceptions if oxygenation is discussed
- Optional: Relate wall structure to pressure
- Unsupported: All arteries always carry oxygenated blood; Veins contain blue blood
- Dependencies: formula=False, visual=False, table=False, multiple_passages=False
- Website answer: partially supported. The website correctly contrasts direction and structure but misleadingly labels veins blue and overgeneralizes oxygenation.
- Verification: high; recommendation=accept

### GEN-BIO-007 — Excretion

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-4-Excretion&chpid=281 (question 1)
- Accepted evidence: textbook pages [84, 85, 86]; PDF pages [93, 94, 95]
- Required: Define excretion as removal of metabolic wastes; Explain glomerular filtration; Explain selective tubular reabsorption; Explain tubular secretion; Explain concentration of urine/water reabsorption
- Optional: Mention roles of Bowman’s capsule, loop of Henle, collecting duct, and ADH
- Unsupported: Useful glucose and amino acids are normally all excreted
- Dependencies: formula=False, visual=False, table=False, multiple_passages=True
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=accept

### GEN-BIO-008 — Excretion

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-4-Excretion&chpid=281 (question 6)
- Accepted evidence: textbook pages [88, 89]; PDF pages [97, 98]
- Required: Dialysis is needed when both kidneys cannot adequately filter wastes; Blood is withdrawn and mixed with anticoagulant; Blood flows through a semipermeable membrane against dialysis fluid; Nitrogenous wastes diffuse out while cells/proteins are retained; Cleaned blood is returned
- Optional: Dialysis fluid resembles plasma but lacks nitrogenous waste
- Unsupported: Dialysis permanently cures kidney failure
- Dependencies: formula=False, visual=False, table=False, multiple_passages=False
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=accept

### GEN-BIO-009 — Coordination

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-5-Coordination&chpid=282 (question 7)
- Accepted evidence: textbook pages [118, 119]; PDF pages [127, 128]
- Required: Phototropism is directional growth in response to light; The shoot tip perceives lateral light; Auxin influence is redistributed to the shaded side; Greater elongation on the shaded side bends the shoot toward light
- Optional: Reference Darwin/Went coleoptile experiments
- Unsupported: Light destroys every auxin molecule on the lit side
- Dependencies: formula=False, visual=False, table=False, multiple_passages=False
- Website answer: partially supported. The website identifies auxin and bending but omits the textbook’s asymmetric-growth mechanism.
- Verification: high; recommendation=accept

### GEN-BIO-010 — Coordination

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-5-Coordination&chpid=282 (question 5)
- Accepted evidence: textbook pages [103]; PDF pages [112]
- Required: A synapse is the functional contact region between two neurons; The neurons are separated by a minute gap without protoplasmic continuity; Signals cross chemically, electrically, or both
- Optional: Synapses are common in the brain and spinal cord
- Unsupported: The cytoplasm of the two neurons is continuous
- Dependencies: formula=False, visual=False, table=False, multiple_passages=False
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=revise

### GEN-BIO-011 — Reproduction

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-6-Reproduction&chpid=283 (question 1)
- Accepted evidence: textbook pages [130, 131]; PDF pages [139, 140]
- Required: Fertilisation is external in water; Eggs and sperm are exposed to currents and predators; The chance of any one gamete/egg surviving and being fertilised is low; Large numbers compensate for high loss
- Optional: No parental protection is available for many eggs
- Unsupported: Every released egg is fertilised
- Dependencies: formula=False, visual=False, table=False, multiple_passages=False
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=accept

### GEN-BIO-012 — Reproduction

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-6-Reproduction&chpid=283 (question 14)
- Accepted evidence: textbook pages [142, 143, 144, 145]; PDF pages [151, 152, 153, 154]
- Required: Mitosis has one division; meiosis has two; Mitosis forms two daughter cells; meiosis forms four; Mitosis preserves chromosome number; meiosis halves it; Mitosis supports growth/repair; meiosis forms gametes; Meiosis creates variation through recombination/segregation
- Optional: Compare prophase events and homologous chromosomes
- Unsupported: Meiosis produces genetically identical diploid cells
- Dependencies: formula=False, visual=False, table=False, multiple_passages=True
- Website answer: formatting corrupted. The website’s answer block is missing, but the question is intact and the textbook table is authoritative.
- Verification: high; recommendation=accept

### GEN-BIO-013 — Coordination in Life Processes

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-7-Coordination-in-Life-Processes&chpid=284 (question 22)
- Accepted evidence: textbook pages [162, 163]; PDF pages [171, 172]
- Required: Oesophageal walls secrete mucus; Mucus lubricates and protects the wall; The bolus slides down more easily during peristalsis
- Optional: Saliva also aids movement
- Unsupported: Mucus digests proteins
- Dependencies: formula=False, visual=False, table=False, multiple_passages=False
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=accept

### GEN-BIO-014 — Coordination in Life Processes

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-7-Coordination-in-Life-Processes&chpid=284 (question 2)
- Accepted evidence: textbook pages [166]; PDF pages [175]
- Required: Use two similar green leaves; Coat one with petroleum jelly/grease and leave one uncoated; Add equal drops of weak acid and observe; The uncoated leaf is affected while the coated leaf is protected; Petroleum jelly models the protective mucus lining of the stomach
- Optional: Observe after about half an hour
- Unsupported: Mucus neutralises all stomach acid completely
- Dependencies: formula=False, visual=False, table=False, multiple_passages=False
- Website answer: formatting corrupted. The source wording contains a corrupted 'iii human' phrase; normalization restores the textbook meaning.
- Verification: high; recommendation=revise

### GEN-BIO-015 — Heredity - Evolution

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-8-Heredity-and-Evolution&chpid=285 (question 5)
- Accepted evidence: textbook pages [180, 182, 183, 184, 186]; PDF pages [189, 191, 192, 193, 195]
- Required: Cross pure parents differing in one trait; F₁ shows only the dominant trait; Self the F₁ heterozygotes; F₂ phenotype ratio is about 3:1 and genotype ratio 1:2:1; Relate results to dominance and segregation
- Optional: Use Y/y or another textbook trait and a checkerboard
- Unsupported: Recessive factors disappear permanently in F₁
- Dependencies: formula=False, visual=False, table=False, multiple_passages=True
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=revise

### GEN-BIO-016 — Heredity - Evolution

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-8-Heredity-and-Evolution&chpid=285 (question 7)
- Accepted evidence: textbook pages [188, 189]; PDF pages [197, 198]
- Required: Females are XX and males are XY; Ova carry only X; Sperm carry either X or Y; X-bearing sperm plus X ovum gives XX; Y-bearing sperm plus X ovum gives XY; The fertilising sperm determines chromosomal sex
- Optional: Expected probability is approximately equal for XX and XY
- Unsupported: The mother’s ovum can carry Y
- Dependencies: formula=False, visual=False, table=False, multiple_passages=False
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=revise

### GEN-BIO-017 — Our Environment

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-9-Our-Environment&chpid=286 (question 1)
- Accepted evidence: textbook pages [211, 212]; PDF pages [220, 221]
- Required: Available energy decreases at each trophic transfer; Only a small fraction becomes new biomass; Energy is lost through respiration, activity, heat, and undigested material; This limits food-chain length
- Optional: Many animals convert no more than about 10% of food into body tissue
- Unsupported: Energy increases toward the top trophic level
- Dependencies: formula=False, visual=False, table=False, multiple_passages=False
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=accept

### GEN-BIO-018 — Our Environment

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-9-Our-Environment&chpid=286 (question 5)
- Accepted evidence: textbook pages [216, 217]; PDF pages [225, 226]
- Required: Persistent toxic substances enter organisms/food chains; Bioaccumulation is pollutant build-up in an organism or entry into a food chain; Biomagnification is increasing concentration across trophic levels; Top consumers can receive harmful concentrations; Toxins can disrupt food chains and ecosystem balance
- Optional: Give pesticides or heavy metals as examples
- Unsupported: Biodegradable pollutants always biomagnify indefinitely
- Dependencies: formula=False, visual=False, table=False, multiple_passages=True
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=revise

### GEN-BIO-019 — Natural Resources

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-10-Natural-Resources&chpid=287 (question 3)
- Accepted evidence: textbook pages [236]; PDF pages [245]
- Required: Define sustainable development as using the environment while retaining resources for the future; Connect development with conservation; Explain management/conservation of renewable and non-renewable resources
- Optional: Give a local water, forest, soil, or energy example
- Unsupported: Sustainability means prohibiting all resource use
- Dependencies: formula=False, visual=False, table=False, multiple_passages=False
- Website answer: partially supported. The website’s core definition is supported, but some added claims are broader than the cited textbook passage.
- Verification: high; recommendation=accept

### GEN-BIO-020 — Natural Resources

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-10-Natural-Resources&chpid=287 (question 26)
- Accepted evidence: textbook pages [230, 232, 234]; PDF pages [239, 241, 243]
- Required: Groundwater is heavily used and can be depleted by over-extraction; Recharge stores rainwater underground and revives dried wells; Recharge supports irrigation and future water availability; Name textbook measures such as dykes/barriers, percolation/storage structures, or field bunds
- Optional: Relate recharge to the Wanaparthy/Vaddicherla or Kothapally case
- Unsupported: Groundwater is unlimited because it is renewable
- Dependencies: formula=False, visual=False, table=False, multiple_passages=True
- Website answer: partially supported. The website supports the need for recharge but adds statistics and consequences not all present in the accepted passages.
- Verification: high; recommendation=accept

### GEN-PSC-001 — Reflection of Light at Curved Surfaces

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-1-Reflection-of-Light-at-Curved-Surfaces&chpid=309 (question 6)
- Accepted evidence: textbook pages [13, 20]; PDF pages [23, 30]
- Required: A convex mirror forms a virtual, erect, diminished image; It provides a wider field of view; Therefore a driver can see a larger region behind the vehicle
- Optional: Image properties hold for different object positions
- Unsupported: A convex rear-view mirror forms a real image on a screen
- Dependencies: formula=False, visual=False, table=False, multiple_passages=False
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=accept

### GEN-PSC-002 — Reflection of Light at Curved Surfaces

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-1-Reflection-of-Light-at-Curved-Surfaces&chpid=309 (question 1)
- Accepted evidence: textbook pages [18, 19]; PDF pages [28, 29]
- Required: Use f = R/2 = -4 cm and u = -10 cm under the textbook sign convention; Apply 1/f = 1/v + 1/u; Obtain v = -20/3 cm ≈ -6.67 cm; Interpret the negative sign as a real image on the object side
- Optional: The image is inverted and diminished between F and C
- Unsupported: Report v as +6.7 cm while also calling it a real same-side image
- Dependencies: formula=True, visual=False, table=False, multiple_passages=False
- Website answer: contradicted. The website gives +6.7 cm; the textbook sign convention and mirror formula give v ≈ -6.67 cm.
- Verification: high; recommendation=accept

### GEN-PSC-003 — Chemical Equations

- Source: https://www.manabadi.co.in/ts-scert-10th-class-Physical-Science-Lesson-2-Chemical-Equations/310 (question 1)
- Accepted evidence: textbook pages [25, 29, 34]; PDF pages [35, 39, 44]
- Required: Identify reactants and products by symbols/formulae; Give stoichiometric ratios of particles/moles; Relate coefficients to relative quantities/masses; Include physical states and reaction conditions when written; Explain that gas volumes/heat information may be conveyed when specified
- Optional: Use an example equation
- Unsupported: A balanced equation alone always gives reaction rate or mechanism
- Dependencies: formula=True, visual=False, table=False, multiple_passages=True
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=accept

### GEN-PSC-004 — Chemical Equations

- Source: https://www.manabadi.co.in/ts-scert-10th-class-Physical-Science-Lesson-2-Chemical-Equations/310 (question 2)
- Accepted evidence: textbook pages [25]; PDF pages [35]
- Required: Chemical reactions obey conservation of mass; Atoms are rearranged rather than created or destroyed; The count of each element must be equal on both sides; Balancing changes coefficients, not chemical formulae
- Optional: Use a simple equation as illustration
- Unsupported: Balance by changing subscripts in compounds
- Dependencies: formula=True, visual=False, table=False, multiple_passages=False
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=accept

### GEN-PSC-005 — Acids, Bases and Salts

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-3-Acids-Bases-and-Salts&chpid=311 (question 3)
- Accepted evidence: textbook pages [38]; PDF pages [48]
- Required: Acid plus a suitable metal liberates hydrogen gas; Collect/lead the gas through the delivery tube; Bring a burning splint or match near the gas; A characteristic pop confirms hydrogen
- Optional: Write a representative acid + metal → salt + H₂ equation
- Unsupported: Hydrogen merely extinguishes the flame without burning
- Dependencies: formula=True, visual=False, table=False, multiple_passages=False
- Website answer: partially supported. The website identifies hydrogen and a pop but says the flame 'turns off', which is scientifically misleading.
- Verification: high; recommendation=accept

### GEN-PSC-006 — Acids, Bases and Salts

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-3-Acids-Bases-and-Salts&chpid=311 (question 2)
- Accepted evidence: textbook pages [50]; PDF pages [60]
- Required: Bacteria break down food/sugars and produce acids; Below about pH 5.5 the acidic medium attacks calcium-phosphate tooth enamel; Continued demineralisation leads to decay
- Optional: Basic toothpaste can help neutralise excess acid
- Unsupported: Tooth enamel dissolves because the mouth becomes strongly alkaline
- Dependencies: formula=False, visual=False, table=False, multiple_passages=False
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=accept

### GEN-PSC-007 — Refraction of Light at Curved Surfaces

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-4-Refraction-of-Light-at-Curved-Surfaces&chpid=312 (question 1)
- Accepted evidence: textbook pages [79, 80]; PDF pages [89, 90]
- Required: Measure/locate image or focal position for the lens in air; Immerse the lens in water without changing its shape; Repeat the observation and compare focal positions; Observe a larger focal length in water; Explain using the smaller relative refractive-index contrast in water
- Optional: Use the black-stone/cylindrical-vessel setup described in the textbook activity
- Unsupported: Immersion makes the lens material’s absolute refractive index zero
- Dependencies: formula=False, visual=False, table=False, multiple_passages=False
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=accept

### GEN-PSC-008 — Refraction of Light at Curved Surfaces

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-4-Refraction-of-Light-at-Curved-Surfaces&chpid=312 (question 4)
- Accepted evidence: textbook pages [80, 81]; PDF pages [90, 91]
- Required: State 1/f = (n − 1)(1/R₁ − 1/R₂) for a thin lens in air; Define f, n, R₁ and R₂; Preserve signs of the radii under the stated convention; Note that the surrounding medium changes the relative refractive index in the general form
- Optional: Relate curvature/refractive index to focal length
- Unsupported: Replace the minus between reciprocal radii with an unspecified symbol
- Dependencies: formula=True, visual=False, table=False, multiple_passages=False
- Website answer: formatting corrupted. The website formula contains question-mark glyphs where the textbook has minus signs and subscripts.
- Verification: high; recommendation=accept

### GEN-PSC-009 — Human Eye and Colourful World

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-5-Human-Eye-and-Colourful-World&chpid=313 (question 1)
- Accepted evidence: textbook pages [92, 93]; PDF pages [102, 103]
- Required: Myopia means distant objects are not focused clearly on the retina; The eye’s far point is finite and the uncorrected image forms before the retina; Use a concave/diverging lens; The lens makes parallel rays appear to come from the far point so the eye focuses them on the retina
- Optional: For far point D, the correcting lens has f = −D for an object at infinity
- Unsupported: Correct myopia with a converging convex lens
- Dependencies: formula=True, visual=True, table=False, multiple_passages=False
- Website answer: formatting corrupted. The source says 'eye detect' and flattens the lens formula; normalization restores the textbook question.
- Verification: high; recommendation=revise

### GEN-PSC-010 — Human Eye and Colourful World

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-5-Human-Eye-and-Colourful-World&chpid=313 (question 9)
- Accepted evidence: textbook pages [105, 106]; PDF pages [115, 116]
- Required: Sunlight is scattered by atmospheric molecules; Scattering depends on wavelength/frequency and scatterer size; Nitrogen and oxygen molecules preferentially scatter blue light toward observers; Without the atmosphere the sky would appear dark
- Optional: Distinguish scattering from dispersion by a prism
- Unsupported: The sky is blue mainly because it reflects ocean water
- Dependencies: formula=False, visual=False, table=False, multiple_passages=False
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=accept

### GEN-PSC-011 — Structure of Atom

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-6-Structure-of-Atom&chpid=314 (question 3)
- Accepted evidence: textbook pages [118, 119, 126]; PDF pages [128, 129, 136]
- Required: An orbital is a region of high probability of finding an electron; A Bohr orbit is a fixed path/energy shell with a defined radius; Orbitals do not have sharp classical paths and have characteristic shapes; A shell can contain 2n² electrons while one orbital holds at most two with opposite spins
- Optional: Relate orbitals to quantum numbers
- Unsupported: An orbital is a literal circular track followed by the electron
- Dependencies: formula=True, visual=False, table=False, multiple_passages=True
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=accept

### GEN-PSC-012 — Classification of Elements - The Periodic Table

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-7-Classification-of-Elements-The-Periodic-Table&chpid=315 (question 1)
- Accepted evidence: textbook pages [136, 142, 143]; PDF pages [146, 152, 153]
- Required: State the uncertain position of hydrogen; Explain anomalous atomic-mass ordering; Explain difficulty placing isotopes and separation/grouping anomalies; Modern classification uses atomic number rather than atomic mass; Atomic number/electronic configuration resolves isotope and ordering problems
- Optional: Give Ar/K or Te/I examples
- Unsupported: Mendeleev originally arranged elements by atomic number
- Dependencies: formula=False, visual=False, table=False, multiple_passages=True
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=revise

### GEN-PSC-013 — Chemical Bonding

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-8-Chemical-Bonding&chpid=316 (question 1)
- Accepted evidence: textbook pages [165, 166, 183]; PDF pages [180, 181, 198]
- Required: Show Na losing one electron and Cl gaining one to form Na⁺ and Cl⁻; Show Ca losing two electrons and O gaining two to form Ca²⁺ and O²⁻; Connect transfer to stable outer-shell configurations; Explain electrostatic attraction and the formulae NaCl and CaO
- Optional: Use Lewis electron-dot symbols/electronic configurations
- Unsupported: Describe NaCl or CaO as electron-sharing covalent molecules
- Dependencies: formula=True, visual=False, table=False, multiple_passages=True
- Website answer: formatting corrupted. The website answer loses several ionic charge signs and superscripts; the rendered textbook pages preserve them.
- Verification: high; recommendation=accept

### GEN-PSC-014 — Chemical Bonding

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-8-Chemical-Bonding&chpid=316 (question 6)
- Accepted evidence: textbook pages [180, 181]; PDF pages [195, 196]
- Required: Most covalent substances consist of neutral molecules; Intermolecular attractions are weaker than ionic lattice forces; Less heat is required to separate the molecules; Therefore many covalent compounds have lower melting/boiling points than ionic compounds
- Optional: Note network-covalent exceptions such as diamond/graphite
- Unsupported: Covalent bonds inside every molecule must break during ordinary melting
- Dependencies: formula=False, visual=False, table=False, multiple_passages=False
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=accept

### GEN-PSC-015 — Electric Current

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-9-Electric-Current&chpid=317 (question 1)
- Accepted evidence: textbook pages [193, 194]; PDF pages [208, 209]
- Required: State V ∝ I at constant temperature, so V/I = R; Connect ammeter in series and voltmeter across the conductor; Vary the number of cells/potential difference; Record paired V and I values in a table; Show V/I is constant or a straight-line V–I graph
- Optional: Name the textbook iron-spoke conductor and switch/key
- Unsupported: Connect the voltmeter in series; Claim Ohm’s law holds when temperature changes substantially
- Dependencies: formula=True, visual=False, table=True, multiple_passages=False
- Website answer: formatting corrupted. The website flattens V/I and substitutes a different conductor in one answer version; the textbook activity uses an iron spoke.
- Verification: high; recommendation=accept

### GEN-PSC-016 — Electric Current

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-9-Electric-Current&chpid=317 (question 6)
- Accepted evidence: textbook pages [202, 211, 214]; PDF pages [217, 226, 229]
- Required: Parallel branches receive the same supply potential difference; Each appliance draws current according to its resistance/power; Appliances can be switched independently; Failure/opening of one branch does not stop the others; In series, voltage is shared, total resistance rises, and all devices carry the same current
- Optional: Relate to household fuse/overload discussion
- Unsupported: A series connection lets every appliance receive full mains voltage independently
- Dependencies: formula=False, visual=False, table=False, multiple_passages=True
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=accept

### GEN-PSC-017 — Electromagnetism

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-10-Electromagnetism&chpid=318 (question 3)
- Accepted evidence: textbook pages [235]; PDF pages [250]
- Required: Connect a coil to a sensitive galvanometer; Move a bar magnet toward the coil and observe deflection; A stationary magnet gives no deflection; Moving the magnet away reverses deflection; Infer induced emf/current from a changing magnetic flux and state Faraday’s law
- Optional: Changing pole or speed changes direction/magnitude
- Unsupported: A stationary magnet always produces steady induced current
- Dependencies: formula=True, visual=False, table=False, multiple_passages=False
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=accept

### GEN-PSC-018 — Electromagnetism

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-10-Electromagnetism&chpid=318 (question 7)
- Accepted evidence: textbook pages [233]; PDF pages [248]
- Required: Place a current-carrying rectangular coil in a magnetic field; Opposite magnetic forces on the coil sides produce torque; Use the appropriate hand rule to give force directions; A split-ring commutator reverses current each half turn; Electrical energy is converted to mechanical rotation
- Optional: Label coil, field/magnets, brushes, split ring, and axle
- Unsupported: The commutator keeps current direction unchanged in the rotating coil
- Dependencies: formula=False, visual=True, table=False, multiple_passages=False
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=accept

### GEN-PSC-019 — Principles of Metallurgy

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-11-Principles-of-Metallurgy&chpid=319 (question 1)
- Accepted evidence: textbook pages [259]; PDF pages [274]
- Required: Use three clean nails in labelled test tubes; Expose one to both air and water; Exclude air with boiled water plus an oil layer in another; Exclude water with anhydrous calcium chloride in the third; Only the nail with both air and water rusts; Conclude both are necessary under the experiment’s conditions
- Optional: Cork the tubes and compare after several days
- Unsupported: Either completely dry air or deoxygenated water alone gives the same rusting
- Dependencies: formula=False, visual=False, table=False, multiple_passages=False
- Website answer: supported. Rendered PDF inspection corrects the processed metadata: PDF page 274 is printed textbook page 259 in Chapter 11, not processed page 264.
- Verification: high; recommendation=accept

### GEN-PSC-020 — Carbon and its Compounds

- Source: https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-12-Carbon-and-its-Compounds&chpid=320 (question 9)
- Accepted evidence: textbook pages [302, 303]; PDF pages [317, 318]
- Required: A soap molecule has a hydrophilic ionic/polar end and hydrophobic hydrocarbon tail; Tails embed in grease while heads remain in water; Agitation forms micelles around dirt; Like-charge repulsion keeps droplets suspended; The dirt-containing micelles are washed away
- Optional: Relate the explanation to the textbook oil-and-water test-tube activity
- Unsupported: Both ends of a soap molecule are equally attracted to oil
- Dependencies: formula=False, visual=False, table=False, multiple_passages=False
- Website answer: supported. No material conflict found.
- Verification: high; recommendation=accept
