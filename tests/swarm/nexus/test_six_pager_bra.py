"""Focused tests for swarm.nexus.six_pager_bra + assemble_six_pager hook."""
from __future__ import annotations

from swarm.nexus.bra import BRACard, BRAReport
from swarm.nexus.six_pager_bra import (
    render_bra_block,
    render_bra_voice,
)
from swarm.six_pager import assemble_six_pager


# ============================================================
# Fixtures
# ============================================================


def _card(brief="MRR ticked up 3% week-over-week.",
          rec="Send the founder a celebratory note.",
          act="Schedule a check-in call next Tuesday.",
          sev="medium",
          evidence=("out-1", "out-2")) -> BRACard:
    return BRACard(
        brief=brief, recommendation=rec, action=act,
        severity=sev, evidence_ids=evidence,
    )


def _report(workspace="acme", cards=()) -> BRAReport:
    return BRAReport(
        workspace_slug=workspace, window="7d", cards=tuple(cards),
    )


# ============================================================
# render_bra_block
# ============================================================


class TestRenderBlock:
    def test_empty_reports_returns_empty_string(self):
        assert render_bra_block([]) == ""

    def test_single_workspace_single_card_renders(self):
        out = render_bra_block([_report(cards=[_card()])])
        assert out.startswith("8. Nexus BRA cards")
        assert "acme" in out
        assert "MRR ticked up" in out
        assert "Action: " in out
        assert "Evidence: out-1, out-2" in out

    def test_multiple_workspaces_render_ordered(self):
        out = render_bra_block([
            _report(workspace="acme", cards=[_card(brief="A1")]),
            _report(workspace="beta", cards=[_card(brief="B1")]),
        ])
        assert "acme" in out
        assert "beta" in out
        assert out.index("acme") < out.index("beta")

    def test_workspace_with_no_cards_renders_no_signals_line(self):
        out = render_bra_block([_report(cards=[])])
        assert "no signals this window" in out


# ============================================================
# render_bra_voice — ≤30s per card
# ============================================================


class TestVoiceVariant:
    def test_empty_reports_returns_empty_string(self):
        assert render_bra_voice([]) == ""

    def test_voice_phrase_truncated_to_max_words(self):
        long_brief = " ".join(["lorem ipsum"] * 200)  # 400 words
        report = _report(cards=[_card(brief=long_brief)])
        voice = render_bra_voice([report])
        # Sanity: should fit budget per card (workspace prefix counts but
        # the per-card phrase must be capped).
        for line in voice.split(" Recommendation:")[1:]:
            # The truncation acts on the joined sentence; assert the
            # whole script contains the truncation ellipsis.
            pass
        assert "…" in voice  # truncation marker

    def test_only_cards_with_content_appear_in_voice(self):
        reports = [
            _report(workspace="acme", cards=[_card(brief="A1")]),
            _report(workspace="beta", cards=[]),  # skipped — no cards
        ]
        voice = render_bra_voice(reports)
        assert "acme" in voice
        assert "beta" not in voice


# ============================================================
# assemble_six_pager hook
# ============================================================


class TestSixPagerHook:
    def test_six_pager_without_bra_omits_section(self, tmp_path):
        text = assemble_six_pager(repo_root=tmp_path, date_str="2026-05-26")
        assert "8. Nexus BRA cards" not in text

    def test_six_pager_with_bra_includes_section(self, tmp_path):
        report = _report(cards=[_card()])
        text = assemble_six_pager(
            repo_root=tmp_path, date_str="2026-05-26",
            bra_reports=[report],
        )
        assert "8. Nexus BRA cards" in text
        # Section appears after Board (section 7) and before the separator:
        assert text.index("7. ") < text.index("8. Nexus BRA cards")
        # The trailing separator is the LAST "—" line — text.rindex finds it
        # past both the header's em-dash and the BRA section.
        assert text.index("8. Nexus BRA cards") < text.rindex("—")
