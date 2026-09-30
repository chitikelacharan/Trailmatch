"""Clinical terminology: concepts, codes, synonyms, ambiguous abbreviations, lab units.

This is a compact, auditable dictionary. In production, back it with UMLS / SNOMED CT /
RxNorm / LOINC services; the engine only depends on the interfaces below.
"""
import re

# --------------------------------------------------------------------------- conditions
CONDITIONS = {
    "type2_diabetes": dict(
        display="Type 2 diabetes mellitus", icd10=["E11"], icd9_regex=r"^250\.\d[02]$",
        synonyms=["type 2 diabetes mellitus", "type 2 diabetes", "type ii diabetes",
                  "diabetes mellitus type 2", "diabetes mellitus type ii", "type 2 dm",
                  "type ii dm", "niddm", "adult-onset diabetes", "adult onset diabetes"],
        abbrs=["T2DM", "T2D", "DM2", "DMII"], generic=["diabetes mellitus", "diabetes"],
        ambiguous={}, conflicts_with=["type1_diabetes"]),
    "type1_diabetes": dict(
        display="Type 1 diabetes mellitus", icd10=["E10"], icd9_regex=r"^250\.\d[13]$",
        synonyms=["type 1 diabetes mellitus", "type 1 diabetes", "type i diabetes",
                  "diabetes mellitus type 1", "type 1 dm", "iddm", "juvenile diabetes"],
        abbrs=["T1DM", "T1D", "DM1"], generic=["diabetes mellitus", "diabetes"],
        ambiguous={}, conflicts_with=["type2_diabetes"]),
    "myocardial_infarction": dict(
        display="Myocardial infarction", icd10=["I21", "I22", "I25.2"], icd9_regex=r"^410\.",
        synonyms=["myocardial infarction", "heart attack", "stemi", "nstemi", "acute mi"],
        abbrs=[], generic=[],
        ambiguous={"MI": ["troponin", "stent", "cath", "stemi", "st elevation", "chest pain",
                          "ecg", "ekg", "pci", "infarct", "cardiac arrest", "heart attack"]},
        conflicts_with=[]),
    "heart_failure": dict(
        display="Heart failure", icd10=["I50"], icd9_regex=r"^428\.",
        synonyms=["heart failure", "congestive heart failure", "cardiac failure"],
        abbrs=["CHF", "HFrEF", "HFpEF"], generic=[], ambiguous={}, conflicts_with=[]),
    "pregnancy": dict(
        display="Pregnancy", icd10=["Z33", "O09", "O24", "Z3A"], icd9_regex=r"^V22\.",
        synonyms=["pregnant", "pregnancy", "gravid", "gestation"], abbrs=[], generic=[],
        ambiguous={}, conflicts_with=[]),
    "ckd": dict(
        display="Chronic kidney disease", icd10=["N18"], icd9_regex=r"^585\.",
        synonyms=["chronic kidney disease", "chronic renal failure", "chronic renal insufficiency"],
        abbrs=["CKD"], generic=[], ambiguous={}, conflicts_with=[]),
    "multiple_sclerosis": dict(
        display="Multiple sclerosis", icd10=["G35"], icd9_regex=r"^340$",
        synonyms=["multiple sclerosis"], abbrs=[], generic=[],
        ambiguous={"MS": ["demyelinat", "lesions", "optic neuritis", "relapsing", "interferon",
                          "mri brain", "neurolog"]}, conflicts_with=[]),
    "rheumatoid_arthritis": dict(
        display="Rheumatoid arthritis", icd10=["M05", "M06"], icd9_regex=r"^714\.0",
        synonyms=["rheumatoid arthritis"], abbrs=[], generic=[],
        ambiguous={"RA": ["joint", "methotrexate", "rheumatoid", "synovitis", "anti-ccp", "rf positive"]},
        conflicts_with=[]),
    "cirrhosis": dict(
        display="Cirrhosis", icd10=["K74"], icd9_regex=r"^571\.[25]",
        synonyms=["cirrhosis", "hepatic cirrhosis"], abbrs=[], generic=[], ambiguous={},
        conflicts_with=[]),
    "stroke": dict(
        display="Stroke", icd10=["I63"], icd9_regex=r"^43[34]\.",
        synonyms=["ischemic stroke", "cerebrovascular accident", "stroke"], abbrs=["CVA"],
        generic=[], ambiguous={}, conflicts_with=[]),
    "hypertension": dict(
        display="Hypertension", icd10=["I10", "I11", "I12", "I13", "I15"], icd9_regex=r"^401\.",
        synonyms=["hypertension", "high blood pressure"], abbrs=["HTN"], generic=[],
        ambiguous={}, conflicts_with=[]),
}

# --------------------------------------------------------------------------- medications
MEDICATIONS = {
    "metformin": dict(display="Metformin", synonyms=["metformin", "glucophage"], abbrs=[], generic=[], ambiguous={}),
    "insulin": dict(display="Insulin", synonyms=["insulin", "glargine", "lispro", "aspart", "detemir", "degludec"],
                    abbrs=[], generic=[], ambiguous={}),
    "sglt2_inhibitor": dict(display="SGLT2 inhibitor", synonyms=["empagliflozin", "dapagliflozin", "canagliflozin", "sglt2"],
                            abbrs=[], generic=[], ambiguous={}),
    "glp1_agonist": dict(display="GLP-1 agonist", synonyms=["semaglutide", "liraglutide", "dulaglutide", "glp-1"],
                         abbrs=[], generic=[], ambiguous={}),
    "systemic_steroid": dict(display="Systemic corticosteroid",
                             synonyms=["prednisone", "prednisolone", "methylprednisolone", "dexamethasone",
                                       "systemic corticosteroid", "systemic corticosteroids", "corticosteroids", "oral steroids"],
                             abbrs=[], generic=[], ambiguous={}),
    "warfarin": dict(display="Warfarin", synonyms=["warfarin", "coumadin"], abbrs=[], generic=[], ambiguous={}),
}

# --------------------------------------------------------------------------- labs
def _hba1c_from_mmol(v): return v / 10.929 + 2.15

LABS = {
    "hba1c": dict(display="HbA1c", names=["hemoglobin a1c", "glycated hemoglobin", "glycosylated hemoglobin", "hba1c", "a1c"],
                  loinc=["4548-4", "17856-6", "4549-2"], unit="%", plausible=(3.0, 20.0),
                  units={"%": lambda v: v, "mmol/mol": _hba1c_from_mmol}),
    "egfr": dict(display="eGFR", names=["estimated gfr", "egfr", "gfr"], loinc=["33914-3", "62238-1", "98979-8", "88293-6"],
                 unit="mL/min/1.73m2", plausible=(1.0, 200.0),
                 units={"ml/min/1.73m2": lambda v: v, "ml/min/1.73m²": lambda v: v, "ml/min": lambda v: v}),
    "creatinine": dict(display="Serum creatinine", names=["serum creatinine", "creatinine"], loinc=["2160-0"],
                       unit="mg/dL", plausible=(0.1, 20.0),
                       units={"mg/dl": lambda v: v, "umol/l": lambda v: v / 88.4, "µmol/l": lambda v: v / 88.4}),
    "alt": dict(display="ALT", names=["alanine aminotransferase", "sgpt", "alt"], loinc=["1742-6", "1743-4"],
                unit="U/L", plausible=(1.0, 5000.0), units={"u/l": lambda v: v, "iu/l": lambda v: v}),
    "bmi": dict(display="BMI", names=["body mass index", "bmi"], loinc=["39156-5"], unit="kg/m2", plausible=(10.0, 90.0),
                units={"kg/m2": lambda v: v, "kg/m²": lambda v: v}),
    "fasting_glucose": dict(display="Fasting glucose", names=["fasting plasma glucose", "fasting glucose", "fpg"],
                            loinc=["1558-6", "76629-5"], unit="mg/dL", plausible=(20.0, 1000.0),
                            units={"mg/dl": lambda v: v, "mmol/l": lambda v: v * 18.016}),
}

KNOWN_CODE_SYSTEMS = ("icd-10", "icd10", "icd-10-cm", "icd-9", "icd9", "icd-9-cm", "snomed")


def norm_unit(u):
    return re.sub(r"\s+", "", (u or "").lower())


def convert_lab(lab_key, value, unit):
    """Return (canonical_value, unit_assumed). Raises ValueError for unknown units."""
    spec = LABS[lab_key]
    if unit in (None, ""):
        return float(value), True
    fn = spec["units"].get(norm_unit(unit))
    if fn is None:
        raise ValueError(f"unknown unit '{unit}' for {spec['display']}")
    return float(fn(float(value))), False


def lab_matches(lab_key, lab):
    spec = LABS[lab_key]
    if lab.get("loinc") and lab["loinc"] in spec["loinc"]:
        return True
    name = (lab.get("name") or "").lower().strip()
    return any(name == n or re.search(rf"\b{re.escape(n)}\b", name) for n in spec["names"])


def code_concepts(code, system=None):
    """Map a structured code to condition concepts (handles ICD-10 and legacy ICD-9)."""
    if not code:
        return set()
    c = str(code).strip().upper()
    flat = c.replace(".", "")
    out = set()
    for key, spec in CONDITIONS.items():
        for pref in spec["icd10"]:
            if flat.startswith(pref.replace(".", "")) and not re.match(r"^\d", c):
                out.add(key)
        if re.match(spec["icd9_regex"], c):
            out.add(key)
    return out
