"""
mcp_server/tools/hr_data_tools.py
------------------------------------
MCP tools backed by the synthetic mock_data/ datasets (employees, PTO,
benefits, tickets). Two of these (`create_mock_hr_ticket`, `draft_hr_email`)
have side effects / produce an action, and are explicitly marked
`readonly=False` in the tool registration (see server.py) so the agent
orchestrator's confirmation gate applies to them.
"""
from __future__ import annotations

from ..mock_data_store import get_store


def lookup_employee_profile(employee_id: str) -> dict:
    """Look up a Solarium employee's profile by employee ID.

    Args:
        employee_id: e.g. "EMP-0007"
    """
    store = get_store()
    emp = store.get_employee(employee_id)
    if not emp:
        return {"found": False, "employee_id": employee_id,
                "message": f"No employee found with ID '{employee_id}'."}
    manager = store.get_manager(employee_id)
    office = store.get_office(emp.get("office_id", ""))
    return {
        "found": True,
        "employee_id": emp["employee_id"],
        "name": f"{emp['first_name']} {emp['last_name']}",
        "email": emp["email"],
        "department": emp["department"],
        "title": emp["title"],
        "employment_type": emp["employment_type"],
        "work_model": emp["work_model"],
        "office": office["office_name"] if office else emp.get("office_id"),
        "hire_date": emp["hire_date"],
        "tenure_band": emp["tenure_band"],
        "status": emp["status"],
        "manager_name": f"{manager['first_name']} {manager['last_name']}" if manager else None,
        "manager_id": emp.get("manager_id") or None,
    }


def check_pto_balance(employee_id: str) -> dict:
    """Look up an employee's current PTO, sick leave, and floating holiday
    balances.

    Args:
        employee_id: e.g. "EMP-0007"
    """
    store = get_store()
    emp = store.get_employee(employee_id)
    if not emp:
        return {"found": False, "employee_id": employee_id,
                "message": f"No employee found with ID '{employee_id}'."}
    pto = store.get_pto_balance(employee_id)
    if not pto:
        return {"found": True, "employee_id": employee_id,
                "message": "Employee found, but has no PTO balance on record "
                           "(e.g. interns do not accrue PTO per SOL-HR-101 Section 9)."}
    return {
        "found": True,
        "employee_id": employee_id,
        "name": f"{emp['first_name']} {emp['last_name']}",
        "plan_year": pto["plan_year"],
        "pto_balance_days": float(pto["pto_balance_days"]),
        "pto_accrued_ytd_days": float(pto["pto_accrued_ytd_days"]),
        "pto_used_ytd_days": float(pto["pto_used_ytd_days"]),
        "sick_leave_balance_hours": float(pto["sick_leave_balance_hours"]),
        "floating_holidays_remaining": int(pto["floating_holidays_remaining"]),
        "as_of_date": pto["as_of_date"],
    }


def lookup_benefits_status(employee_id: str) -> dict:
    """Look up an employee's current benefits elections.

    Args:
        employee_id: e.g. "EMP-0007"
    """
    store = get_store()
    emp = store.get_employee(employee_id)
    if not emp:
        return {"found": False, "employee_id": employee_id,
                "message": f"No employee found with ID '{employee_id}'."}
    benefits = store.get_benefits(employee_id)
    if not benefits:
        return {"found": True, "employee_id": employee_id,
                "message": "No benefits record on file for this employee."}
    eligible = str(benefits.get("benefits_eligible", "")).lower() == "true"
    return {
        "found": True,
        "employee_id": employee_id,
        "name": f"{emp['first_name']} {emp['last_name']}",
        "benefits_eligible": eligible,
        "health_plan": benefits["health_plan"],
        "dental": benefits["dental"],
        "vision": benefits["vision"],
        "fsa_election": benefits["fsa_election"],
        "retirement_contribution_pct": benefits["retirement_contribution_pct"],
        "wellness_stipend_enrolled": str(benefits.get("wellness_stipend_enrolled", "")).lower() == "true",
    }


def create_mock_hr_ticket(employee_id: str, category: str, subject: str,
                           description: str = "", priority: str = "Medium") -> dict:
    """Create a MOCK HR/IT support ticket. This does not contact any real
    ticketing system -- it is a simulated write for demo/evaluation
    purposes. The agent orchestrator requires explicit user confirmation
    before calling this tool (see agent/orchestrator.py CONFIRM-then-ACT
    gate).

    Args:
        employee_id: requester's employee ID
        category: one of "IT", "HR", "Security", "Facilities"
        subject: short ticket subject line
        description: optional longer description
        priority: "Low" | "Medium" | "High" | "Urgent"
    """
    store = get_store()
    emp = store.get_employee(employee_id)
    if not emp:
        return {"created": False, "message": f"No employee found with ID '{employee_id}'."}
    ticket = store.create_ticket(category, subject, employee_id, description, priority)
    return {"created": True, "mock_action": True, "ticket": ticket}


def draft_hr_email(employee_id: str, purpose: str, key_points: str = "") -> dict:
    """Draft (but never send) an HR-related email on the employee's behalf,
    e.g. requesting parental leave dates from a manager. This is a MOCK
    drafting tool only -- it returns text for the user to review and send
    themselves; it never actually transmits anything.

    Args:
        employee_id: the employee the email is drafted for
        purpose: what the email is about, e.g. "requesting 2 weeks PTO in October"
        key_points: optional comma-separated key points to include
    """
    store = get_store()
    emp = store.get_employee(employee_id)
    if not emp:
        return {"drafted": False, "message": f"No employee found with ID '{employee_id}'."}
    manager = store.get_manager(employee_id)
    manager_name = f"{manager['first_name']} {manager['last_name']}" if manager else "your manager"
    points_block = ""
    if key_points:
        bullets = "\n".join(f"- {p.strip()}" for p in key_points.split(",") if p.strip())
        points_block = f"\n{bullets}\n"

    draft = (
        f"Subject: {purpose.strip().capitalize()}\n\n"
        f"Hi {manager_name.split()[0] if manager else 'there'},\n\n"
        f"I wanted to reach out about {purpose.strip()}.{points_block}\n"
        f"Let me know if you'd like to discuss further.\n\n"
        f"Thanks,\n{emp['first_name']} {emp['last_name']}"
    )
    return {"drafted": True, "mock_action": True, "recipient": manager_name, "email_draft": draft}
