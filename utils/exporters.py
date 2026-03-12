from __future__ import annotations

import json
from pathlib import Path
from typing import List

import pandas as pd

from models import Lead


def export_leads(leads: List[Lead], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = [lead.to_dict() for lead in leads]
    pd.DataFrame(records).to_csv(output_dir / "leads.csv", index=False)
    (output_dir / "leads.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
