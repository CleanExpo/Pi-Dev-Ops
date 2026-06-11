import { NextRequest, NextResponse } from 'next/server';
import { getAdminClient } from '@/lib/supabase/admin';
import { requireAdmin } from '@/lib/security/require-admin';
import { ADD_ON_GATES } from '@/components/command-center/control-panel/control-panel-data';
import {
  buildCrmActivityTimelineEvent,
  buildCrmTimelineAgentActionInsert,
} from '@/lib/crm/activity-timeline';
import { ADD_ON_ASSIGNEE_TYPE } from './_assignee-type';

export const dynamic = 'force-dynamic';

type ExistingTask = {
  id: string;
  title: string;
  status: string;
  created_at: string | null;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function addOnFor(value: unknown) {
  if (!isRecord(value) || typeof value.addOnId !== 'string') return null;
  const addOnId = value.addOnId.trim();
  return ADD_ON_GATES.find((item) => item.id === addOnId) ?? null;
}

function taskDescription(addOn: (typeof ADD_ON_GATES)[number], actorEmail: string) {
  return [
    `Review add-on request: ${addOn.label}`,
    '',
    `Category: ${addOn.category}`,
    `Current state: ${addOn.state}`,
    `Approval rule: ${addOn.approval}`,
    `Requested by: ${actorEmail}`,
    '',
    'Safety gates:',
    '- No add-on can self-enable from the Control Panel.',
    '- Approval task must stay blocked until a human decision is recorded.',
    '- Synthex receives only marketing/campaign work.',
    '- Unite CRM remains the source of truth.',
  ].join('\n');
}

export async function POST(req: NextRequest) {
  const gate = await requireAdmin(req);
  if (gate instanceof NextResponse) return gate;

  const workspaceId = process.env.UNITE_CRM_WORKSPACE_ID?.trim();
  if (!workspaceId) {
    return NextResponse.json({ error: 'crm_not_configured' }, { status: 503 });
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'invalid_json' }, { status: 400 });
  }

  const addOn = addOnFor(body);
  if (!addOn) return NextResponse.json({ error: 'invalid_add_on' }, { status: 400 });

  const obsidianPath = `command-center/add-ons/${addOn.id}`;
  const tags = [
    'hermes-addon-request',
    'approval-required',
    'unite-crm',
    addOn.id,
    addOn.category,
  ];

  try {
    const admin = getAdminClient();
    const existing = await admin
      .from('tasks')
      .select('id,title,status,created_at')
      .eq('workspace_id', workspaceId)
      .eq('obsidian_path', obsidianPath)
      .neq('status', 'done')
      .limit(1)
      .maybeSingle();

    if (existing.error) {
      return NextResponse.json({ error: 'crm_lookup_failed' }, { status: 500 });
    }

    if (existing.data) {
      const task = existing.data as ExistingTask;
      return NextResponse.json(
        {
          ok: true,
          existing: true,
          crm_task_id: task.id,
          task_title: task.title,
          task_status: task.status,
          requested_at: task.created_at,
        },
        { headers: { 'Cache-Control': 'no-store' } },
      );
    }

    const inserted = await admin
      .from('tasks')
      .insert({
        workspace_id: workspaceId,
        title: `Approve add-on: ${addOn.label}`,
        description: taskDescription(addOn, gate.actorEmail),
        status: 'blocked',
        priority: 'high',
        assignee_type: ADD_ON_ASSIGNEE_TYPE,
        assignee_name: 'Phill approval',
        tags,
        position: 0,
        obsidian_path: obsidianPath,
      })
      .select('id,title,status,created_at')
      .single();

    if (inserted.error || !inserted.data?.id) {
      console.error('[add-ons] tasks insert failed');
      return NextResponse.json({ error: 'crm_task_insert_failed' }, { status: 500 });
    }

    try {
      const timelineInsert = buildCrmTimelineAgentActionInsert(buildCrmActivityTimelineEvent({
        type: 'approval_requested',
        actor: 'Margot',
        subjectId: inserted.data.id,
        subjectLabel: addOn.label,
        occurredAt: inserted.data.created_at ?? new Date().toISOString(),
        source: 'command_center_add_on_request',
        requiresApproval: true,
        metadata: {
          addOnId: addOn.id,
          category: addOn.category,
          taskStatus: inserted.data.status,
        },
      }));
      const timelineResult = await admin.from('agent_actions').insert(timelineInsert);
      if (timelineResult.error) console.error('[add-ons] CRM timeline insert failed');
    } catch {
      console.error('[add-ons] CRM timeline insert failed');
    }

    return NextResponse.json(
      {
        ok: true,
        existing: false,
        crm_task_id: inserted.data.id,
        task_title: inserted.data.title,
        task_status: inserted.data.status,
        requested_at: inserted.data.created_at,
      },
      { headers: { 'Cache-Control': 'no-store' } },
    );
  } catch {
    return NextResponse.json({ error: 'crm_unavailable' }, { status: 503 });
  }
}
