"""
Phase 1 — Source DB cleanup migration.

Actions:
  1. Remove sources that are out of scope (competitor, ESG reddit, IT-focused, etc.)
  2. Rename source_types: reddit→practitioner_community, community→practitioner_community,
     industry_news→trade_media
  3. Add 6 practitioner publication sources (type: practitioner_pub)
  4. Add 5 conference program sources  (type: conference)

Run from alm-market-voice/backend/ with the venv active:
    python migrate_sources.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.models import SessionLocal, Source

# ── Sources to remove (by exact name) ────────────────────────────────────────
REMOVE_NAMES = {
    "Reddit r/maximo",
    "Reddit r/sustainability",
    "Reddit r/sysadmin (asset mgmt)",
    "Stack Overflow - asset mgmt",          # often named this in DB
    "IBM Community - Maximo",               # in case it exists
    "LinkedIn EAM/CMMS Group",
    "Spiceworks - Asset Mgmt",
    # Competitors
    "IFS",
    "MaintainX",
    "Hexagon",
    "Siemens",
    "SAP",
    "ServiceNow",
}

# ── Source type renames ───────────────────────────────────────────────────────
TYPE_RENAMES = {
    "reddit":        "practitioner_community",
    "community":     "practitioner_community",
    "industry_news": "trade_media",
}

# ── New practitioner publication sources ─────────────────────────────────────
NEW_PRACTITIONER_PUBS = [
    {
        "name": "Plant Services",
        "source_type": "practitioner_pub",
        "url": "https://news.google.com/rss/search?q=plant+services+maintenance+reliability&hl=en-US&gl=US&ceid=US:en",
    },
    {
        "name": "Reliable Plant",
        "source_type": "practitioner_pub",
        "url": "https://news.google.com/rss/search?q=reliable+plant+maintenance+reliability+practitioner&hl=en-US&gl=US&ceid=US:en",
    },
    {
        "name": "Maintworld",
        "source_type": "practitioner_pub",
        "url": "https://news.google.com/rss/search?q=maintworld+maintenance+reliability&hl=en-US&gl=US&ceid=US:en",
    },
    {
        "name": "Maintenance World",
        "source_type": "practitioner_pub",
        "url": "https://news.google.com/rss/search?q=maintenance+world+reliability+asset+management&hl=en-US&gl=US&ceid=US:en",
    },
    {
        "name": "Reliabilityweb / IMC",
        "source_type": "practitioner_pub",
        "url": "https://news.google.com/rss/search?q=reliabilityweb+maintenance+reliability&hl=en-US&gl=US&ceid=US:en",
    },
    {
        "name": "Asset Mgmt & Maintenance Journal",
        "source_type": "practitioner_pub",
        "url": "https://news.google.com/rss/search?q=asset+management+maintenance+journal+practitioner&hl=en-US&gl=US&ceid=US:en",
    },
]

# ── New conference program sources ────────────────────────────────────────────
NEW_CONFERENCES = [
    {
        "name": "SMRP Annual Conference",
        "source_type": "conference",
        "url": "https://www.smrp.org/conference",
    },
    {
        "name": "MAINSTREAM Summit",
        "source_type": "conference",
        "url": "https://www.maintenancesummit.com/sessions",
    },
    {
        "name": "Reliable Plant Conference",
        "source_type": "conference",
        "url": "https://www.reliableplant.com/conference",
    },
    {
        "name": "IMC / Reliabilityweb Conference",
        "source_type": "conference",
        "url": "https://reliabilityweb.com/imc",
    },
    {
        "name": "IAM Conference",
        "source_type": "conference",
        "url": "https://theiam.org/events",
    },
]


def run():
    db = SessionLocal()
    try:
        from app.models import Signal

        removed = 0
        for name in REMOVE_NAMES:
            src = db.query(Source).filter(Source.name == name).first()
            if src:
                # Delete child signals first to avoid FK / cascade issues
                deleted_sigs = db.query(Signal).filter(Signal.source_id == src.id).delete()
                db.delete(src)
                removed += 1
                print(f"  ✗ Removed: {name}  (deleted {deleted_sigs} signals)")
            else:
                print(f"  - Not found (skip): {name}")

        db.flush()

        renamed = 0
        all_sources = db.query(Source).all()
        for src in all_sources:
            new_type = TYPE_RENAMES.get(src.source_type)
            if new_type:
                src.source_type = new_type
                renamed += 1
                print(f"  ↷ Renamed type: {src.name}  {src.source_type!r} → {new_type!r}")

        added = 0
        for spec in NEW_PRACTITIONER_PUBS + NEW_CONFERENCES:
            exists = db.query(Source).filter(Source.name == spec["name"]).first()
            if not exists:
                db.add(Source(**spec))
                added += 1
                print(f"  + Added: {spec['name']} ({spec['source_type']})")
            else:
                print(f"  ~ Already exists: {spec['name']}")

        db.commit()
        print(f"\nDone. Removed={removed}, Renamed={renamed}, Added={added}")

    except Exception as exc:
        db.rollback()
        print(f"ERROR: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
