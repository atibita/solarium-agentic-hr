import csv, json, random, datetime

random.seed(42)
TODAY = datetime.date(2026, 8, 10)

OUT = "/home/claude/solarium/data"

# ---------------------------------------------------------------------------
# OFFICE LOCATIONS
# ---------------------------------------------------------------------------
offices = [
    {"office_id": "LOC-01", "office_name": "Solarium HQ - Austin",      "city": "Austin",      "state_region": "TX", "country": "USA",    "timezone": "America/Chicago",   "is_headquarters": True},
    {"office_id": "LOC-02", "office_name": "Solarium - Denver",         "city": "Denver",      "state_region": "CO", "country": "USA",    "timezone": "America/Denver",     "is_headquarters": False},
    {"office_id": "LOC-03", "office_name": "Solarium - New York",       "city": "New York",    "state_region": "NY", "country": "USA",    "timezone": "America/New_York",   "is_headquarters": False},
    {"office_id": "LOC-04", "office_name": "Solarium - Toronto",        "city": "Toronto",     "state_region": "ON", "country": "Canada", "timezone": "America/Toronto",    "is_headquarters": False},
    {"office_id": "LOC-05", "office_name": "Solarium - Lisbon",         "city": "Lisbon",      "state_region": "",   "country": "Portugal","timezone": "Europe/Lisbon",      "is_headquarters": False},
    {"office_id": "LOC-06", "office_name": "Remote - No Assigned Office","city": "",            "state_region": "",   "country": "",        "timezone": "",                   "is_headquarters": False},
]

# ---------------------------------------------------------------------------
# NAME POOLS (intentionally generic / placeholder-style to signal synthetic data)
# ---------------------------------------------------------------------------
first_names = [
    "Ava","Ben","Carla","Devon","Elena","Femi","Grace","Hassan","Iris","Jamal",
    "Kira","Leo","Mina","Noah","Priya","Quinn","Rosa","Sam","Tara","Uma",
    "Viktor","Wren","Xena","Yusuf","Zoe","Aiden","Bianca","Caleb","Dara","Emmett",
    "Farrah","Gus","Hana","Ivan","Jade","Kenji","Lola","Marco","Nadia","Omar",
]
last_names = [
    "Nakamura","Odusanya","Petrova","Quinones","Reyes","Silva","Thackeray","Ulmer","Vance","Whitfield",
    "Anders","Brightwater","Castellano","Dunmore","Ekwueme","Fontaine","Grigoryan","Holloway","Ionescu","Jarrah",
    "Kowalski","Lindqvist","Mercado","Novak","Okafor","Pemberton","Quintero","Rasmussen","Sandoval","Tanaka",
]
used_names = set()
def unique_name():
    while True:
        fn, ln = random.choice(first_names), random.choice(last_names)
        if (fn, ln) not in used_names:
            used_names.add((fn, ln))
            return fn, ln

departments = ["Engineering","Product","Design","Sales","Marketing","Customer Support",
               "People Operations","Finance","Legal","IT Operations","Security"]

titles_by_dept = {
    "Engineering": ["Software Engineer I","Software Engineer II","Senior Software Engineer","Engineering Manager","Staff Engineer"],
    "Product": ["Product Manager","Senior Product Manager","Associate Product Manager"],
    "Design": ["Product Designer","Senior Product Designer","UX Researcher"],
    "Sales": ["Account Executive","Sales Development Rep","Sales Manager"],
    "Marketing": ["Marketing Specialist","Content Marketing Manager","Growth Marketing Manager"],
    "Customer Support": ["Support Specialist","Senior Support Specialist","Support Team Lead"],
    "People Operations": ["HR Business Partner","People Operations Coordinator","Recruiter"],
    "Finance": ["Financial Analyst","Accounts Payable Specialist","Controller"],
    "Legal": ["Legal Counsel","Contracts Administrator"],
    "IT Operations": ["IT Support Specialist","IT Systems Administrator","Director of IT Operations"],
    "Security": ["Security Analyst","Security Engineer","Chief Information Security Officer"],
}

employment_types = ["Full-Time","Full-Time","Full-Time","Full-Time","Part-Time","Fixed-Term","Intern"]
work_models_by_dept_default = {
    "Customer Support": "Hybrid",
    "IT Operations": "Hybrid",
    "Security": "Hybrid",
}

NUM_EMPLOYEES = 42
employees = []

# First, create a small leadership layer with no manager (executives)
exec_titles = ["Chief Executive Officer","Chief Operating Officer","VP, People Operations",
               "Chief Information Security Officer","Controller"]
exec_depts  = ["Executive","Executive","People Operations","Security","Finance"]

emp_id_counter = 1
def next_id():
    global emp_id_counter
    eid = f"EMP-{emp_id_counter:04d}"
    emp_id_counter += 1
    return eid

leadership = []
for t, d in zip(exec_titles, exec_depts):
    fn, ln = unique_name()
    eid = next_id()
    hire_date = TODAY - datetime.timedelta(days=random.randint(365*4, 365*9))
    office = "LOC-01"
    emp = {
        "employee_id": eid, "first_name": fn, "last_name": ln,
        "email": f"{fn.lower()}.{ln.lower()}@solarium.example",
        "department": d, "title": t, "manager_id": "",
        "employment_type": "Full-Time", "work_model": "Hybrid",
        "office_id": office, "hire_date": hire_date.isoformat(),
        "fte": 1.0, "status": "Active",
    }
    employees.append(emp)
    leadership.append(eid)

# Managers per department (reporting to a leadership exec, mostly VP People Ops for HR-ish, or CEO/COO for others)
dept_manager = {}
for dept in departments:
    fn, ln = unique_name()
    eid = next_id()
    hire_date = TODAY - datetime.timedelta(days=random.randint(365*2, 365*7))
    office = random.choice([o["office_id"] for o in offices if o["office_id"] != "LOC-06"])
    manager_of_manager = random.choice(leadership)
    title = f"{dept} Manager" if dept not in ("Engineering","IT Operations","Security") else \
            ("Engineering Manager" if dept == "Engineering" else f"{dept} Team Lead")
    work_model = work_models_by_dept_default.get(dept, random.choice(["Remote","Hybrid","Office-Based"]))
    emp = {
        "employee_id": eid, "first_name": fn, "last_name": ln,
        "email": f"{fn.lower()}.{ln.lower()}@solarium.example",
        "department": dept, "title": title, "manager_id": manager_of_manager,
        "employment_type": "Full-Time", "work_model": work_model,
        "office_id": office, "hire_date": hire_date.isoformat(),
        "fte": 1.0, "status": "Active",
    }
    employees.append(emp)
    dept_manager[dept] = eid

# Individual contributors
remaining = NUM_EMPLOYEES - len(employees)
for _ in range(remaining):
    fn, ln = unique_name()
    eid = next_id()
    dept = random.choice(departments)
    title = random.choice(titles_by_dept[dept])
    manager_id = dept_manager[dept]
    emp_type = random.choices(employment_types, weights=[40,40,10,6,4])[0] if False else random.choice(employment_types)
    fte = 1.0 if emp_type != "Part-Time" else random.choice([0.5, 0.6, 0.8])
    if emp_type == "Intern":
        hire_date = TODAY - datetime.timedelta(days=random.randint(10, 80))
    elif emp_type == "Fixed-Term":
        hire_date = TODAY - datetime.timedelta(days=random.randint(30, 300))
    else:
        hire_date = TODAY - datetime.timedelta(days=random.randint(15, 365*8))
    work_model = work_models_by_dept_default.get(dept, random.choice(["Remote","Remote","Hybrid","Office-Based"]))
    office = "LOC-06" if work_model == "Remote" else random.choice([o["office_id"] for o in offices if o["office_id"] != "LOC-06"])
    status = "Active"
    # sprinkle a couple of terminated/on-leave employees for realism
    r = random.random()
    if r < 0.07:
        status = "Terminated"
    elif r < 0.11:
        status = "On Leave"

    emp = {
        "employee_id": eid, "first_name": fn, "last_name": ln,
        "email": f"{fn.lower()}.{ln.lower()}@solarium.example",
        "department": dept, "title": title, "manager_id": manager_id,
        "employment_type": emp_type, "work_model": work_model,
        "office_id": office, "hire_date": hire_date.isoformat(),
        "fte": fte, "status": status,
    }
    employees.append(emp)

# ---------------------------------------------------------------------------
# Derived: tenure band + write employees.csv
# ---------------------------------------------------------------------------
def tenure_years(hire_date_str):
    hd = datetime.date.fromisoformat(hire_date_str)
    return (TODAY - hd).days / 365.25

def tenure_band(years):
    if years < 2: return "0-2 years"
    if years < 6: return "3-5 years"
    return "6+ years"

for e in employees:
    e["tenure_years"] = round(tenure_years(e["hire_date"]), 2)
    e["tenure_band"] = tenure_band(e["tenure_years"])

emp_fields = ["employee_id","first_name","last_name","email","department","title",
              "manager_id","employment_type","fte","work_model","office_id",
              "hire_date","tenure_years","tenure_band","status"]
with open(f"{OUT}/employees.csv","w",newline="") as f:
    w = csv.DictWriter(f, fieldnames=emp_fields)
    w.writeheader()
    for e in employees:
        w.writerow({k: e[k] for k in emp_fields})

with open(f"{OUT}/office_locations.csv","w",newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(offices[0].keys()))
    w.writeheader()
    w.writerows(offices)

# ---------------------------------------------------------------------------
# PTO / LEAVE BALANCES  (mirrors SOL-HR-101 accrual rules)
# ---------------------------------------------------------------------------
def pto_annual_days(tenure_band, fte, emp_type):
    if emp_type in ("Intern",):
        return 0.0
    base = {"0-2 years": 15, "3-5 years": 20, "6+ years": 25}[tenure_band]
    return round(base * fte, 2)

pto_rows = []
for e in employees:
    if e["status"] == "Terminated":
        continue
    annual = pto_annual_days(e["tenure_band"], e["fte"], e["employment_type"])
    # months employed this year (partial for new hires)
    hire_date = datetime.date.fromisoformat(e["hire_date"])
    if hire_date.year == TODAY.year:
        months_elapsed = TODAY.month - hire_date.month + (1 if TODAY.day >= hire_date.day else 0)
        months_elapsed = max(months_elapsed, 0)
    else:
        months_elapsed = TODAY.month  # full months elapsed this calendar year
    accrued_ytd = round(annual / 12 * months_elapsed, 2) if annual else 0.0
    used_ytd = round(min(accrued_ytd, random.uniform(0, max(annual*0.6,0))), 2) if annual else 0.0
    carryover_in = round(random.uniform(0,5),2) if e["tenure_years"] >= 1 and annual else 0.0
    balance = round(accrued_ytd + carryover_in - used_ytd, 2)

    sick_cap_hours = 72 * e["fte"] if e["employment_type"] != "Intern" else round(40*e["fte"],1)
    sick_accrued = round(min(sick_cap_hours, random.uniform(10, sick_cap_hours)), 1)
    sick_used = round(min(sick_accrued, random.uniform(0, sick_accrued*0.5)), 1)
    sick_balance = round(sick_accrued - sick_used, 1)

    if e["employment_type"] == "Intern":
        floating_total = 0
    elif hire_date.year == TODAY.year and hire_date.month >= 10:
        floating_total = 0
    elif hire_date.year == TODAY.year and hire_date.month >= 7:
        floating_total = 1
    else:
        floating_total = 2
    floating_used = random.randint(0, floating_total) if floating_total else 0
    floating_remaining = floating_total - floating_used

    pto_rows.append({
        "employee_id": e["employee_id"],
        "plan_year": TODAY.year,
        "pto_annual_accrual_days": annual,
        "pto_accrued_ytd_days": accrued_ytd,
        "pto_used_ytd_days": used_ytd,
        "pto_carryover_in_days": carryover_in,
        "pto_balance_days": balance,
        "sick_leave_accrual_cap_hours": sick_cap_hours,
        "sick_leave_accrued_ytd_hours": sick_accrued,
        "sick_leave_used_ytd_hours": sick_used,
        "sick_leave_balance_hours": sick_balance,
        "floating_holidays_total": floating_total,
        "floating_holidays_used": floating_used,
        "floating_holidays_remaining": floating_remaining,
        "as_of_date": TODAY.isoformat(),
    })

with open(f"{OUT}/pto_leave_balances.csv","w",newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(pto_rows[0].keys()))
    w.writeheader()
    w.writerows(pto_rows)

# ---------------------------------------------------------------------------
# BENEFITS ELECTIONS (mirrors SOL-HR-103)
# ---------------------------------------------------------------------------
health_plans = ["PPO Health Plan", "HDHP + HSA", "Waived - Covered Elsewhere"]
dental_opts = ["Enrolled", "Waived"]
vision_opts = ["Enrolled", "Waived"]
fsa_types = ["None", "Healthcare FSA", "Dependent Care FSA", "Both"]

benefits_rows = []
for e in employees:
    if e["status"] == "Terminated":
        continue
    eligible = e["employment_type"] != "Intern" and e["fte"] >= 0.5
    if not eligible:
        benefits_rows.append({
            "employee_id": e["employee_id"], "plan_year": TODAY.year,
            "benefits_eligible": False, "health_plan": "Not Eligible",
            "dental": "Not Eligible", "vision": "Not Eligible",
            "fsa_election": "None", "fsa_annual_amount_usd": 0,
            "retirement_contribution_pct": 0, "retirement_auto_enrolled": False,
            "supplemental_life_insurance": "Not Eligible",
            "wellness_stipend_enrolled": False,
            "domestic_partner_coverage": False,
        })
        continue

    health = random.choices(health_plans, weights=[55, 30, 15])[0]
    dental = random.choices(dental_opts, weights=[80,20])[0]
    vision = random.choices(vision_opts, weights=[70,30])[0]
    fsa = random.choices(fsa_types, weights=[55,20,15,10])[0]
    fsa_amt = 0
    if fsa in ("Healthcare FSA","Both"):
        fsa_amt += random.choice([500,1000,1500,2000,2500])
    if fsa in ("Dependent Care FSA","Both"):
        fsa_amt += random.choice([1000,2000,3000,5000])
    retirement_pct = random.choice([0,2,4,4,4,6,8,10,15])
    auto_enrolled = retirement_pct == 4 and random.random() < 0.6
    supplemental_life = random.choices(["None","1x Salary","2x Salary","3x Salary"], weights=[50,25,15,10])[0]
    wellness = random.random() < 0.62
    domestic_partner = random.random() < 0.08

    benefits_rows.append({
        "employee_id": e["employee_id"], "plan_year": TODAY.year,
        "benefits_eligible": True, "health_plan": health,
        "dental": dental, "vision": vision,
        "fsa_election": fsa, "fsa_annual_amount_usd": fsa_amt,
        "retirement_contribution_pct": retirement_pct, "retirement_auto_enrolled": auto_enrolled,
        "supplemental_life_insurance": supplemental_life,
        "wellness_stipend_enrolled": wellness,
        "domestic_partner_coverage": domestic_partner,
    })

with open(f"{OUT}/benefits_elections.csv","w",newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(benefits_rows[0].keys()))
    w.writeheader()
    w.writerows(benefits_rows)

# ---------------------------------------------------------------------------
# SUPPORT TICKETS (IT / HR / Security / Facilities) -> JSON
# ---------------------------------------------------------------------------
categories = {
    "IT": ["Laptop hardware issue","Software install request","VPN connectivity problem",
           "Monitor / peripheral request","Password reset","Account access request"],
    "HR": ["Benefits enrollment question","PTO balance discrepancy","Parental leave request",
           "Address / direct deposit update","Bereavement leave request","Onboarding paperwork issue"],
    "Security": ["Suspected phishing email","Lost or stolen device","MFA setup issue",
                 "Access request - Restricted data","Policy exception request"],
    "Facilities": ["Office badge access issue","Desk / seating request","Conference room AV issue"],
}
priorities = ["Low","Medium","High","Urgent"]
statuses = ["Open","In Progress","Resolved","Closed"]

active_employees = [e for e in employees if e["status"] != "Terminated"]
tickets = []
ticket_counter = 1
NUM_TICKETS = 65
for _ in range(NUM_TICKETS):
    cat = random.choices(list(categories.keys()), weights=[45,30,10,15])[0]
    subject = random.choice(categories[cat])
    requester = random.choice(active_employees)
    created = TODAY - datetime.timedelta(days=random.randint(0, 120))
    priority = random.choices(priorities, weights=[30,40,20,10])[0]
    if cat == "Security" and subject in ("Suspected phishing email","Lost or stolen device"):
        priority = random.choices(["High","Urgent"], weights=[60,40])[0]
    status = random.choices(statuses, weights=[15,20,25,40])[0]
    resolved = None
    resolution_days = None
    if status in ("Resolved","Closed"):
        resolution_days = random.randint(0, 12) if priority != "Urgent" else random.randint(0,2)
        resolved_date = created + datetime.timedelta(days=resolution_days)
        if resolved_date <= TODAY:
            resolved = resolved_date.isoformat()
        else:
            status = "Open"
    assignee_pool = [e for e in employees if e["department"] in
                      ({"IT":"IT Operations","Security":"Security","HR":"People Operations","Facilities":"IT Operations"}[cat])]
    assignee = random.choice(assignee_pool)["employee_id"] if assignee_pool else ""

    tickets.append({
        "ticket_id": f"TCK-{ticket_counter:05d}",
        "category": cat,
        "subject": subject,
        "requester_employee_id": requester["employee_id"],
        "assigned_to_employee_id": assignee,
        "priority": priority,
        "status": status,
        "created_date": created.isoformat(),
        "resolved_date": resolved,
        "resolution_days": resolution_days if resolved else None,
    })
    ticket_counter += 1

with open(f"{OUT}/support_tickets.json","w") as f:
    json.dump({
        "_meta": {
            "description": "SYNTHETIC MOCK DATA - Solarium Inc. IT/HR/Security/Facilities support tickets. Not real people, systems, or events.",
            "record_count": len(tickets),
            "generated_as_of": TODAY.isoformat(),
        },
        "tickets": tickets
    }, f, indent=2)

# ---------------------------------------------------------------------------
# ORG CHART (manager -> direct reports) as JSON, derived from employees.csv
# ---------------------------------------------------------------------------
by_id = {e["employee_id"]: e for e in employees}
reports = {}
for e in employees:
    mgr = e["manager_id"]
    if mgr:
        reports.setdefault(mgr, []).append(e["employee_id"])

org_chart = []
for e in employees:
    org_chart.append({
        "employee_id": e["employee_id"],
        "name": f"{e['first_name']} {e['last_name']}",
        "title": e["title"],
        "department": e["department"],
        "manager_id": e["manager_id"] or None,
        "manager_name": (f"{by_id[e['manager_id']]['first_name']} {by_id[e['manager_id']]['last_name']}"
                          if e["manager_id"] else None),
        "direct_report_ids": reports.get(e["employee_id"], []),
        "direct_report_count": len(reports.get(e["employee_id"], [])),
    })

with open(f"{OUT}/org_chart.json","w") as f:
    json.dump({
        "_meta": {
            "description": "SYNTHETIC MOCK DATA - Solarium Inc. reporting relationships. Not real people.",
            "record_count": len(org_chart),
        },
        "employees": org_chart
    }, f, indent=2)

print("Employees:", len(employees))
print("PTO rows:", len(pto_rows))
print("Benefits rows:", len(benefits_rows))
print("Tickets:", len(tickets))
print("Done.")
