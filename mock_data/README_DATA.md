# Solarium Inc. — Synthetic Mock HR/IT Datasets

**⚠️ ALL DATA IN THIS PACKAGE IS SYNTHETIC.** Every employee, name, email address, ticket, and balance below was randomly generated (seeded, reproducible) for testing, demos, and documentation purposes. "Solarium Inc." is a fictional company. No record here corresponds to a real person, and `@solarium.example` uses the `.example` domain reserved by [RFC 2606](https://www.rfc-editor.org/rfc/rfc2606) specifically so it can never resolve to a real address. Do not treat any value as real PII.

This dataset is designed to pair with the Solarium Governance Policy Corpus (SOL-GOV-000 and related policy documents) so that policy figures (PTO accrual rates, sick leave caps, floating holiday counts, benefits plan names, etc.) are reflected consistently in the underlying data.

## Files

| File | Format | Rows | Grain | Description |
|---|---|---|---|---|
| `employees.csv` | CSV | 42 | 1 row per employee | Core employee profile: department, title, manager, employment type, work model, office, hire date, tenure, status |
| `office_locations.csv` | CSV | 6 | 1 row per office | Office locations including a "Remote - No Assigned Office" placeholder row |
| `pto_leave_balances.csv` | CSV | 40 | 1 row per active/on-leave employee, current plan year | PTO accrual/usage/balance, sick leave hours, floating holidays — mirrors SOL-HR-101 accrual tiers |
| `benefits_elections.csv` | CSV | 40 | 1 row per active/on-leave employee, current plan year | Health/dental/vision elections, FSA, retirement contribution %, supplemental life, wellness stipend — mirrors SOL-HR-103 |
| `support_tickets.json` | JSON | 65 | 1 record per ticket | IT / HR / Security / Facilities support tickets with requester, assignee, priority, status, dates |
| `org_chart.json` | JSON | 42 | 1 record per employee | Manager relationships and direct reports, derived from `employees.csv` |

Terminated employees (status = `Terminated`) appear in `employees.csv` for referential completeness but are intentionally excluded from `pto_leave_balances.csv` and `benefits_elections.csv`, since those balances aren't meaningful after separation — a realistic quirk worth testing against.

## Schema Details

### employees.csv
| Column | Type | Notes |
|---|---|---|
| employee_id | string | Primary key, format `EMP-####` |
| first_name, last_name | string | Synthetic names |
| email | string | `first.last@solarium.example` |
| department | string | One of 11 departments, or `Executive` for leadership |
| title | string | Job title |
| manager_id | string, nullable | FK to `employee_id`; blank for the 5 top executives |
| employment_type | string | `Full-Time`, `Part-Time`, `Fixed-Term`, `Intern` |
| fte | float | 1.0 for full-time; 0.5–0.8 for part-time |
| work_model | string | `Remote`, `Hybrid`, `Office-Based` (see SOL-OPS-201) |
| office_id | string | FK to `office_locations.csv`; `LOC-06` for fully remote employees |
| hire_date | date (ISO 8601) | |
| tenure_years | float | Computed as of the dataset's `as_of` date, 2026-08-10 |
| tenure_band | string | `0-2 years`, `3-5 years`, `6+ years` — matches the PTO accrual tiers in SOL-HR-101 |
| status | string | `Active`, `On Leave`, `Terminated` |

### pto_leave_balances.csv
Mirrors SOL-HR-101: 15/20/25 annual PTO days by tenure band, sick leave accruing to a 72-hour cap, and 2 floating holidays/year (pro-rated for employees hired after June 30). `pto_balance_days` = accrued year-to-date + carryover in − used year-to-date.

### benefits_elections.csv
Mirrors SOL-HR-103: `PPO Health Plan`, `HDHP + HSA`, or waived; dental/vision enrollment; FSA type and annual election amount; retirement contribution % (4% reflects the auto-enrollment default); supplemental life insurance tier; wellness stipend enrollment flag; domestic partner coverage flag. Employees who are ineligible (interns, <0.5 FTE) show `benefits_eligible: false` with placeholder "Not Eligible" values rather than blank fields, so eligibility logic can be tested explicitly.

### support_tickets.json
```json
{
  "_meta": { "description": "...", "record_count": 65, "generated_as_of": "2026-08-10" },
  "tickets": [
    {
      "ticket_id": "TCK-00001",
      "category": "IT | HR | Security | Facilities",
      "subject": "string",
      "requester_employee_id": "FK -> employees.csv",
      "assigned_to_employee_id": "FK -> employees.csv (routed to a plausible owning department)",
      "priority": "Low | Medium | High | Urgent",
      "status": "Open | In Progress | Resolved | Closed",
      "created_date": "ISO 8601",
      "resolved_date": "ISO 8601 or null",
      "resolution_days": "integer or null"
    }
  ]
}
```
Security tickets about phishing or lost/stolen devices are weighted toward `High`/`Urgent` priority to reflect SOL-SEC-401's incident-reporting urgency.

### org_chart.json
Derived view of `employees.csv` showing each employee's manager and direct reports, useful for testing org-hierarchy questions ("who does X report to," "how many direct reports does Y have") without re-deriving it from the flat employee table each time.

## Regeneration

All files were produced by `generate_mock_data.py` (included) using a fixed random seed (`42`), so re-running the script reproduces an identical dataset — useful if you need to regenerate after editing the generation logic, or want to verify no hidden randomness leaked in.

## Suggested Uses

- Testing chatbot/assistant responses against the Solarium policy corpus using realistic-shaped data ("What's my PTO balance?", "Who's my manager?", "Show me open Security tickets")
- Demoing dashboards, reports, or data pipelines without any real employee data
- Validating that eligibility rules (e.g., benefits eligibility, PTO accrual by tenure) are correctly implemented against known synthetic inputs
