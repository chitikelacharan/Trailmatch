"""Generates synthetic, de-identified sample patients, a trial protocol and gold labels."""
import json, pathlib
OUT = pathlib.Path(__file__).resolve().parent.parent / "data"

def P(id, dob, sex, conditions, labs, meds, notes):
    return dict(id=id, demographics=dict(birth_date=dob, sex=sex), conditions=conditions, labs=labs,
                medications=meds, notes=[dict(id=f"{id}-N{i+1}", date=d, text=t) for i, (d, t) in enumerate(notes)])
C = lambda code, disp, onset, system="ICD-10-CM", status="active": dict(code=code, display=disp, onset=onset, system=system, status=status)
L = lambda name, v, u, date, loinc=None: dict(name=name, value=v, unit=u, date=date, loinc=loinc)
M = lambda name, start, end=None: dict(name=name, start=start, end=end)

patients = [
 P("P001", "1968-04-12", "female", [C("E11.9", "Type 2 diabetes mellitus", "2019-03-01"), C("I10", "Essential hypertension", "2015-06-01")],
   [L("HbA1c", 8.4, "%", "2026-08-10", "4548-4"), L("eGFR", 72, "mL/min/1.73m2", "2026-07-15", "33914-3")],
   [M("Metformin 1000 mg", "2019-04-01")],
   [("2026-08-10", "58F with T2DM well tolerating metformin. No history of myocardial infarction. Denies chest pain. HbA1c 8.4%.")]),
 P("P002", "1981-02-20", "male", [C("E11.65", "Type 2 diabetes mellitus with hyperglycemia", "2018-01-10"), C("I21.4", "NSTEMI", "2026-06-10")],
   [L("HbA1c", 8.0, "%", "2026-08-01", "4548-4"), L("eGFR", 80, "mL/min/1.73m2", "2026-08-01", "33914-3")],
   [M("Metformin 500 mg", "2018-02-01")],
   [("2026-06-12", "Admitted with NSTEMI, troponin elevated, underwent PCI with stent placement."), ("2026-08-01", "Follow-up. T2DM stable on metformin.")]),
 P("P003", "1963-09-30", "female", [C("E11.9", "Type 2 diabetes mellitus", "2016-05-05")],
   [L("HbA1c", 8.9, "%", "2025-11-01", "4548-4")], [M("Metformin", "2016-06-01")],
   [("2026-05-02", "Routine visit. Type 2 diabetes on metformin. Labs to be ordered.")]),
 P("P004", "1975-01-15", "male", [C("E11.9", "Type 2 diabetes mellitus", "2020-02-02")],
   [L("HbA1c", 8.1, "%", "2026-08-20", "4548-4"), L("eGFR", 90, "mL/min/1.73m2", "2026-08-20", "33914-3")], [M("Metformin", "2020-03-01")],
   [("2026-08-20", "Patient has type 1 diabetes, C-peptide undetectable, GAD antibodies positive. Chart lists E11 in error per endocrinology.")]),
 P("P005", "1972-07-07", "male", [C("E11.9", "Type 2 diabetes mellitus", "2017-04-04"), C("I10", "Hypertension", "2012-01-01")],
   [L("HbA1c", 7.6, "%", "2026-09-02", "4548-4"), L("eGFR", 65, "mL/min/1.73m2", "2026-08-30", "33914-3")], [M("Metformin", "2017-05-01")],
   [("2026-09-02", "Father had type 2 diabetes. Mother had heart failure. No history of myocardial infarction. Patient is not pregnant. Denies heart failure.")]),
 P("P006", "1959-11-11", "female", [C("E11.9", "Type 2 diabetes mellitus", "2014-08-08")],
   [L("HbA1c", 9.0, "%", "2026-08-15", "4548-4"), L("eGFR", 60, "mL/min/1.73m2", "2026-08-15", "33914-3")], [M("Metformin", "2014-09-01")],
   [("2026-08-15", "Echo shows moderate MI with LA enlargement; valve repair planned. T2DM on metformin.")]),
 P("P007", "1957-03-03", "female", [C("250.00", "Diabetes mellitus without complication", "2010-01-01", "ICD-9-CM"),
                                   C("DM2-LEG", "Diabetes mellitus type II", "2010-01-01", "LOCAL")],
   [L("HbA1c", 64, "mmol/mol", "2026-08-05", "4548-4"), L("eGFR", 55, "mL/min/1.73m2", "2026-08-05", "33914-3")], [M("Glucophage 850 mg", "2010-02-01")],
   [("2026-08-05", "Long-standing diabetes mellitus type II managed with Glucophage.")]),
 P("P008", "1994-05-05", "female", [C("E11.9", "Type 2 diabetes mellitus", "2021-01-01"), C("Z33.1", "Pregnant state, incidental", "2026-06-01")],
   [L("HbA1c", 7.5, "%", "2026-08-01", "4548-4"), L("eGFR", 100, "mL/min/1.73m2", "2026-08-01", "33914-3")], [M("Metformin", "2021-02-01")],
   [("2026-08-01", "Currently 14 weeks pregnant. T2DM on metformin.")]),
 P("P009", "2010-06-06", "male", [C("E11.9", "Type 2 diabetes mellitus", "2024-01-01")],
   [L("HbA1c", 8.0, "%", "2026-08-01", "4548-4"), L("eGFR", 110, "mL/min/1.73m2", "2026-08-01", "33914-3")], [M("Metformin", "2024-02-01")],
   [("2026-08-01", "16-year-old with T2DM on metformin.")]),
 P("P010", "1960-08-08", "male", [C("E11.9", "Type 2 diabetes mellitus", "2015-01-01")],
   [L("HbA1c", 8.3, "%", "2026-08-12", "4548-4"), L("eGFR", 38, "mL/min/1.73m2", "2026-08-12", "33914-3")], [M("Metformin", "2015-02-01")],
   [("2026-08-12", "T2DM and CKD. eGFR 38. SSN 123-45-6789 on file. Call 555-123-4567 for follow-up. Mr. Rajesh Kumar attended.")]),
 P("P011", "1970-10-10", "female", [],
   [L("HbA1c", 8.8, "%", "2026-08-25", "4548-4"), L("eGFR", 70, "mL/min/1.73m2", "2026-08-25", "33914-3")], [M("Metformin", "2025-11-01")],
   [("2023-03-01", "Screening visit. Patient denies diabetes. Fasting labs normal."),
    ("2026-01-20", "Newly diagnosed type 2 diabetes mellitus, started metformin.")]),
 P("P012", "1966-12-12", "male", [C("E11.9", "Type 2 diabetes mellitus", "2018-01-01")],
   [L("HbA1c", 6.1, "%", "2026-08-10", "4548-4"), L("HbA1c", 9.4, "%", "2026-08-10", "4548-4"), L("eGFR", 75, "mL/min/1.73m2", "2026-08-10", "33914-3")],
   [M("Metformin", "2018-02-01")], [("2026-08-10", "T2DM on metformin. Two HbA1c results filed same day.")]),
]

trial = dict(id="DIAB-201", title="Phase II study of an SGLT2/GLP-1 combination in Type 2 Diabetes", criteria_text="""Inclusion Criteria:
1. Age between 18 and 75 years
2. Diagnosis of type 2 diabetes mellitus
3. HbA1c between 7.0 and 10.5 % within 90 days
4. Currently taking metformin
5. eGFR >= 45 within 180 days
6. Willing and able to provide informed consent
Exclusion Criteria:
1. Type 1 diabetes
2. Myocardial infarction within 180 days
3. Pregnancy
4. Heart failure
5. Systemic corticosteroids within 30 days
""")

gold = {
 "P001": dict(decision="ELIGIBLE", missing=[]),
 "P002": dict(decision="INELIGIBLE", missing=[], states={"E2": "TRUE"}),
 "P003": dict(decision="NEEDS_REVIEW", missing=["I3", "I5"]),
 "P004": dict(decision="NEEDS_REVIEW", missing=["I2", "E1"], states={"I2": "CONFLICT", "E1": "CONFLICT"}),
 "P005": dict(decision="ELIGIBLE", missing=[], states={"E2": "FALSE", "E4": "FALSE"}),
 "P006": dict(decision="NEEDS_REVIEW", missing=["E2"], states={"E2": "UNKNOWN"}),
 "P007": dict(decision="ELIGIBLE", missing=[], states={"I2": "TRUE", "I3": "TRUE"}),
 "P008": dict(decision="INELIGIBLE", missing=[], states={"E3": "TRUE"}),
 "P009": dict(decision="INELIGIBLE", missing=[], states={"I1": "FALSE"}),
 "P010": dict(decision="INELIGIBLE", missing=[], states={"I5": "FALSE"}),
 "P011": dict(decision="ELIGIBLE", missing=[], states={"I2": "TRUE"}),
 "P012": dict(decision="NEEDS_REVIEW", missing=["I3"], states={"I3": "CONFLICT"}),
}
if __name__ == "__main__":
    (OUT / "sample_patients.json").write_text(json.dumps(patients, indent=1))
    (OUT / "sample_trial.json").write_text(json.dumps(trial, indent=1))
    (OUT / "gold_labels.json").write_text(json.dumps(dict(trial_id="DIAB-201", as_of="2026-09-30", labels=gold), indent=1))
    import shutil; [shutil.copy(OUT / f, OUT.parent / "static" / f) for f in ("sample_patients.json", "sample_trial.json")]; print("wrote", len(patients), "patients")
