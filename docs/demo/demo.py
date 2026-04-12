#!/usr/bin/env python3
"""
register-mcp CLI Demo
=====================
Simulates the MCP tool responses in a terminal for demo recording (vhs).
Calls the live Zefix API — requires internet access.

Usage:
    python docs/demo/demo.py verify "Lehrmittelverlag Zürich AG"
    python docs/demo/demo.py uid "CHE-109.741.634"
    python docs/demo/demo.py search "Migros" --canton ZH
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

# Allow running from repo root without installation
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import httpx

ZEFIX_BASE = "https://www.zefix.admin.ch/ZefixREST/api/v1"
TIMEOUT = 15.0

# ── helpers ──────────────────────────────────────────────────────────────────

def _status_icon(status: str) -> str:
    return "✅" if status == "EXISTIEREND" else "❌"


def _uid_fmt(uid: str) -> str:
    """CHE123456789 → CHE-123.456.789"""
    digits = uid.replace("CHE", "").replace("-", "").replace(".", "")
    if len(digits) == 9:
        return f"CHE-{digits[:3]}.{digits[3:6]}.{digits[6:]}"
    return uid


async def _fetch_legal_forms(client: httpx.AsyncClient) -> dict[int, str]:
    r = await client.get(f"{ZEFIX_BASE}/legalForm", timeout=TIMEOUT)
    r.raise_for_status()
    return {lf["id"]: lf["kurzform"].get("de", "—") for lf in r.json()}


# ── commands ─────────────────────────────────────────────────────────────────

async def cmd_verify(name: str) -> None:
    print(f"\n🔍  zefix_verify_company(name={name!r})\n")
    async with httpx.AsyncClient() as client:
        legal_forms = await _fetch_legal_forms(client)
        payload = {"name": name, "maxEntries": 5, "offset": 0}
        r = await client.post(f"{ZEFIX_BASE}/firm/search.json", json=payload, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()

    firms = data.get("list", [])
    if not firms:
        print("❌  Nicht im Handelsregister gefunden.")
        return

    active = [f for f in firms if f.get("status") == "EXISTIEREND"]
    icon = "✅" if active else "❌"
    label = "Aktive Einträge" if active else "Keine aktiven Einträge"
    print(f"{icon}  {label} für «{name}»\n")
    for f in (active or firms)[:3]:
        uid = _uid_fmt(f.get("uidFormatted") or f.get("uid", "—"))
        lf = legal_forms.get(f.get("legalFormId", 0), "—")
        canton = f.get("legalSeat", "—")
        shab = f.get("shabDate", "—")
        print(f"  • {f['name']}")
        print(f"    UID: {uid}  |  Rechtsform: {lf}  |  Sitz: {canton}")
        print(f"    Status: {f.get('status')}  |  Letzte SHAB-Mutation: {shab}")
        print()


async def cmd_uid(uid: str) -> None:
    uid_clean = uid.replace("-", "").replace(".", "")
    print(f"\n🔍  zefix_get_company_by_uid(uid={uid!r})\n")
    async with httpx.AsyncClient() as client:
        legal_forms = await _fetch_legal_forms(client)
        payload = {"uid": uid_clean, "maxEntries": 1, "offset": 0}
        r = await client.post(f"{ZEFIX_BASE}/firm/search.json", json=payload, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()

    firms = data.get("list", [])
    if not firms:
        print(f"❌  Keine Firma mit UID {uid} gefunden.")
        return

    f = firms[0]
    uid_fmt = _uid_fmt(f.get("uidFormatted") or f.get("uid", uid))
    lf = legal_forms.get(f.get("legalFormId", 0), "—")
    icon = _status_icon(f.get("status", ""))
    print(f"## {icon} {f['name']}\n")
    print(f"  UID:         {uid_fmt}")
    print(f"  CHID:        {f.get('chidFormatted', '—')}")
    print(f"  Rechtsform:  {lf}")
    print(f"  Sitz:        {f.get('legalSeat', '—')}")
    print(f"  Status:      {f.get('status', '—')}")
    print(f"  SHAB-Datum:  {f.get('shabDate', '—')}")
    if f.get("cantonalExcerptWeb"):
        print(f"  Auszug:      {f['cantonalExcerptWeb']}")
    print()


async def cmd_search(name: str, canton: str | None) -> None:
    print(f"\n🔍  zefix_search_companies(name={name!r}, canton={canton!r})\n")
    async with httpx.AsyncClient() as client:
        legal_forms = await _fetch_legal_forms(client)
        payload: dict = {"name": name, "maxEntries": 5, "offset": 0}
        if canton:
            payload["canton"] = canton.upper()
        r = await client.post(f"{ZEFIX_BASE}/firm/search.json", json=payload, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()

    firms = data.get("list", [])
    total = data.get("maxOffset", len(firms))
    print(f"  {len(firms)} Ergebnisse (von ca. {total}):\n")
    for f in firms:
        uid = _uid_fmt(f.get("uidFormatted") or f.get("uid", "—"))
        lf = legal_forms.get(f.get("legalFormId", 0), "—")
        icon = _status_icon(f.get("status", ""))
        print(f"  {icon} {f['name']}")
        print(f"     UID: {uid}  |  {lf}  |  {f.get('legalSeat', '—')}")
    print()


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="register-mcp demo CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser("verify", help="Verify company status")
    p_verify.add_argument("name")

    p_uid = sub.add_parser("uid", help="Lookup company by UID")
    p_uid.add_argument("uid")

    p_search = sub.add_parser("search", help="Search companies by name")
    p_search.add_argument("name")
    p_search.add_argument("--canton", default=None)

    args = parser.parse_args()

    if args.cmd == "verify":
        asyncio.run(cmd_verify(args.name))
    elif args.cmd == "uid":
        asyncio.run(cmd_uid(args.uid))
    elif args.cmd == "search":
        asyncio.run(cmd_search(args.name, args.canton))


if __name__ == "__main__":
    main()
