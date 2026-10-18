"""Independent arithmetic oracle for the M01 comparable-window rehearsal."""

import csv
from datetime import date
from decimal import Decimal

from scripts.testing.run_p7_browser_rehearsal import _write_fixtures


def test_action_fixture_has_comparable_windows_and_real_cost_inputs(tmp_path):
    inbox = tmp_path / "workspace" / "inbox"
    inbox.mkdir(parents=True)
    _write_fixtures(tmp_path)
    with (inbox / "F-ACTION.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    windows = (
        (date(2026, 9, 7), date(2026, 9, 13)),
        (date(2026, 9, 14), date(2026, 9, 20)),
    )
    expected = (
        {"amount": 700, "campaign_cost": 140, "net_contribution": 560, "orders": 70},
        {"amount": 770, "campaign_cost": 175, "net_contribution": 595, "orders": 77},
    )
    assert len(rows) == 14
    for row in rows:
        assert Decimal(row["net_contribution"]) == (
            Decimal(row["amount"]) - Decimal(row["campaign_cost"])
        )
    for (start, end), totals in zip(windows, expected):
        selected = [row for row in rows if start <= date.fromisoformat(row["date"]) <= end]
        assert len(selected) == 7
        assert {column: sum(Decimal(row[column]) for row in selected)
                for column in totals} == totals
    assert expected[1]["net_contribution"] - expected[0]["net_contribution"] == 35
    assert Decimal(expected[0]["campaign_cost"]) / expected[0]["orders"] == 2
    assert Decimal(expected[1]["campaign_cost"]) / expected[1]["orders"] == Decimal(175) / 77
