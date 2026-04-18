# CMS National Provider Directory — Full Analysis

This repository contains analysis scripts for the [CMS National Provider Directory (NPD)](https://directory.cms.gov/) — the largest public healthcare provider dataset ever released, containing **27,204,567 FHIR records** across 6 resource types.

## Dataset Overview

| Resource | Records | Compressed Size | Original Size |
|---|---|---|---|
| Practitioner | 7,441,212 | 1.2 GB | 20.5 GB |
| PractitionerRole | 7,180,732 | 660 MB | 5.8 GB |
| Organization | 3,605,261 | 512 MB | 8.2 GB |
| Location | 3,494,239 | 202 MB | 1.5 GB |
| Endpoint | 5,043,524 | 179 MB | 4.4 GB |
| OrganizationAffiliation | 439,599 | 18 MB | 188 MB |
| **Total** | **27,204,567** | **2.8 GB** | **40.7 GB** |

Data source: [https://directory.cms.gov/downloads/](https://directory.cms.gov/downloads/)  
Release date: 2026-04-09 | Format: NDJSON compressed with zstd level 12

## Key Findings (100% Population Analysis)

### Practitioners (7,441,212 records)
- **67.42% female** (5,016,631 women vs. 2,389,498 men)
- **Nurse Practitioners** are the #1 specialty (8.8%)
- **Behavior Technicians** are #2 (8.53%) — reflecting the ABA therapy boom
- **39.75%** have CMS enrollment in good standing
- **0%** have been IAL2 identity-verified (NIST standard)
- **27.39%** are aligned with the CMS data network
- NPI enrollment peaked in **2006** (1,009,174 new enrollments)
- **92.47%** have an endpoint reference

### Organizations (3,605,261 records)
- **55.45%** typed as "Healthcare Provider"
- **44.55%** typed as "ein" (tax ID only — no FHIR type)
- **100%** have verification status "complete"
- **94.77%** have a phone number
- **54.95%** have a fax number

### Endpoints (5,043,524 records)
- **74.21%** active, **25.79%** error/Direct Project
- **FHIR R4**: 70.6% of all endpoints
- **Direct Project** (legacy): 25.81% of all endpoints
- **Cerner** is #1 EHR by endpoint count (12.97%)
- **athenahealth** is #2 (8.40%)
- **Epic** hosted infrastructure is #3 (7.38%)
- **100%** use HTTPS

### Locations (3,494,239 records)
- **46.64%** have GPS coordinates
- **0%** have hours of operation
- **0%** have accepting-new-patients flag
- GPS precision: 97.9% at 5+ decimal places (sub-meter accuracy)
- Top states: CA (176,913), FL (134,240), TX (126,627)

### PractitionerRole (7,180,732 records)
- **44.85%** are inactive (historical records)
- **100%** have `newpatients: true` (field is not being used meaningfully)
- **74.93%** have a phone number
- **9.51%** have a fax number

### OrganizationAffiliation (439,599 records)
- **57.10%** Member affiliations
- **3.33%** HIE/HIO affiliations (14,622 records — first public enumeration of HIE participation)
- **100%** active

## GitHub Actions Analysis

The `graph_analysis.yml` workflow runs the full **cross-resource graph linkage analysis** in GitHub Actions cloud infrastructure:

1. Downloads all 6 CMS NPD files (2.8 GB)
2. Builds the full Practitioner → PractitionerRole → Organization → Location → Endpoint chain
3. Computes chain completeness at population scale
4. Identifies top 50 health systems by practitioner count
5. Analyzes the OrganizationAffiliation network
6. Uploads `graph_stats.json` as a downloadable artifact

### Running the workflow

1. Go to **Actions** tab → **CMS NPD Graph Linkage Analysis**
2. Click **Run workflow** → type `run` → click **Run workflow**
3. Wait ~45–60 minutes for completion
4. Download `graph-linkage-results` artifact from the completed run

## Repository Structure

```
cms-npd-analysis/
├── .github/
│   └── workflows/
│       └── graph_analysis.yml    # GitHub Actions workflow
├── analysis/
│   └── graph_linkage.py          # Cross-resource graph linkage script
├── data/                         # Downloaded data files (gitignored — too large)
├── results/                      # Analysis output JSON files
└── README.md
```

## Data Access

The raw data files are not stored in this repository (too large for GitHub). Download them directly:

```bash
BASE="https://directory.cms.gov/downloads"
wget "$BASE/Practitioner.ndjson.zst"
wget "$BASE/PractitionerRole.ndjson.zst"
wget "$BASE/Organization.ndjson.zst"
wget "$BASE/Location.ndjson.zst"
wget "$BASE/Endpoint.ndjson.zst"
wget "$BASE/OrganizationAffiliation.ndjson.zst"
```

## Requirements

```
pip install zstandard
```

## What Can Be Built

The NPD enables a new generation of healthcare infrastructure:

1. **Provider search engines** — Google Maps for doctors, with real-time FHIR endpoint discovery
2. **EHR connectivity maps** — visualize which EHR platforms serve which geographies
3. **Care gap analytics** — identify deserts for specific specialties
4. **Prior authorization automation** — use endpoint data to route requests to the right FHIR API
5. **Healthcare CRM enrichment** — append FHIR endpoints and org affiliations to sales data
6. **HIE participation tracking** — the 14,622 HIE/HIO records are the first public enumeration
7. **Workforce analytics** — gender, specialty, and qualification distributions at population scale
8. **Referral network mapping** — use PractitionerRole to map who works where

## License

Data is public domain (US Government). Analysis code is MIT licensed.
