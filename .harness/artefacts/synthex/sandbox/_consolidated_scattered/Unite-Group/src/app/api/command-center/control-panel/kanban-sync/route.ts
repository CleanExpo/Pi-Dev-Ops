import { NextRequest, NextResponse } from 'next/server';
import { getAdminClient } from '@/lib/supabase/admin';
import { requireAdmin } from '@/lib/security/require-admin';

export const dynamic = 'force-dynamic';

type TaskRow = {
  id: string;
  title: string;
  description: string | null;
  status: string;
  priority: string | null;
  tags: string[] | null;
  assignee_name: string | null;
  obsidian_path: string | null;
  obsidian_synced_at: string | null;
  updated_at: string | null;
  created_at: string | null;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function syncDue(task: TaskRow) {
  if (['done', 'closed', 'complete', 'completed'].includes(task.status.toLowerCase())) {
    return false;
  }
  if (!task.obsidian_synced_at) return true;

  const updatedAt = task.updated_at ?? task.created_at;
  if (!updatedAt) return true;

  return new Date(updatedAt).getTime() > new Date(task.obsidian_synced_at).getTime();
}

function laneFor(task: TaskRow) {
  const tags = task.tags ?? [];
  if (tags.includes('margot-voice')) return 'voice-intake';
  if (tags.includes('hermes-addon-request')) return 'add-on-approval';
  if (tags.includes('approval-required')) return 'approval-gate';
  return 'crm-task';
}

function bodyFor(task: TaskRow) {
  return [
    task.description ?? task.title,
    '',
    `CRM task: ${task.id}`,
    `CRM status: ${task.status}`,
    `Priority: ${task.priority ?? 'normal'}`,
    `Assignee: ${task.assignee_name ?? 'unassigned'}`,
    `Source path: ${task.obsidian_path ?? 'none'}`,
    '',
    'Safety gates:',
    '- Unite CRM remains source of truth.',
    '- No Kanban done state without evidence attached to the CRM task.',
    '- Synthex receives only marketing/campaign work.',
  ].join('\n');
}

function toSyncPacket(task: TaskRow) {
  return {
    crmTaskId: task.id,
    idempotencyKey: `unite-crm-${task.id}`,
    title: task.title,
    lane: laneFor(task),
    status: task.status,
    priority: task.priority ?? 'normal',
    assignee: task.assignee_name ?? 'Pi-CEO',
    tags: task.tags ?? [],
    obsidianPath: task.obsidian_path,
    updatedAt: task.updated_at ?? task.created_at,
    kanban: {
      title: task.title,
      body: bodyFor(task),
      status: task.status === 'blocked' ? 'blocked' : 'triage',
      priority: task.priority === 'high' ? 100 : 80,
    },
  };
}

function response(payload: Record<string, unknown>, status = 200) {
  return NextResponse.json(payload, {
    status,
    headers: { 'Cache-Control': 'no-store' },
  });
}

export async function GET(req: NextRequest) {
  const gate = await requireAdmin(req);
  if (gate instanceof NextResponse) return gate;

  const workspaceId = process.env.UNITE_CRM_WORKSPACE_ID?.trim();
  if (!workspaceId) return response({ error: 'crm_not_configured' }, 503);

  try {
    const admin = getAdminClient();
    const { data, error } = await admin
      .from('tasks')
      .select('id,title,description,status,priority,tags,assignee_name,obsidian_path,obsidian_synced_at,updated_at,created_at')
      .eq('workspace_id', workspaceId)
      .order('updated_at', { ascending: false, nullsFirst: false })
      .limit(100);

    if (error) return response({ error: 'crm_read_failed' }, 500);

    const tasks = ((data ?? []) as TaskRow[]).filter(syncDue).map(toSyncPacket);
    return response({
      source: 'crm:kanban-sync',
      generatedAt: new Date().toISOString(),
      pendingCount: tasks.length,
      tasks,
    });
  } catch {
    return response({ error: 'crm_unavailable' }, 503);
  }
}

export async function POST(req: NextRequest) {
  const gate = await requireAdmin(req);
  if (gate instanceof NextResponse) return gate;

  const workspaceId = process.env.UNITE_CRM_WORKSPACE_ID?.trim();
  if (!workspaceId) return response({ error: 'crm_not_configured' }, 503);

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return response({ error: 'invalid_json' }, 400);
  }

  if (!isRecord(body) || !Array.isArray(body.taskIds)) {
    return response({ error: 'invalid_packet' }, 400);
  }

  const taskIds = body.taskIds.filter((id): id is string => typeof id === 'string' && !!id.trim());
  if (taskIds.length === 0) return response({ error: 'invalid_packet' }, 400);

  const syncedAt = typeof body.syncedAt === 'string' ? body.syncedAt : new Date().toISOString();

  try {
    const admin = getAdminClient();
    const { error } = await admin
      .from('tasks')
      .update({ obsidian_synced_at: syncedAt })
      .eq('workspace_id', workspaceId)
      .in('id', taskIds);

    if (error) return response({ error: 'crm_update_failed' }, 500);

    return response({
      ok: true,
      syncedAt,
      taskIds,
    });
  } catch {
    return response({ error: 'crm_unavailable' }, 503);
  }
}
