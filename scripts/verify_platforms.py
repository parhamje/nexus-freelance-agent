#!/usr/bin/env python3
"""Verify the three platform connectors against the LIVE sites (read-only,
polite: single page each, respects robots.txt). Run from repo root:

    python scripts/verify_platforms.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("FREELANCE_DEBUG", "false")


async def main():
    from app.core.config import settings
    from app.integrations.base.connector import get_connector

    print(f"debug={settings.debug}\n")
    for slug in ("karlancer", "ponisha", "parscoders"):
        connector = get_connector(slug)
        caps = connector.capabilities()
        print(f"=== {connector.name} ({slug}) ===")
        print(f"    capabilities: submit={caps.submit_method}, verified={caps.verified}")
        try:
            items = await connector.fetch_projects(page=1, max_items=3)
            print(f"    fetch_projects: {len(items)} item(s)")
            for it in items:
                budget = f"{it.budget_min or '?'}-{it.budget_max or '?'} {it.currency}"
                print(f"      • [{it.external_id}] {it.title[:60]}  | {budget}")
                print(f"        {it.url[:100]}")
            if items:
                check = await connector.check_availability(items[0].external_id, items[0].raw)
                print(f"    availability[{items[0].external_id}]: {check.available} ({check.reason[:60]})")
        except Exception as exc:  # noqa: BLE001
            print(f"    FAILED: {type(exc).__name__}: {exc}")
        finally:
            await connector.aclose()
        print()

asyncio.run(main())
