"""
mcp_server/mock_data_store.py
--------------------------------
Loads the synthetic HR datasets (mock_data/*.csv, *.json) into memory once
and exposes small lookup helpers used by the HR data MCP tools. All data
here is synthetic test data -- see mock_data/README_DATA.md.

This module is intentionally storage-agnostic at the call site: tools call
`get_employee(employee_id)` etc. without knowing whether the backing store
is CSV files (current, free-tier friendly), SQLite, or a hosted DB -- so
swapping storage later doesn't touch tool logic.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from threading import Lock

MOCK_DATA_DIR = Path(__file__).resolve().parent.parent / "mock_data"


class MockDataStore:
    _lock = Lock()

    def __init__(self, data_dir: Path = MOCK_DATA_DIR):
        self.data_dir = Path(data_dir)
        self.employees: dict[str, dict] = {}
        self.pto: dict[str, dict] = {}
        self.benefits: dict[str, dict] = {}
        self.offices: dict[str, dict] = {}
        self.tickets: list[dict] = []
        self._next_ticket_seq = 1
        self._load()

    # -- loading ------------------------------------------------------
    def _load(self):
        self.employees = {r["employee_id"]: r for r in self._read_csv("employees.csv")}
        self.pto = {r["employee_id"]: r for r in self._read_csv("pto_leave_balances.csv")}
        self.benefits = {r["employee_id"]: r for r in self._read_csv("benefits_elections.csv")}
        self.offices = {r["office_id"]: r for r in self._read_csv("office_locations.csv")}

        tickets_path = self.data_dir / "support_tickets.json"
        if tickets_path.exists():
            with open(tickets_path) as f:
                payload = json.load(f)
            self.tickets = payload.get("tickets", [])
            existing = [int(t["ticket_id"].split("-")[1]) for t in self.tickets if "-" in t["ticket_id"]]
            self._next_ticket_seq = (max(existing) + 1) if existing else 1

    def _read_csv(self, filename: str) -> list[dict]:
        path = self.data_dir / filename
        if not path.exists():
            return []
        with open(path, newline="") as f:
            return list(csv.DictReader(f))

    # -- lookups --------------------------------------------------------
    def get_employee(self, employee_id: str) -> dict | None:
        return self.employees.get(employee_id)

    def find_employee_by_name(self, name: str) -> dict | None:
        name_lower = name.strip().lower()
        for e in self.employees.values():
            full = f"{e['first_name']} {e['last_name']}".lower()
            if full == name_lower:
                return e
        return None

    def get_pto_balance(self, employee_id: str) -> dict | None:
        return self.pto.get(employee_id)

    def get_benefits(self, employee_id: str) -> dict | None:
        return self.benefits.get(employee_id)

    def get_office(self, office_id: str) -> dict | None:
        return self.offices.get(office_id)

    def get_manager(self, employee_id: str) -> dict | None:
        emp = self.get_employee(employee_id)
        if not emp or not emp.get("manager_id"):
            return None
        return self.get_employee(emp["manager_id"])

    # -- mock write operations ------------------------------------------
    def create_ticket(self, category: str, subject: str, requester_employee_id: str,
                       description: str = "", priority: str = "Medium") -> dict:
        """Mock HR/IT ticket creation. This never touches a real ticketing
        system -- it appends to an in-memory list for the lifetime of the
        process, which is sufficient for a demo/evaluation environment and
        keeps the action safely reversible (nothing external is mutated)."""
        with self._lock:
            ticket_id = f"TCK-{self._next_ticket_seq:05d}"
            self._next_ticket_seq += 1
            ticket = {
                "ticket_id": ticket_id,
                "category": category,
                "subject": subject,
                "requester_employee_id": requester_employee_id,
                "assigned_to_employee_id": "",
                "priority": priority,
                "status": "Open",
                "description": description,
                "created_date": _today_iso(),
                "resolved_date": None,
                "resolution_days": None,
                "mock": True,
            }
            self.tickets.append(ticket)
            return ticket


def _today_iso() -> str:
    import datetime
    return datetime.date.today().isoformat()


# Module-level singleton so all tool calls within a process share one store.
_store: MockDataStore | None = None


def get_store() -> MockDataStore:
    global _store
    if _store is None:
        _store = MockDataStore()
    return _store
