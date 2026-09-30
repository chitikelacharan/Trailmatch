# UI Wireframes (implemented in `static/index.html`)

## 1. Sign-in
```
+----------------------------------+
|  Sign in                         |
|  [username        ] [password  ] |
|  [ Sign in ]                     |
+----------------------------------+
```
## 2. Dashboard — ranked candidates
```
+--------------------------------------------------------------------------------+
| TrialMatch · explainable eligibility screening                 coordinator (..)|
+--------------------------------------------------------------------------------+
| [Trial v] [as-of date] [Match all] [Load sample] [Run evaluation] [Audit log]  |
+--------------------------------------------------------------------------------+
|  4 ELIGIBLE      |  4 NEEDS_REVIEW    |  4 INELIGIBLE                          |
+--------------------------------------------------------------------------------+
| Patient | Decision      | Conf | Criteria | Missing | Why (first 150 chars)      |
| P001    | ELIGIBLE      | 0.85 | 10/11    |         | All criteria resolved ...  |
| P003    | NEEDS_REVIEW  | 0.0  | 8/11     | 2       | No HbA1c within 90 days... |
| P002    | INELIGIBLE    | 0.9  | 10/11    |         | [E2] MI within 180 days... |
+--------------------------------------------------------------------------------+
```
## 3. Patient–trial detail (click a row)
```
P003 -> DIAB-201     [NEEDS_REVIEW]   confidence 0.0 · engine 1.0.0
Summary: Cannot finalize eligibility. [I3] No HbA1c within 90 days ...
Missing evidence:  [HbA1c result within 90 days (I3) — latest is 333 days old]
                   [eGFR result within 180 days (I5)]
Criterion | Reasoning + verbatim evidence                     | State
I2        | T2DM documented (structured:E11.9)                | TRUE 0.95
I3        | No HbA1c within 90 days (latest 333 days old)     | UNKNOWN
            [structured · 2025-11-01] "HbA1c 8.9 % on 2025-11-01"
E2        | ...                                               | FALSE 0.85
Data-quality warnings: ...
[Confirm for screening] [Request info] [Reject]     Decision support only.
```
## 4. Evaluation & audit panels
Metric tiles (accuracy, FP rate, unsafe errors, missing-evidence recall, grounding failures) with GATE PASSED/FAILED badge;
audit table with hash-chain integrity badge.
