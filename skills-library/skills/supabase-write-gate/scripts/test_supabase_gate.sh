#!/bin/zsh
# Positive AND negative controls for the Supabase write gate.
# A gate that only ever blocks is as useless as one that only ever permits.
H=/Users/phillmcgurk/.claude/hooks/PreToolUse/supabase_write_gate.py
pass=0; fail=0

check() {  # name, expected_exit, json
  print -n "  $1 ... "
  print -r -- "$3" | /usr/bin/env python3 $H >/dev/null 2>&1
  got=$?
  if [[ "$got" == "$2" ]]; then print "OK (exit $got)"; ((pass++))
  else print "*** WRONG: expected $2, got $got"; ((fail++)); fi
}

print "MUST BLOCK (exit 2):"
check "apply_migration"          2 '{"tool_name":"mcp__claude_ai_Supabase__apply_migration","tool_input":{"project_id":"udooysjajglluvuxkijp","query":"CREATE TABLE x();"}}'
check "deploy_edge_function"     2 '{"tool_name":"mcp__claude_ai_Supabase__deploy_edge_function","tool_input":{"project_id":"udooysjajglluvuxkijp"}}'
check "delete_branch"            2 '{"tool_name":"mcp__claude_ai_Supabase__delete_branch","tool_input":{"project_id":"lksfwktwtmyznckodsau"}}'
check "pause_project"            2 '{"tool_name":"mcp__claude_ai_Supabase__pause_project","tool_input":{"project_id":"znyjoyjsvjotlzjppzal"}}'
check "execute_sql DROP"         2 '{"tool_name":"mcp__claude_ai_Supabase__execute_sql","tool_input":{"project_id":"p","query":"DROP TABLE \"Foo\";"}}'
check "execute_sql UPDATE"       2 '{"tool_name":"mcp__claude_ai_Supabase__execute_sql","tool_input":{"project_id":"p","query":"UPDATE \"User\" SET x=1;"}}'
check "execute_sql SELECT;DROP"  2 '{"tool_name":"mcp__claude_ai_Supabase__execute_sql","tool_input":{"project_id":"p","query":"SELECT 1; DROP TABLE \"Foo\";"}}'
check "execute_sql CTE-write"    2 '{"tool_name":"mcp__claude_ai_Supabase__execute_sql","tool_input":{"project_id":"p","query":"WITH d AS (DELETE FROM \"User\" RETURNING *) SELECT * FROM d;"}}'
check "execute_sql empty"        2 '{"tool_name":"mcp__claude_ai_Supabase__execute_sql","tool_input":{"project_id":"p","query":"   "}}'
check "malformed payload"        2 'not json at all'
print "DEFAULT-DENY (a tool that does not exist yet):"
check "future_write_tool"        2 '{"tool_name":"mcp__claude_ai_Supabase__obliterate_everything","tool_input":{"project_id":"p"}}'

print ""
print "MUST PERMIT (exit 0):"
check "list_projects"            0 '{"tool_name":"mcp__claude_ai_Supabase__list_projects","tool_input":{}}'
check "list_migrations"          0 '{"tool_name":"mcp__claude_ai_Supabase__list_migrations","tool_input":{"project_id":"p"}}'
check "get_advisors"             0 '{"tool_name":"mcp__claude_ai_Supabase__get_advisors","tool_input":{"project_id":"p"}}'
check "execute_sql SELECT"       0 '{"tool_name":"mcp__claude_ai_Supabase__execute_sql","tool_input":{"project_id":"p","query":"SELECT count(*) FROM \"User\";"}}'
check "execute_sql CTE-read"     0 '{"tool_name":"mcp__claude_ai_Supabase__execute_sql","tool_input":{"project_id":"p","query":"WITH t AS (SELECT 1 AS a) SELECT * FROM t;"}}'
check "execute_sql EXPLAIN"      0 '{"tool_name":"mcp__claude_ai_Supabase__execute_sql","tool_input":{"project_id":"p","query":"EXPLAIN SELECT 1;"}}'
check "non-supabase tool"        0 '{"tool_name":"mcp__railway__list_projects","tool_input":{}}'
check "Bash untouched"           0 '{"tool_name":"Bash","tool_input":{"command":"git status"}}'

print ""
print "pass=$pass fail=$fail"
[[ $fail -eq 0 ]] || exit 1

print ""
print "BREAK-GLASS (found broken on first real use: branch tools carry branch_id, not project_id):"
G="$HOME/.claude/.supabase-write-approved.json"
[[ -f "$G" ]] && mv "$G" "$G.testbak"
FUTURE=$(python3 -c 'import time;print(int(time.time())+600)')

check "delete_branch, no grant"        2 '{"tool_name":"mcp__claude_ai_Supabase__delete_branch","tool_input":{"branch_id":"BR-1"}}'
print '{"branch_id":"BR-1","expires_at":'"$FUTURE"',"reason":"test"}' > "$G"
check "delete_branch, grant matches"   0 '{"tool_name":"mcp__claude_ai_Supabase__delete_branch","tool_input":{"branch_id":"BR-1"}}'
check "delete_branch, grant for other" 2 '{"tool_name":"mcp__claude_ai_Supabase__delete_branch","tool_input":{"branch_id":"BR-2"}}'
print '{"branch_id":"BR-1","expires_at":1,"reason":"expired"}' > "$G"
check "grant expired"                  2 '{"tool_name":"mcp__claude_ai_Supabase__delete_branch","tool_input":{"branch_id":"BR-1"}}'
print 'not json' > "$G"
check "grant malformed"                2 '{"tool_name":"mcp__claude_ai_Supabase__delete_branch","tool_input":{"branch_id":"BR-1"}}'
rm -f "$G"
[[ -f "$G.testbak" ]] && mv "$G.testbak" "$G"

print ""
print "TOTAL pass=$pass fail=$fail"
[[ $fail -eq 0 ]] || exit 1
