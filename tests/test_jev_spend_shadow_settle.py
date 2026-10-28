"""A paid shadow reply survives its own ledger failing at settle time (RA-8116 review round 1, P1).

The reply has already been paid for when finish_call runs. If the shadow's own ledger cannot be written then,
the receipt must still come back exactly once and the machine ledger row must still settle at the real price."""
from scripts import mission_control_jev_shadow as shadow
from tests.jev_spend_support import PRICE, SHADOW_SNAP, rows, shadow_reply


def test_shadow_returns_the_paid_reply_and_settles_the_machine_row_when_its_own_ledger_breaks(tmp_path, capsys):
    legacy = tmp_path / "jev-shadow-ledger.sqlite"
    opened = []

    def opener(req, timeout):
        opened.append(1)
        legacy.unlink()
        legacy.mkdir()  # the shadow's own ledger is now unwritable for the settle
        return shadow_reply(700)

    receipt = shadow.run_line(SHADOW_SNAP, live=True, key="k", ledger=legacy, opener=opener)
    assert opened == [1]
    assert receipt.get("reason") is None and receipt["input_tokens"] == 700
    (canon,) = rows()
    assert canon["status"] == "answered" and canon["actual_usd"] == 700 * PRICE
    assert "own ledger settle failed" in capsys.readouterr().err
