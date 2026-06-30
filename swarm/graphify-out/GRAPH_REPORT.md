# Graph Report - swarm  (2026-06-08)

## Corpus Check
- 105 files · ~93,606 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1842 nodes · 3319 edges · 73 communities (70 shown, 3 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 40 edges (avg confidence: 0.75)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]

## God Nodes (most connected - your core abstractions)
1. `handle_turn()` - 24 edges
2. `_process_one()` - 18 edges
3. `_load_business_ids()` - 18 edges
4. `send()` - 18 edges
5. `atomic_write_json()` - 17 edges
6. `propose_idea()` - 17 edges
7. `Path` - 16 edges
8. `Path` - 16 edges
9. `run_debate()` - 15 edges
10. `Any` - 14 edges

## Surprising Connections (you probably didn't know these)
- `handle_dispatch()` --calls--> `_run()`  [INFERRED]
  board/wiring.py → kanban_adapter.py
- `approve_spend()` --calls--> `post_draft()`  [INFERRED]
  cfo.py → draft_review.py
- `approve_adspend()` --calls--> `post_draft()`  [INFERRED]
  cmo.py → draft_review.py
- `approve_refund()` --calls--> `post_draft()`  [INFERRED]
  cs.py → draft_review.py
- `approve_pr_merge()` --calls--> `post_draft()`  [INFERRED]
  cto.py → draft_review.py

## Import Cycles
- 1-file cycle: `bots/cfo.py -> bots/cfo.py`
- 1-file cycle: `bots/cmo.py -> bots/cmo.py`
- 1-file cycle: `bots/cs.py -> bots/cs.py`
- 1-file cycle: `bots/cto.py -> bots/cto.py`
- 1-file cycle: `portfolio_pulse_github.py -> portfolio_pulse_github.py`
- 1-file cycle: `meta_curator.py -> meta_curator.py`
- 1-file cycle: `six_pager_dispatcher.py -> six_pager_dispatcher.py`
- 1-file cycle: `intent_router.py -> intent_router.py`
- 1-file cycle: `providers/github_actions.py -> providers/github_actions.py`
- 1-file cycle: `training/hf_traces.py -> training/hf_traces.py`

## Communities (73 total, 3 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (67): append_turn(), _audit(), BoardTrigger, build_context(), build_prompt(), build_prompt_with_research(), _call_llm(), _ccw_state_summary() (+59 more)

### Community 1 - "Community 1"
Cohesion: 0.05
Nodes (49): _bump_version(), _entry_to_dict(), export(), _extract_dependencies(), _extract_safety(), _load_previous_manifest(), _parse_frontmatter(), Any (+41 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (54): _append_to_wiki(), Bot, _file_to_linear(), _is_authorized(), load_registry(), poll_bot(), _process_update(), Any (+46 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (51): bubus_enabled(), dispatch(), Env-flag gateway: legacy sentinel-string dispatch vs bubus typed dispatch.  DORM, Check the BUBUS_ENABLED env flag at call time., Route to bubus or legacy dispatch based on env flag., Persona, Pi-CEO Board personas — 9-persona deliberation per ceo-board skill.  Wave 5.4 Ph, BoardDecision (+43 more)

### Community 4 - "Community 4"
Cohesion: 0.06
Nodes (49): _char_split(), _chunk(), deliver_to_telegram(), _extract_synthesis(), _maybe_compose_synthesis_voice(), Path, swarm/portfolio_pulse_telegram.py — RA-1893 (child of RA-1409).  Telegram delive, Return the cross-portfolio synthesis section body, or None.      The synthesis s (+41 more)

### Community 5 - "Community 5"
Cohesion: 0.06
Nodes (48): list, build_pulse(), get_lookback_hours(), _load_sibling_providers(), lookback_window(), PortfolioPulseRun, _pulse_path(), PulseResult (+40 more)

### Community 6 - "Community 6"
Cohesion: 0.07
Nodes (46): AdSpendDecision, append_snapshot(), approve_adspend(), assemble_daily_brief(), ChannelSpend, compute_metrics(), detect_breaches(), load_last_snapshot() (+38 more)

### Community 7 - "Community 7"
Cohesion: 0.08
Nodes (47): _existing_linear_titles(), GapResult, _parse_action_items(), Path, swarm/gap_detector.py — wiki action queue → Linear tickets.  Runs once per day., Fuzzy match: is this title close enough to an existing ticket?, Scan wiki action queues and file Linear tickets for unaddressed gaps.      Calle, True if gap detection hasn't run today. (+39 more)

### Community 8 - "Community 8"
Cohesion: 0.08
Nodes (44): append_snapshot(), approve_refund(), assemble_daily_brief(), compute_metrics(), CsBreach, CsMetrics, detect_breaches(), load_last_snapshot() (+36 more)

### Community 9 - "Community 9"
Cohesion: 0.11
Nodes (46): accept_proposal(), _append_jsonl(), _build_skill_prompt(), _bump_rate(), Cluster, _cluster_id(), _compose_skill_body_via_claude_print(), _compose_skill_body_via_sdk() (+38 more)

### Community 10 - "Community 10"
Cohesion: 0.10
Nodes (44): assemble_brief(), _audit(), BoardBrief, BoardSession, _call_ceo_board_sdk(), deliberate(), Directive, _directives_path() (+36 more)

### Community 11 - "Community 11"
Cohesion: 0.08
Nodes (39): _audit_file(), _config(), _langfuse_post(), _maybe_redact(), _now_iso(), Any, Path, swarm/audit_emit.py — RA-1839: Centralised, schema-enforced audit boundary.  Sin (+31 more)

### Community 12 - "Community 12"
Cohesion: 0.09
Nodes (38): _api_key(), _gql(), _kill_switch_active(), list_issues(), Any, swarm/linear_tools.py — RA-1839: Linear flow tools.  Wraps the Linear GraphQL AP, List issues in a team. `state` filter is a state-name substring., Create a new Linear issue. Returns {id, identifier, url} on success.      `prior (+30 more)

### Community 13 - "Community 13"
Cohesion: 0.15
Nodes (38): GoalStatus, abort_goal(), advance_goal(), _audit(), _channel_top_share_below_70(), check_resolution(), create_goal(), cycle_due() (+30 more)

### Community 14 - "Community 14"
Cohesion: 0.09
Nodes (37): _completed_dir(), _load_processed(), _processed_log(), Path, swarm/sources_watcher.py — auto-ingest new Brain-1 Sources/ clips.  Runs every o, Return set of filenames already ingested (stem only, for rename-safety)., Check Sources/ for new clips and ingest them.      Safe to call every orchestrat, run_cycle() (+29 more)

### Community 15 - "Community 15"
Cohesion: 0.10
Nodes (36): first_client_first_response_alert(), first_client_first_response_critical(), is_first_client(), list_first_clients(), swarm/client_priority.py — first-client elevation across senior bots.  A flat en, Read ``TAO_FIRST_CLIENTS`` (comma-separated business_ids).      Defaults to ``cc, True when the business should get top-of-brief + tightened SLA., Tightened first-response warning threshold in minutes for first     clients. Def (+28 more)

### Community 16 - "Community 16"
Cohesion: 0.10
Nodes (33): _append_audit(), _audit_file(), _builtins(), _config(), execute_flow(), _kill_switch_active(), _load_state(), _lookup() (+25 more)

### Community 17 - "Community 17"
Cohesion: 0.11
Nodes (35): ci_provider(), ci_summary(), deploys_provider(), _gh_get(), _load_projects(), _no_repo_section(), _no_token_section(), _parse_iso() (+27 more)

### Community 18 - "Community 18"
Cohesion: 0.09
Nodes (33): _atomic_write_queue(), _default_greeting(), _import_telethon(), _insert_context_bot(), load_queue(), _login(), _mint_one(), mint_queue() (+25 more)

### Community 19 - "Community 19"
Cohesion: 0.06
Nodes (10): BuildPromptTests, ClaudePrintSummariseTests, ListActiveContextsTests, OpenrouterSummariseTests, Tests for swarm.inbox.preamble_trainer., Verify the Max-first → Chinese-OS → Gemini cascade per     `[[feedback-model-rou, SplitPreambleAndEntitiesTests, SummariseCascadeTests (+2 more)

### Community 20 - "Community 20"
Cohesion: 0.11
Nodes (29): Hit, _classify_via_claude_print(), _ClassifyError, default_classifier(), _make_classifier_with_anthropic(), _parse_spans(), Wraps a single-tier failure so the cascade can fall through cleanly., Tier 0 — `claude --print` ($0 marginal under Max). Raises on failure. (+21 more)

### Community 21 - "Community 21"
Cohesion: 0.10
Nodes (27): append_snapshot(), approve_spend(), assemble_daily_brief(), Breach, compute_metrics(), detect_breaches(), load_last_snapshot(), Metrics (+19 more)

### Community 22 - "Community 22"
Cohesion: 0.11
Nodes (29): Finding, _call_perplexity(), _default_notebooklm_caller(), _default_perplexity_caller(), _ledger_today_key(), _load_ledger(), _load_notebook_map(), _looks_like_no_signal() (+21 more)

### Community 23 - "Community 23"
Cohesion: 0.12
Nodes (28): date, _apply_slug(), _call_llm(), _check_contradictions(), _check_cross_refs(), _check_orphans(), _check_stale(), _decay_threshold() (+20 more)

### Community 24 - "Community 24"
Cohesion: 0.11
Nodes (28): build_prompt(), _claude_print_summarise(), entities_path(), fetch_messages(), _gemini_api_key(), _gemini_summarise(), list_active_contexts(), _openrouter_summarise() (+20 more)

### Community 25 - "Community 25"
Cohesion: 0.11
Nodes (15): Path, DryRunTests, PersistenceTests, QueueSeedTests, RateLimitParseTests, RateLimitTests, Tests for swarm.inbox.botfather_minter.  Mocks urllib.request.urlopen (for the S, Mid-write SIGKILL must not corrupt the queue file. We simulate this         by m (+7 more)

### Community 26 - "Community 26"
Cohesion: 0.18
Nodes (26): _append_jsonl(), _audit_swarm_jsonl(), _config(), _do_send(), _drafts_jsonl(), _drafts_snapshot(), expire_overdue(), list_pending() (+18 more)

### Community 27 - "Community 27"
Cohesion: 0.14
Nodes (26): _build_fix_prompt(), _dispatch_specialist(), _fetch_open_work_orders(), FixJob, _guess_specialist(), _jobs_log(), _load_active_jobs(), _ollama_triage() (+18 more)

### Community 28 - "Community 28"
Cohesion: 0.13
Nodes (24): append_snapshot(), approve_pr_merge(), assemble_daily_brief(), _classify_dora(), compute_metrics(), detect_breaches(), load_last_snapshot(), _now_iso() (+16 more)

### Community 29 - "Community 29"
Cohesion: 0.15
Nodes (7): BuildDay0PortalContentTests, _client(), ProvisionOneTests, _queue_row(), Tests for swarm.inbox.provisioner (Hour-1 portal worker).  Mocks every external, ResolveBrandCandidatesTests, TickTests

### Community 30 - "Community 30"
Cohesion: 0.11
Nodes (22): _default_metrics_provider(), _gates_open(), _is_daily_fire_window(), _is_test_mode(), datetime, RawMetrics, swarm/bots/cfo.py — RA-1850 (Wave 4.1): CFO senior-agent bot.  Per-cycle job:, True when TAO_DRAFT_REVIEW_TEST=1 — same flag draft_review uses. (+14 more)

### Community 31 - "Community 31"
Cohesion: 0.15
Nodes (9): _bot(), _http_response(), LoadRegistryTests, PollBotTests, ProcessUpdateTests, Tests for swarm.inbox.intake_router.  Mocks urllib.request.urlopen so the suite, Build a fake context-manager response for urlopen., TickTests (+1 more)

### Community 32 - "Community 32"
Cohesion: 0.15
Nodes (13): CycleCooldownTests, DeDupePrevScopedTests, FetchAmbiguousTicketsTests, GroundedResearchDepthTests, GroundedResearchFallbackTests, PerTicketErrorContainmentTests, Path, Tests for swarm.pm_scoper — Senior PM Scoping Bot. (+5 more)

### Community 33 - "Community 33"
Cohesion: 0.14
Nodes (18): _log_observation(), swarm/bots/guardian.py — RA-650: Guardian Bot.  Responsibilities:   - Monitor sw, Append a structured observation to the Guardian JSONL log., Execute one Guardian observation cycle.      Checks:       1. Ollama service liv, run_cycle(), effective_max_daily_prs(), swarm/config.py — RA-650: Autonomous AI Swarm configuration.  All behaviour is c, Return the auto-clamped daily-PR cap. RA-3019.      Reads `.harness/swarm/green_ (+10 more)

### Community 34 - "Community 34"
Cohesion: 0.13
Nodes (21): by_provider_24h(), by_role_24h(), check_ceiling(), daily_total_usd(), _iter_rows(), _log_path(), Any, Path (+13 more)

### Community 35 - "Community 35"
Cohesion: 0.15
Nodes (21): finance_section_provider(), FinanceFigures, _fmt_usd(), _gather_figures(), provider(), Any, Path, PulseSection (+13 more)

### Community 36 - "Community 36"
Cohesion: 0.14
Nodes (21): _bid_key(), Any, RawMetrics, swarm/providers/stripe_xero.py — production CFO metrics provider.  Pulls real nu, One Xero GET. Raises on HTTP error so caller can fall back.      Xero OAuth 2.0, Pull (cash_on_hand_usd, cogs_window_usd, revenue_window_usd) from Xero.      Rea, Walk the Xero report rows tree to find a row whose Title matches one     of ``ro, Build RawMetrics for one business from Stripe + Xero. None on failure.      Stri (+13 more)

### Community 37 - "Community 37"
Cohesion: 0.09
Nodes (21): client_display_name, client_slug, completion, linear_tag_on_ready, on_all_answered_fire, phill_review_block_minutes, synthesis_outputs, delivery (+13 more)

### Community 38 - "Community 38"
Cohesion: 0.12
Nodes (19): AdSpendDecision, _default_marketing_provider(), _gates_open(), _is_daily_fire_window(), _is_test_mode(), datetime, RawMarketingMetrics, swarm/bots/cmo.py — RA-1860 (Wave 4 A2): CMO / Growth senior-agent bot.  Per-cyc (+11 more)

### Community 39 - "Community 39"
Cohesion: 0.14
Nodes (20): add_comment(), block_card(), complete_card(), create_card(), emit_debate_card(), _hermes_bin(), KanbanCard, list_open() (+12 more)

### Community 40 - "Community 40"
Cohesion: 0.14
Nodes (19): _active_build_ticket_ids(), _assess_ticket(), _fetch_buildable_tickets(), _fire_build(), _increment_pr_counter(), _log_cycle(), swarm/bots/builder.py — RA-650-C: Builder Bot.  Responsibilities:   - Scan Linea, Ask Ollama to assess build eligibility and draft a brief for a ticket.      Retu (+11 more)

### Community 41 - "Community 41"
Cohesion: 0.17
Nodes (18): _build_proposals(), EnhancementProposal, _file_as_board_agenda(), Path, _queue_board_briefing(), swarm/enhancement_scout.py — autonomous enhancement discovery agent.  Continuous, Find tasks still on paid APIs that could move to Gemma 4., File each enhancement as a Board agenda item in Linear. (+10 more)

### Community 42 - "Community 42"
Cohesion: 0.22
Nodes (19): _append_history(), _config(), _flag_file(), _history_file(), is_active(), is_locked(), _lock_file(), _now_iso() (+11 more)

### Community 43 - "Community 43"
Cohesion: 0.21
Nodes (19): _create_label(), _ensure_label(), fetch_ambiguous_tickets(), _label_id_for(), _linear_gql(), _load_state(), post_comment(), swarm/pm_scoper.py — Senior PM Scoping Bot.  Closes the autonomy gap identified (+11 more)

### Community 44 - "Community 44"
Cohesion: 0.16
Nodes (19): _classify_closed(), _fetch_movement(), _format_priority(), linear_section_provider(), _load_projects(), Any, Path, swarm/portfolio_pulse_linear.py — RA-1890 (child of RA-1409).  Linear-movement s (+11 more)

### Community 45 - "Community 45"
Cohesion: 0.16
Nodes (8): CascadeOrderTests, ClaudePrintTierTests, _cluster(), PromptSharedTests, Tests for the meta_curator SKILL.md composition cascade.  Locks the Max-first mi, Both tiers must use the same prompt — extracted into _build_skill_prompt., Tier 0 — `claude --print` (free under Max plan)., `_draft_skill_md_stub` must try tier 0 before tier 1 before template.

### Community 46 - "Community 46"
Cohesion: 0.10
Nodes (5): CascadeTests, ClaudePrintTierTests, ParseSpansTests, Tests for swarm.pii_classify cascade.  Lock the Max-first cost-strategy migratio, End-to-end: default_classifier wires tier 0 → tier 1 correctly.

### Community 47 - "Community 47"
Cohesion: 0.26
Nodes (18): _cli_main(), export_to_env(), load_token(), needs_refresh(), _post_token_endpoint(), Any, Path, swarm/oauth_refresh.py — OAuth refresh-token sidecar.  Production credential man (+10 more)

### Community 48 - "Community 48"
Cohesion: 0.14
Nodes (17): _default_platform_provider(), _gates_open(), _is_daily_fire_window(), _is_test_mode(), datetime, RawPlatformMetrics, swarm/bots/cto.py — RA-1861 (Wave 4 A3): CTO senior-agent bot.  Same shape as cf, Public entry-point: any bot/agent requesting a production PR merge.      Auto-ap (+9 more)

### Community 49 - "Community 49"
Cohesion: 0.16
Nodes (17): classify(), classify_llm(), _has_pii(), _is_margot_dm_chat(), _luhn_ok(), _parse_relative_date(), Any, datetime (+9 more)

### Community 50 - "Community 50"
Cohesion: 0.18
Nodes (17): _compute_dora(), _gh_get(), github_actions_provider(), _load_repo_for_business(), _parse_iso(), Any, datetime, RawPlatformMetrics (+9 more)

### Community 51 - "Community 51"
Cohesion: 0.15
Nodes (16): _default_cs_provider(), _gates_open(), _is_daily_fire_window(), _is_test_mode(), datetime, RawCsMetrics, swarm/bots/cs.py — RA-1862 (Wave 4 A4): CS-tier1 senior-agent bot.  Same shape a, Public entry-point — refunds <= $100 auto-approve, above route HITL. (+8 more)

### Community 52 - "Community 52"
Cohesion: 0.16
Nodes (15): _fetch_linear_stalled(), _log_drafts(), swarm/bots/scribe.py — RA-650-D: Scribe Bot.  Responsibilities:   - Monitor Line, Read unprocessed entries from .harness/lessons.jsonl.      Args:         since_t, Append a Scribe observation to the JSONL log., Execute one Scribe observation cycle.      Checks:       1. Linear for stalled I, Fetch In Progress tickets not updated in >24h from Linear REST API.      Returns, _read_new_lessons() (+7 more)

### Community 53 - "Community 53"
Cohesion: 0.16
Nodes (13): _poll_telegram(), Any, swarm/bots/chief_of_staff.py — RA-1839: Chief of Staff swarm bot.  Polls Telegra, Route a classified intent to the right specialist. Returns action dict., One CoS cycle: poll Telegram, classify, route, return summary., Pull Telegram updates after `state_offset`. Returns (messages, new_offset)., _route(), run_cycle() (+5 more)

### Community 54 - "Community 54"
Cohesion: 0.19
Nodes (15): _assemble_brief(), BriefingResult, _nlm_create_or_update_notebook(), _nlm_generate_audio(), Path, swarm/visual_briefing.py — 4x daily visual briefings via NotebookLM + Telegram., Create or update a NotebookLM notebook with the briefing content. Returns notebo, Generate audio overview for the notebook. Returns path to audio file. (+7 more)

### Community 55 - "Community 55"
Cohesion: 0.22
Nodes (14): acknowledge(), all_pending_counts(), consume_for(), _cursor_key(), pending_count_for(), Any, Path, swarm/board_directive_consumer.py — RA-1868 senior-bot directive consumer.  Seni (+6 more)

### Community 56 - "Community 56"
Cohesion: 0.19
Nodes (14): _check_kill_switch(), _load_state(), _poll_telegram_for_ack(), Path, swarm/orchestrator.py — RA-650: Pi-CEO Autonomous Swarm Orchestrator.  Entry poi, Return True if the daily 08:00 AEST report is due., Main orchestrator loop — runs until killed or kill-switch fires., Re-read TAO_SWARM_ENABLED + .harness/swarm/kill_switch.flag every cycle.      Re (+6 more)

### Community 57 - "Community 57"
Cohesion: 0.31
Nodes (6): Tests for swarm.training.hf_traces — the labelled-corpus capture layer., RecordTests, _reload(), SummariseTests, UploadGuardTests, Path

### Community 58 - "Community 58"
Cohesion: 0.23
Nodes (12): _call_llm(), _identify_pages(), Path, query(), QueryResult, swarm/wiki_query.py — wiki-query skill implementation.  Queries the Brain-1 wiki, Ask LLM to answer the query from the loaded page content., Query the Brain-1 wiki.      Args:         query_text:      The question to answ (+4 more)

### Community 59 - "Community 59"
Cohesion: 0.23
Nodes (11): escalate(), from_founder(), from_margot(), list_pending(), Any, Path, queue_depth(), swarm/bots/board.py — request-driven Board entry-point for senior bots.  Thin wr (+3 more)

### Community 60 - "Community 60"
Cohesion: 0.24
Nodes (11): _check_local_health(), _check_railway_health(), _http_get(), _log_cycle(), swarm/bots/click.py — RA-650-E: Click Bot.  Responsibilities:   - Poll Pi-Dev-Op, Poll the Railway-deployed Pi-Dev-Ops /health endpoint if configured.      Uses P, Append a Click observation to the JSONL log., Execute one Click observation cycle.      Checks:       1. Local Pi-Dev-Ops /hea (+3 more)

### Community 61 - "Community 61"
Cohesion: 0.26
Nodes (11): _business_type(), RawMetrics, swarm/providers/synthetic.py — deterministic CFO metrics provider.  Reads ``.har, Deterministic provider — one RawMetrics per business in projects.json., Deterministic non-negative int from (business_id, salt)., Deterministic float in [lo, hi] from (business_id, salt)., Generate one plausible RawMetrics for a business id., _scale() (+3 more)

### Community 62 - "Community 62"
Cohesion: 0.24
Nodes (11): _path_for(), Any, datetime, Path, swarm/training/hf_traces.py — labelled-corpus assembly for the Q3 PEFT LoRA expe, If HF_TOKEN is set, batch-upload the last N days of traces to HF Datasets., Append one trace row. Safe to call concurrently — JSONL append-only.      Trunca, Count traces per worker + per task. Used by the corpus-growth dashboard. (+3 more)

### Community 63 - "Community 63"
Cohesion: 0.31
Nodes (10): _load_business_ids(), RawPlatformMetrics, swarm/providers/synthetic_platform.py — deterministic CTO platform provider.  Re, Deterministic provider — one RawPlatformMetrics per business., _scale(), _seed_int(), _synth_one(), synthetic_platform_one() (+2 more)

### Community 64 - "Community 64"
Cohesion: 0.40
Nodes (4): _audit(), _Any, Compatibility package for the legacy ``swarm.board`` module plus submodules.  PR, Best-effort audit emit — never raises.

### Community 65 - "Community 65"
Cohesion: 0.50
Nodes (3): Test fixtures for the bubus typed-event surface (DORMANT)., Stub ``provider_ollama.call`` so wiring imports without a live daemon., _stub_provider_ollama()

## Knowledge Gaps
- **60 isolated node(s):** `Any`, `Path`, `Any`, `_Any`, `Directive` (+55 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_run()` connect `Community 39` to `Community 27`, `Community 9`, `Community 3`?**
  _High betweenness centrality (0.072) - this node is a cross-community bridge._
- **Why does `handle_dispatch()` connect `Community 3` to `Community 39`?**
  _High betweenness centrality (0.070) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `atomic_write_json()` (e.g. with `.test_atomic_write_json_round_trip()` and `.test_atomic_write_json_with_trailing_newline()`) actually correct?**
  _`atomic_write_json()` has 6 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Tests for swarm._atomic — crash-safe file write helper.  The contract under test`, `If json.dumps raises mid-write, the OLD file must survive.`, `Simulate disk-full / SIGKILL between tmp write and os.replace.` to the rest of the system?**
  _673 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.0601404741000878 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.05257936507936508 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.06291591046581972 - nodes in this community are weakly interconnected._