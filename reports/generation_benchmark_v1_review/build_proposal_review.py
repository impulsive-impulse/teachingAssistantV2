"""Build the temporary, approval-gated 40-question generation proposal."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


HERE = Path(__file__).parent
RAW = HERE / "manabadi_raw_candidates.jsonl"


def spec(qid, book, chapter, needle, normalized, qtype, difficulty, tpages, ppages,
         required, *, optional=None, prohibited=None, formula=False, visual=False,
         table=False, multi=False, depth="medium", status="supported", notes="",
         confidence="high", recommendation="accept"):
    return locals()


SPECS = [
    spec("GEN-BIO-001", "biology", 1, "laboratory to study the presence of starch", None,
         "experiment_based", "medium", [3, 4], [12, 13],
         ["Use a sun-exposed leaf and boil it in water", "Remove chlorophyll using alcohol in a water bath", "Add iodine solution", "A blue-black colour shows starch"],
         optional=["State the safety precaution not to heat alcohol directly"], prohibited=["Iodine produces starch rather than merely testing for it"], multi=True),
    spec("GEN-BIO-002", "biology", 1, "How are fats digested", None,
         "process_explanation", "easy", [16, 17], [25, 26],
         ["Bile emulsifies fats into small globules", "Pancreatic lipase acts on fats", "Digestion is completed in the small intestine", "End products include fatty acids and glycerol"],
         optional=["The intestinal medium becomes alkaline"], prohibited=["Fats are completely digested in the stomach"], multi=True),
    spec("GEN-BIO-003", "biology", 2, "How are alveoli designed", None,
         "structure_function", "easy", [30, 31], [39, 40],
         ["Alveoli are extremely numerous microscopic air sacs", "Their folding/number gives an enormous moist surface area", "They are closely associated with blood capillaries", "These features support rapid gas exchange by diffusion"],
         optional=["The textbook estimates a total area near 160 m²"], prohibited=["Gas exchange occurs only in bronchi"], multi=True),
    spec("GEN-BIO-004", "biology", 2, "procedure do you follow to understand anaerobic respiration", None,
         "experiment_based", "hard", [40, 41], [49, 50],
         ["Use yeast supplied with glucose solution", "Remove/exclude oxygen and prevent its re-entry", "Maintain an experimental setup and an appropriate comparison", "Detect carbon dioxide and/or a temperature rise", "Infer that yeast releases energy and CO₂ without oxygen"],
         optional=["Liquid paraffin excludes air; bicarbonate indicator detects CO₂"], prohibited=["Oxygen must be continuously bubbled through the anaerobic setup"], multi=True, depth="detailed"),
    spec("GEN-BIO-005", "biology", 3, "What is double circulation? Why is it important", None,
         "process_explanation", "medium", [58, 63, 64], [67, 72, 73],
         ["Blood passes through the heart twice in one complete circulation", "Describe the pulmonary circuit", "Describe the systemic circuit", "Explain efficient separation/delivery of oxygenated and deoxygenated blood"],
         optional=["Trace the named heart chambers and major vessels"], prohibited=["Humans have single circulation"], multi=True, depth="detailed"),
    spec("GEN-BIO-006", "biology", 3, "Differentiate between arteries and veins", None,
         "comparison", "medium", [60, 61], [69, 70],
         ["Arteries carry blood away from the heart; veins carry it toward the heart", "Arteries have thicker, more elastic muscular walls", "Veins have thinner walls, wider lumen, and valves", "State pulmonary-vessel exceptions if oxygenation is discussed"],
         optional=["Relate wall structure to pressure"], prohibited=["All arteries always carry oxygenated blood", "Veins contain blue blood"], table=True, multi=True,
         status="partially supported", notes="The website correctly contrasts direction and structure but misleadingly labels veins blue and overgeneralizes oxygenation."),
    spec("GEN-BIO-007", "biology", 4, "Explain the process of formation of urine", None,
         "process_explanation", "hard", [84, 85, 86], [93, 94, 95],
         ["Define excretion as removal of metabolic wastes", "Explain glomerular filtration", "Explain selective tubular reabsorption", "Explain tubular secretion", "Explain concentration of urine/water reabsorption"],
         optional=["Mention roles of Bowman’s capsule, loop of Henle, collecting duct, and ADH"], prohibited=["Useful glucose and amino acids are normally all excreted"], visual=True, multi=True, depth="detailed"),
    spec("GEN-BIO-008", "biology", 4, "Why do some people need to use a dialysis machine", None,
         "structure_function", "medium", [88, 89], [97, 98],
         ["Dialysis is needed when both kidneys cannot adequately filter wastes", "Blood is withdrawn and mixed with anticoagulant", "Blood flows through a semipermeable membrane against dialysis fluid", "Nitrogenous wastes diffuse out while cells/proteins are retained", "Cleaned blood is returned"],
         optional=["Dialysis fluid resembles plasma but lacks nitrogenous waste"], prohibited=["Dialysis permanently cures kidney failure"], multi=True, depth="detailed"),
    spec("GEN-BIO-009", "biology", 5, "How does phototropism occur", None,
         "cause_effect", "medium", [118, 119], [127, 128],
         ["Phototropism is directional growth in response to light", "The shoot tip perceives lateral light", "Auxin influence is redistributed to the shaded side", "Greater elongation on the shaded side bends the shoot toward light"],
         optional=["Reference Darwin/Went coleoptile experiments"], prohibited=["Light destroys every auxin molecule on the lit side"], multi=True,
         status="partially supported", notes="The website identifies auxin and bending but omits the textbook’s asymmetric-growth mechanism."),
    spec("GEN-BIO-010", "biology", 5, "What is a Synapse?", "What is a synapse, and how does it transfer information?",
         "structure_function", "easy", [103], [112],
         ["A synapse is the functional contact region between two neurons", "The neurons are separated by a minute gap without protoplasmic continuity", "Signals cross chemically, electrically, or both"],
         optional=["Synapses are common in the brain and spinal cord"], prohibited=["The cytoplasm of the two neurons is continuous"], recommendation="revise"),
    spec("GEN-BIO-011", "biology", 6, "Why do fish and frog produce a huge number of eggs", None,
         "cause_effect", "easy", [130, 131], [139, 140],
         ["Fertilisation is external in water", "Eggs and sperm are exposed to currents and predators", "The chance of any one gamete/egg surviving and being fertilised is low", "Large numbers compensate for high loss"],
         optional=["No parental protection is available for many eggs"], prohibited=["Every released egg is fertilised"], multi=True),
    spec("GEN-BIO-012", "biology", 6, "differences between mitosis and meiosis", None,
         "comparison", "hard", [142, 143, 144, 145], [151, 152, 153, 154],
         ["Mitosis has one division; meiosis has two", "Mitosis forms two daughter cells; meiosis forms four", "Mitosis preserves chromosome number; meiosis halves it", "Mitosis supports growth/repair; meiosis forms gametes", "Meiosis creates variation through recombination/segregation"],
         optional=["Compare prophase events and homologous chromosomes"], prohibited=["Meiosis produces genetically identical diploid cells"], table=True, multi=True, depth="detailed",
         status="formatting corrupted", notes="The website’s answer block is missing, but the question is intact and the textbook table is authoritative."),
    spec("GEN-BIO-013", "biology", 7, "How does mucus help in passage of food", None,
         "structure_function", "easy", [162, 163], [171, 172],
         ["Oesophageal walls secrete mucus", "Mucus lubricates and protects the wall", "The bolus slides down more easily during peristalsis"],
         optional=["Saliva also aids movement"], prohibited=["Mucus digests proteins"], multi=True),
    spec("GEN-BIO-014", "biology", 7, "acid and leaf experiment", "Describe the acid-and-leaf experiment used to model how the stomach is protected from its own acid, and compare the observations with the stomach’s mucus lining.",
         "experiment_based", "medium", [166], [175],
         ["Use two similar green leaves", "Coat one with petroleum jelly/grease and leave one uncoated", "Add equal drops of weak acid and observe", "The uncoated leaf is affected while the coated leaf is protected", "Petroleum jelly models the protective mucus lining of the stomach"],
         optional=["Observe after about half an hour"], prohibited=["Mucus neutralises all stomach acid completely"], recommendation="revise",
         status="formatting corrupted", notes="The source wording contains a corrupted 'iii human' phrase; normalization restores the textbook meaning."),
    spec("GEN-BIO-015", "biology", 8, "monohybrid experiment with an example", "Explain Mendel’s monohybrid experiment with an example. Which law of inheritance does it demonstrate?",
         "experiment_based", "hard", [180, 182, 183, 184, 186], [189, 191, 192, 193, 195],
         ["Cross pure parents differing in one trait", "F₁ shows only the dominant trait", "Self the F₁ heterozygotes", "F₂ phenotype ratio is about 3:1 and genotype ratio 1:2:1", "Relate results to dominance and segregation"],
         optional=["Use Y/y or another textbook trait and a checkerboard"], prohibited=["Recessive factors disappear permanently in F₁"], visual=True, multi=True, depth="detailed", recommendation="revise"),
    spec("GEN-BIO-016", "biology", 8, "How does sex determination take place in human", "How does sex determination take place in humans?",
         "process_explanation", "medium", [188, 189], [197, 198],
         ["Females are XX and males are XY", "Ova carry only X", "Sperm carry either X or Y", "X-bearing sperm plus X ovum gives XX; Y-bearing sperm plus X ovum gives XY", "The fertilising sperm determines chromosomal sex"],
         optional=["Expected probability is approximately equal for XX and XY"], prohibited=["The mother’s ovum can carry Y"], visual=True, multi=True, recommendation="revise"),
    spec("GEN-BIO-017", "biology", 9, "amount of energy transferred from one step", None,
         "cause_effect", "medium", [211, 212], [220, 221],
         ["Available energy decreases at each trophic transfer", "Only a small fraction becomes new biomass", "Energy is lost through respiration, activity, heat, and undigested material", "This limits food-chain length"],
         optional=["Many animals convert no more than about 10% of food into body tissue"], prohibited=["Energy increases toward the top trophic level"], visual=True, multi=True),
    spec("GEN-BIO-018", "biology", 9, "toxic material affecting the ecosystem", "How does the use of toxic materials affect an ecosystem? Explain bioaccumulation and biomagnification.",
         "multi_point_explanation", "hard", [216, 217], [225, 226],
         ["Persistent toxic substances enter organisms/food chains", "Bioaccumulation is pollutant build-up in an organism or entry into a food chain", "Biomagnification is increasing concentration across trophic levels", "Top consumers can receive harmful concentrations", "Toxins can disrupt food chains and ecosystem balance"],
         optional=["Give pesticides or heavy metals as examples"], prohibited=["Biodegradable pollutants always biomagnify indefinitely"], multi=True, depth="detailed", recommendation="revise"),
    spec("GEN-BIO-019", "biology", 10, "What is sustainable development? How is it useful", None,
         "multi_point_explanation", "medium", [236], [245],
         ["Define sustainable development as using the environment while retaining resources for the future", "Connect development with conservation", "Explain management/conservation of renewable and non-renewable resources"],
         optional=["Give a local water, forest, soil, or energy example"], prohibited=["Sustainability means prohibiting all resource use"],
         status="partially supported", notes="The website’s core definition is supported, but some added claims are broader than the cited textbook passage."),
    spec("GEN-BIO-020", "biology", 10, "Why is it important to recharge the ground water", None,
         "cause_effect", "medium", [230, 232, 234], [239, 241, 243],
         ["Groundwater is heavily used and can be depleted by over-extraction", "Recharge stores rainwater underground and revives dried wells", "Recharge supports irrigation and future water availability", "Name textbook measures such as dykes/barriers, percolation/storage structures, or field bunds"],
         optional=["Relate recharge to the Wanaparthy/Vaddicherla or Kothapally case"], prohibited=["Groundwater is unlimited because it is renewable"], multi=True, depth="detailed",
         status="partially supported", notes="The website supports the need for recharge but adds statistics and consequences not all present in the accepted passages."),

    spec("GEN-PSC-001", "physical_sciences", 1, "convex mirror as a rear-view mirror", None,
         "cause_effect", "easy", [13, 20], [23, 30],
         ["A convex mirror forms a virtual, erect, diminished image", "It provides a wider field of view", "Therefore a driver can see a larger region behind the vehicle"],
         optional=["Image properties hold for different object positions"], prohibited=["A convex rear-view mirror forms a real image on a screen"], visual=True, multi=True),
    spec("GEN-PSC-002", "physical_sciences", 1, "Find the distance of the image", None,
         "formula_numerical", "hard", [18, 19], [28, 29],
         ["Use f = R/2 = -4 cm and u = -10 cm under the textbook sign convention", "Apply 1/f = 1/v + 1/u", "Obtain v = -20/3 cm ≈ -6.67 cm", "Interpret the negative sign as a real image on the object side"],
         optional=["The image is inverted and diminished between F and C"], prohibited=["Report v as +6.7 cm while also calling it a real same-side image"], formula=True, visual=True, multi=True, depth="detailed",
         status="contradicted", notes="The website gives +6.7 cm; the textbook sign convention and mirror formula give v ≈ -6.67 cm."),
    spec("GEN-PSC-003", "physical_sciences", 2, "information do you get from a balanced chemical equation", None,
         "multi_point_explanation", "medium", [25, 29, 34], [35, 39, 44],
         ["Identify reactants and products by symbols/formulae", "Give stoichiometric ratios of particles/moles", "Relate coefficients to relative quantities/masses", "Include physical states and reaction conditions when written", "Explain that gas volumes/heat information may be conveyed when specified"],
         optional=["Use an example equation"], prohibited=["A balanced equation alone always gives reaction rate or mechanism"], formula=True, multi=True, depth="detailed"),
    spec("GEN-PSC-004", "physical_sciences", 2, "Why should we balance a chemical equation", None,
         "cause_effect", "easy", [25], [35],
         ["Chemical reactions obey conservation of mass", "Atoms are rearranged rather than created or destroyed", "The count of each element must be equal on both sides", "Balancing changes coefficients, not chemical formulae"],
         optional=["Use a simple equation as illustration"], prohibited=["Balance by changing subscripts in compounds"], formula=True),
    spec("GEN-PSC-005", "physical_sciences", 3, "Which gas is usually liberated when an acid reacts with a metal", None,
         "experiment_based", "easy", [38], [48],
         ["Acid plus a suitable metal liberates hydrogen gas", "Collect/lead the gas through the delivery tube", "Bring a burning splint or match near the gas", "A characteristic pop confirms hydrogen"],
         optional=["Write a representative acid + metal → salt + H₂ equation"], prohibited=["Hydrogen merely extinguishes the flame without burning"], formula=True,
         status="partially supported", notes="The website identifies hydrogen and a pop but says the flame 'turns off', which is scientifically misleading."),
    spec("GEN-PSC-006", "physical_sciences", 3, "tooth decay start when the pH of mouth is lower than 5.5", None,
         "cause_effect", "easy", [50], [60],
         ["Bacteria break down food/sugars and produce acids", "Below about pH 5.5 the acidic medium attacks calcium-phosphate tooth enamel", "Continued demineralisation leads to decay"],
         optional=["Basic toothpaste can help neutralise excess acid"], prohibited=["Tooth enamel dissolves because the mouth becomes strongly alkaline" ]),
    spec("GEN-PSC-007", "physical_sciences", 4, "focal length of a convex lens is increased when it is kept in water", None,
         "experiment_based", "hard", [79, 80], [89, 90],
         ["Measure/locate image or focal position for the lens in air", "Immerse the lens in water without changing its shape", "Repeat the observation and compare focal positions", "Observe a larger focal length in water", "Explain using the smaller relative refractive-index contrast in water"],
         optional=["Use the black-stone/cylindrical-vessel setup described in the textbook activity"], prohibited=["Immersion makes the lens material’s absolute refractive index zero"], visual=True, multi=True, depth="detailed"),
    spec("GEN-PSC-008", "physical_sciences", 4, "lens maker’s formula", None,
         "formula_explanation", "hard", [80, 81], [90, 91],
         ["State 1/f = (n − 1)(1/R₁ − 1/R₂) for a thin lens in air", "Define f, n, R₁ and R₂", "Preserve signs of the radii under the stated convention", "Note that the surrounding medium changes the relative refractive index in the general form"],
         optional=["Relate curvature/refractive index to focal length"], prohibited=["Replace the minus between reciprocal radii with an unspecified symbol"], formula=True, visual=True, multi=True,
         status="formatting corrupted", notes="The website formula contains question-mark glyphs where the textbook has minus signs and subscripts."),
    spec("GEN-PSC-009", "physical_sciences", 5, "correct the eye detect Myopia", "How is myopia corrected? Explain with a ray diagram.",
         "visual_explanation", "medium", [92, 93], [102, 103],
         ["Myopia means distant objects are not focused clearly on the retina", "The eye’s far point is finite and the uncorrected image forms before the retina", "Use a concave/diverging lens", "The lens makes parallel rays appear to come from the far point so the eye focuses them on the retina"],
         optional=["For far point D, the correcting lens has f = −D for an object at infinity"], prohibited=["Correct myopia with a converging convex lens"], formula=True, visual=True, multi=True, recommendation="revise",
         status="formatting corrupted", notes="The source says 'eye detect' and flattens the lens formula; normalization restores the textbook question."),
    spec("GEN-PSC-010", "physical_sciences", 5, "reason for the blue colour of the sky", None,
         "cause_effect", "medium", [105, 106], [115, 116],
         ["Sunlight is scattered by atmospheric molecules", "Scattering depends on wavelength/frequency and scatterer size", "Nitrogen and oxygen molecules preferentially scatter blue light toward observers", "Without the atmosphere the sky would appear dark"],
         optional=["Distinguish scattering from dispersion by a prism"], prohibited=["The sky is blue mainly because it reflects ocean water"], multi=True),
    spec("GEN-PSC-011", "physical_sciences", 6, "What is an orbital? How is it different from Bohr", None,
         "comparison", "medium", [118, 119, 126], [128, 129, 136],
         ["An orbital is a region of high probability of finding an electron", "A Bohr orbit is a fixed path/energy shell with a defined radius", "Orbitals do not have sharp classical paths and have characteristic shapes", "A shell can contain 2n² electrons while one orbital holds at most two with opposite spins"],
         optional=["Relate orbitals to quantum numbers"], prohibited=["An orbital is a literal circular track followed by the electron"], formula=True, multi=True),
    spec("GEN-PSC-012", "physical_sciences", 7, "limitations of Mendeleeff", "What are the limitations of Mendeleev’s periodic table, and how does the modern periodic table address them?",
         "comparison", "hard", [136, 142, 143], [146, 152, 153],
         ["State the uncertain position of hydrogen", "Explain anomalous atomic-mass ordering", "Explain difficulty placing isotopes and separation/grouping anomalies", "Modern classification uses atomic number rather than atomic mass", "Atomic number/electronic configuration resolves isotope and ordering problems"],
         optional=["Give Ar/K or Te/I examples"], prohibited=["Mendeleev originally arranged elements by atomic number"], multi=True, depth="detailed", recommendation="revise"),
    spec("GEN-PSC-013", "physical_sciences", 8, "formation of sodium chloride and calcium oxide", None,
         "process_explanation", "hard", [165, 166, 183], [180, 181, 198],
         ["Show Na losing one electron and Cl gaining one to form Na⁺ and Cl⁻", "Show Ca losing two electrons and O gaining two to form Ca²⁺ and O²⁻", "Connect transfer to stable outer-shell configurations", "Explain electrostatic attraction and the formulae NaCl and CaO"],
         optional=["Use Lewis electron-dot symbols/electronic configurations"], prohibited=["Describe NaCl or CaO as electron-sharing covalent molecules"], formula=True, visual=True, multi=True, depth="detailed",
         status="formatting corrupted", notes="The website answer loses several ionic charge signs and superscripts; the rendered textbook pages preserve them."),
    spec("GEN-PSC-014", "physical_sciences", 8, "low melting points for covalent compounds", None,
         "comparison", "medium", [180, 181], [195, 196],
         ["Most covalent substances consist of neutral molecules", "Intermolecular attractions are weaker than ionic lattice forces", "Less heat is required to separate the molecules", "Therefore many covalent compounds have lower melting/boiling points than ionic compounds"],
         optional=["Note network-covalent exceptions such as diamond/graphite"], prohibited=["Covalent bonds inside every molecule must break during ordinary melting"], table=True, multi=True),
    spec("GEN-PSC-015", "physical_sciences", 9, "State Ohm’s law. Suggest an experiment", None,
         "experiment_based", "hard", [193, 194], [208, 209],
         ["State V ∝ I at constant temperature, so V/I = R", "Connect ammeter in series and voltmeter across the conductor", "Vary the number of cells/potential difference", "Record paired V and I values in a table", "Show V/I is constant or a straight-line V–I graph"],
         optional=["Name the textbook iron-spoke conductor and switch/key"], prohibited=["Connect the voltmeter in series", "Claim Ohm’s law holds when temperature changes substantially"], formula=True, table=True, visual=True, multi=True, depth="detailed",
         status="formatting corrupted", notes="The website flattens V/I and substitutes a different conductor in one answer version; the textbook activity uses an iron spoke."),
    spec("GEN-PSC-016", "physical_sciences", 9, "connect electric appliances in parallel", None,
         "cause_effect", "medium", [202, 211, 214], [217, 226, 229],
         ["Parallel branches receive the same supply potential difference", "Each appliance draws current according to its resistance/power", "Appliances can be switched independently", "Failure/opening of one branch does not stop the others", "In series, voltage is shared, total resistance rises, and all devices carry the same current"],
         optional=["Relate to household fuse/overload discussion"], prohibited=["A series connection lets every appliance receive full mains voltage independently"], visual=True, multi=True, depth="detailed"),
    spec("GEN-PSC-017", "physical_sciences", 10, "Faraday’s law of induction with the help of activity", None,
         "experiment_based", "hard", [235], [250],
         ["Connect a coil to a sensitive galvanometer", "Move a bar magnet toward the coil and observe deflection", "A stationary magnet gives no deflection", "Moving the magnet away reverses deflection", "Infer induced emf/current from a changing magnetic flux and state Faraday’s law"],
         optional=["Changing pole or speed changes direction/magnitude"], prohibited=["A stationary magnet always produces steady induced current"], formula=True, visual=True, depth="detailed"),
    spec("GEN-PSC-018", "physical_sciences", 10, "working of an electric motor", None,
         "visual_explanation", "hard", [233], [248],
         ["Place a current-carrying rectangular coil in a magnetic field", "Opposite magnetic forces on the coil sides produce torque", "Use the appropriate hand rule to give force directions", "A split-ring commutator reverses current each half turn", "Electrical energy is converted to mechanical rotation"],
         optional=["Label coil, field/magnets, brushes, split ring, and axle"], prohibited=["The commutator keeps current direction unchanged in the rotating coil"], visual=True, depth="detailed"),
    spec("GEN-PSC-019", "physical_sciences", 11, "presence of air and water are essential for corrosion", None,
         "experiment_based", "medium", [259], [274],
         ["Use three clean nails in labelled test tubes", "Expose one to both air and water", "Exclude air with boiled water plus an oil layer in another", "Exclude water with anhydrous calcium chloride in the third", "Only the nail with both air and water rusts", "Conclude both are necessary under the experiment’s conditions"],
         optional=["Cork the tubes and compare after several days"], prohibited=["Either completely dry air or deoxygenated water alone gives the same rusting"], visual=True, depth="detailed",
         notes="Rendered PDF inspection corrects the processed metadata: PDF page 274 is printed textbook page 259 in Chapter 11, not processed page 264."),
    spec("GEN-PSC-020", "physical_sciences", 12, "cleansing action of soap", None,
         "visual_explanation", "medium", [302, 303], [317, 318],
         ["A soap molecule has a hydrophilic ionic/polar end and hydrophobic hydrocarbon tail", "Tails embed in grease while heads remain in water", "Agitation forms micelles around dirt", "Like-charge repulsion keeps droplets suspended", "The dirt-containing micelles are washed away"],
         optional=["Relate the explanation to the textbook oil-and-water test-tube activity"], prohibited=["Both ends of a soap molecule are equally attracted to oil"], visual=True, multi=True, depth="detailed"),
]

VISUAL_REQUIRED = {"GEN-PSC-009", "GEN-PSC-018"}
TABLE_REQUIRED = {"GEN-PSC-015"}
MULTI_PASSAGE_REQUIRED = {
    "GEN-BIO-005", "GEN-BIO-007", "GEN-BIO-012", "GEN-BIO-015",
    "GEN-BIO-018", "GEN-BIO-020", "GEN-PSC-003", "GEN-PSC-011",
    "GEN-PSC-012", "GEN-PSC-013", "GEN-PSC-016",
}


def select_source(rows, item):
    matches = [row for row in rows if row["book_id"] == item["book"] and
               row["chapter_number"] == item["chapter"] and
               item["needle"].lower() in row["original_source_question"].lower()]
    if not matches:
        raise ValueError(f"No source match for {item['qid']}: {item['needle']}")
    return matches[0]


def main() -> None:
    rows = [json.loads(line) for line in RAW.read_text(encoding="utf-8").splitlines()]
    proposal = []
    for item in SPECS:
        source = select_source(rows, item)
        normalized = item["normalized"] or source["original_source_question"]
        proposal.append({
            "question_id": item["qid"], "book_id": item["book"],
            "chapter_id": f"{item['book']}-ch{item['chapter']:02d}",
            "chapter_number": item["chapter"], "chapter_title": source["chapter_title"],
            "original_source_question": source["original_source_question"],
            "normalized_question": normalized, "source_name": "Manabadi",
            "source_url": source["source_url"],
            "source_question_number": source["source_question_number"],
            "question_type": item["qtype"], "difficulty": item["difficulty"],
            "required_answer_points": item["required"],
            "optional_answer_points": item["optional"] or [],
            "prohibited_or_unsupported_claims": item["prohibited"] or [],
            "accepted_textbook_pages": item["tpages"], "accepted_pdf_pages": item["ppages"],
            "requires_formula": item["formula"], "requires_visual": item["qid"] in VISUAL_REQUIRED,
            "requires_table": item["qid"] in TABLE_REQUIRED,
            "requires_multiple_passages": item["qid"] in MULTI_PASSAGE_REQUIRED,
            "expected_answer_depth": item["depth"], "website_answer_status": item["status"],
            "website_answer_notes": item["notes"], "verification_confidence": item["confidence"],
            "recommendation": item["recommendation"], "reviewer_status": "proposed_pending_approval",
            "benchmark_version": "generation_benchmark_v1_proposal",
        })
    out = HERE / "proposed_40_questions.jsonl"
    out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in proposal), encoding="utf-8", newline="\n")

    by_book = Counter(row["book_id"] for row in proposal)
    by_chapter = Counter((row["book_id"], row["chapter_number"]) for row in proposal)
    by_type = Counter(row["question_type"] for row in proposal)
    by_difficulty = Counter(row["difficulty"] for row in proposal)
    dependencies = {key: sum(bool(row[key]) for row in proposal) for key in
                    ("requires_formula", "requires_visual", "requires_table", "requires_multiple_passages")}
    summary = {
        "total": len(proposal), "by_book": by_book, "by_chapter": {f"{b}:{c}": n for (b, c), n in by_chapter.items()},
        "by_type": by_type, "by_difficulty": by_difficulty, "dependencies": dependencies,
        "website_status": Counter(row["website_answer_status"] for row in proposal),
        "recommendations": Counter(row["recommendation"] for row in proposal),
    }
    (HERE / "proposal_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
