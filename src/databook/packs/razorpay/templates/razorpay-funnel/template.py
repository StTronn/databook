"""razorpay-funnel template: builds the what-if model; with --demo also writes synthetic exports."""
from pathlib import Path

from openpyxl import Workbook


def build_whatif(path: Path) -> None:
    wb = Workbook()
    inp = wb.active
    inp.title = "Inputs"
    for row in (["Input", "Value", "Source"],
                ["Card payments (month)", 0, "card.payments"],
                ["Current card success", 0, "card.success_rate"],
                ["Target card success", 0.75, "assumption: edit me"],
                ["Avg paid order value (INR)", 0, "aov.inr"]):
        inp.append(row)
    for c in ("B3", "B4"):
        inp[c].number_format = "0.0%"
    m = wb.create_sheet("Model")
    for row in (["What-if: card success", ""],
                ["Card payments / month", "=Inputs!B2"],
                ["Current success", "=Inputs!B3"],
                ["Target success", "=Inputs!B4"],
                ["Extra successful payments", "=ROUND(B2*(B4-B3),0)"],
                ["Avg paid order value", "=Inputs!B5"],
                ["Monthly uplift (INR)", "=B5*B6"]):
        m.append(row)
    for c, f in (("B3", "0.0%"), ("B4", "0.0%"), ("B6", "#,##0"), ("B7", "#,##0")):
        m[c].number_format = f
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def setup(root: Path, demo: bool = False) -> list[str]:
    build_whatif(root / "models" / "whatif.xlsx")
    created = ["models/whatif.xlsx"]
    if demo:
        from databook.packs.razorpay.demo import generate, write_exports
        created += write_exports(generate(), root / "data")
    return created
