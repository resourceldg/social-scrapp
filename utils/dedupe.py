from __future__ import annotations

from typing import Dict, List

from models import Lead


def _merge(existing: Lead, incoming: Lead) -> Lead:
    for field_name in existing.__dataclass_fields__.keys():
        current = getattr(existing, field_name)
        new = getattr(incoming, field_name)
        if field_name == "interest_signals":
            setattr(existing, field_name, sorted(set((current or []) + (new or []))))
            continue
        if field_name == "raw_data":
            merged = {**(current or {}), **(new or {})}
            setattr(existing, field_name, merged)
            continue
        if (not current) and new:
            setattr(existing, field_name, new)
    return existing


def dedupe_leads(leads: List[Lead]) -> List[Lead]:
    registry: Dict[str, Lead] = {}
    output: List[Lead] = []

    for lead in leads:
        keys = [
            f"url:{lead.profile_url.lower()}" if lead.profile_url else "",
            f"handle:{lead.social_handle.lower()}" if lead.social_handle else "",
            f"email:{lead.email.lower()}" if lead.email else "",
        ]
        keys = [k for k in keys if k]

        matched = None
        for key in keys:
            if key in registry:
                matched = registry[key]
                break

        if matched:
            merged = _merge(matched, lead)
            for key in keys:
                registry[key] = merged
        else:
            output.append(lead)
            for key in keys:
                registry[key] = lead

    return output
