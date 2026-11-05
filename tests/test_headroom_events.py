"""HEADROOM limit-string parser (RA-8188, AR-02).

Every string below was seen on this estate (sources in scripts/headroom_events.py),
except the Codex usage-limit line, which is labelled `unverified`. Each test names the
why (W1..W5 in the PR body) it traces to.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import headroom_events as he  # noqa: E402

BNE = ZoneInfo("Australia/Brisbane")
NOW = datetime(2026, 10, 6, 14, 0, tzinfo=BNE).timestamp()

CURSOR_SPEND = ("You've hit your usage limit You've saved $1121 on API model usage this month "
                "with Pro+. Switch to a different model or set a Spend Limit to continue with this "
                "model. Your usage limits will reset when your monthly cycle ends on 10/6/2026.")
CURSOR_FREE = "You've hit your usage limit Get Cursor Pro for more Agent usage, unlimited Tab, and more."


def events(text, provider="claude", exit_code=1):
    return [(h["event"], h["pattern_id"]) for h in he.classify(text, provider, NOW, exit_code)]


# W1: the router can only skip an account it knows is cooling; each observed string maps.
def test_w1_claude_weekly_is_weekly_cooling():
    assert events("You've hit your weekly limit · resets Oct 9 at 1am (Australia/Brisbane)") == [
        ("weekly_cooling", "claude.quota")]


def test_w1_claude_session_limits_are_5h_cooling():
    for line in ("5-hour limit reached ∙ resets 3:30pm (Australia/Brisbane)",
                 "Claude usage limit reached. Your limit will reset at 5pm (Australia/Brisbane).",
                 "You've hit your usage limit · resets 11am (Australia/Brisbane)",
                 "Claude AI usage limit reached|1791000000"):
        assert events(line) == [("5h_cooling", "claude.quota")], line


def test_w1_reset_time_is_read_when_printed():
    hit = he.classify("5-hour limit reached ∙ resets 3:30pm (Australia/Brisbane)", "claude", NOW, 1)[0]
    assert hit["reset_at"] == datetime(2026, 10, 6, 15, 30, tzinfo=BNE).timestamp()


def test_w1_unreadable_reset_is_null_not_a_guess():
    # W5: a default hold must never look like a parsed reset time.
    hit = he.classify("You've hit your usage limit", "claude", NOW, 1)[0]
    assert hit["reset_at"] is None


def test_w1_cursor_spend_limit_is_on_demand_capped():
    assert events(CURSOR_SPEND, "cursor") == [("on_demand_capped", "cursor.spend_limit")]


def test_w1_cursor_json_turn_error_is_read():
    line = '{"type":"turn_ended","status":"error","error":"%s"}' % CURSOR_SPEND.replace("'", "\\u0027")
    assert events(line, "cursor") == [("on_demand_capped", "cursor.spend_limit")]


def test_w1_cursor_free_plan_is_billing_blocked():
    assert events(CURSOR_FREE, "cursor") == [("billing_blocked", "cursor.free_plan")]


def test_w1_claude_org_disabled_is_billing_blocked():
    assert events("Your organization has disabled Claude subscription access") == [
        ("billing_blocked", "claude.org_disabled")]


# W2: a dead login is a human sign-in job, never a cooling account and never a billing fact.
def test_w2_claude_login_expired_is_auth_expired():
    assert events("Login expired · Please run /login") == [("auth_expired", "claude.login_expired")]
    assert events("API Error: OAuth session expired and could not be refreshed") == [
        ("auth_expired", "claude.oauth_expired")]


def test_w2_codex_out_of_credits_is_auth_not_billing():
    hits = he.classify("ERROR: Your workspace is out of credits. Add credits to continue.", "codex", NOW, 0)
    assert [(h["event"], h["source"]) for h in hits] == [("auth_expired", "observed")]


def test_w2_codex_usage_limit_scans_despite_exit_zero_and_is_unverified():
    hits = he.classify("You've hit your usage limit. Try again at 3:45 PM.", "codex", NOW, 0)
    assert [(h["event"], h["source"]) for h in hits] == [("5h_cooling", "unverified")]


# W3: a false cooling event would make the router skip a healthy account.
def test_w3_quoted_mid_sentence_does_not_fire():
    assert events("The runner printed You've hit your weekly limit · resets Oct 9 and stopped.") == []


def test_w3_bulleted_quote_in_a_report_does_not_fire():
    assert events("- Login expired · Please run /login (seen at 11:56)") == []


def test_w3_clean_claude_exit_does_not_fire():
    assert events("You've hit your weekly limit · resets Oct 9 at 1am", exit_code=0) == []


def test_w3_unknown_exit_still_scans():
    assert events("Login expired · Please run /login", exit_code=None) == [
        ("auth_expired", "claude.login_expired")]


def test_w3_other_providers_patterns_do_not_cross():
    assert events(CURSOR_SPEND, "claude") == [("5h_cooling", "claude.quota")]
    assert events("Login expired · Please run /login", "cursor") == []


def test_w3_only_the_tail_is_read():
    text = "You've hit your weekly limit\n" + "ok\n" * (he.TAIL_LINES + 5)
    assert events(text) == []


def test_w3_ansi_and_curly_quote_do_not_hide_a_limit():
    assert events("\x1b[31mYou’ve hit your weekly limit · resets Oct 9 at 1am\x1b[0m") == [
        ("weekly_cooling", "claude.quota")]


def test_w3_repeated_line_gives_one_event():
    line = "Login expired · Please run /login\n"
    assert events(line * 3) == [("auth_expired", "claude.login_expired")]


def test_w3_unknown_provider_is_refused():
    try:
        he.classify("Login expired · Please run /login", "openrouter", NOW, 1)
    except ValueError:
        return
    raise AssertionError("an unknown provider must be refused, not scanned")


def test_w5_a_hit_carries_no_cli_text():
    # W5: nothing downstream can log the CLI's words if the parser never hands them on.
    hit = he.classify("You've hit your weekly limit · resets Oct 9 secret-like-value-do-not-log", "claude", NOW, 1)[0]
    assert set(hit) == {"event", "pattern_id", "source", "reset_at"}


# W4: the five event names are a fixed contract AR-03 reads.
def test_w4_event_names_are_exactly_the_five():
    assert set(he.EVENTS) == {"5h_cooling", "weekly_cooling", "auth_expired",
                              "billing_blocked", "on_demand_capped"}
    assert {p.event for p in he.PATTERNS} <= set(he.EVENTS)
    assert {p.source for p in he.PATTERNS} <= {"observed", "unverified"}
