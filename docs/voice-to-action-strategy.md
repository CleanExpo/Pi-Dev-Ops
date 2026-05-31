# Voice-to-Action Pipeline: Personal Recording Strategy

## Overview

A dedicated pipeline to capture Phill's thoughts, ideas, and decisions via voice, process them through a specialized "Personal Intelligence" expert, and route actionable insights back to the correct project or personal knowledge base.

```
Plaud NotePin (Capture)
    ↓ (Plaud AI Transcription)
Plaud Cloud (Transcript + Audio)
    ↓ (Webhook)
Plaud Processor API (/webhooks/plaud)
    ↓ (Personal Intelligence Analysis)
Structured Insights (Action Items, Decisions, Ideas)
    ↓ (Router)
├─→ Linear (Tasks for specific projects)
├─→ Pi-CEO Brain (Strategic knowledge)
├─→ Telegram (Immediate alerts)
└─→ Email (Daily digest)
```

## 1. Capture Strategy (The Recording Discipline)

### When to Record
- **Immediate:** Any idea, decision, or thought that feels important. Don't wait.
- **During Calls:** Use Plaud to record key decisions and action items from meetings.
- **While Driving / Walking:** Capture reflections and strategic thinking.
- **Before Sleep:** Capture end-of-day thoughts and tomorrow's priorities.

### How to Record (The 'Prompting' Technique)
Since the Plaud NotePin listens continuously, you don't need to 'start' a recording. However, to ensure the AI understands the context, begin your thought with a **clear intent marker**:

- **"DECISION:"** — For firm decisions that need to be actioned.
- **"IDEA:"** — For new ideas or concepts to explore later.
- **"TASK:"** — For specific tasks that need to be done.
- **"PROJECT [Name]:"** — To associate the thought with a specific project.
- **"STRATEGY:"** — For high-level strategic thoughts.
- **"NOTE:"** — For general observations or information.

**Example Recordings:**
- "DECISION: We are shifting RestoreAssist to a client-local deployment model. This will reduce our infrastructure costs and appeal more to enterprise clients."
- "IDEA: Create a deployment abstraction layer in Pi-Dev-Ops so all projects can be cloud or local."
- "TASK: Fix the cron job for the ecosystem health check. It's firing too often."
- "PROJECT RestoreAssist: Need to design the update mechanism for the self-hosted version."

### Why This Works
By prefixing your thoughts, you eliminate ambiguity for the AI. It doesn't have to guess if something is a task, an idea, or a decision. It knows immediately how to categorize and process it.

## 2. The Personal Intelligence Expert

This is a specialized expert configured in the `plaud-processor` specifically for you.

### Expert Profile
- **Name:** `Phill's Personal Intelligence`
- **Description:** Processes Phill's voice recordings to extract decisions, ideas, tasks, and strategic insights. Routes them to the correct project or knowledge base.

### System Prompt
```
You are Phill McGurk's Personal Intelligence assistant. Your job is to process his voice recordings and extract structured, actionable insights.

Phill is the CEO of Unite Group, a technology holding company. His portfolio includes:
- RestoreAssist (Compliance/Restoration Platform)
- Pi-Dev-Ops (Internal DevOps Dashboard)
- Synthex (Social Media/Content Engine)
- CCW-CRM (Clean Craft Works ERP)
- And other projects under the Unite-Group umbrella.

The North Star goal is $2B by 2028-06-30.

### Instructions ###

1.  **Identify the Intent:** Look for intent markers at the beginning of the transcript (DECISION, IDEA, TASK, PROJECT, STRATEGY, NOTE).
    - If no marker is found, infer the intent based on the content.

2.  **Extract the Core Message:** Remove filler words, repetitions, and verbal stumbles. Summarize the core thought in 1-2 clear sentences.

3.  **Categorize:**
    - **Decision:** Something Phill has decided. Needs to be recorded and potentially actioned.
    - **Idea:** A new concept or possibility. Needs to be evaluated later.
    - **Task:** A specific action to be taken. Needs a due date if mentioned.
    - **Project Context:** Which project does this relate to? (RestoreAssist, Pi-Dev-Ops, Synthex, CCW-CRM, General/Unite-Group)

4.  **Generate Action Items:**
    - If it's a task, create a clear action item.
    - If it's a decision, create an action item to document the decision in the appropriate place (e.g., a decision log, project wiki).
    - If it's an idea, create an action item to 'Evaluate idea: [summary]'.
    - If it's strategic, create an action item to 'Discuss strategy: [summary]'.

5.  **Assess Priority:**
    - **P0 (Critical):** Directly impacts the North Star goal. Immediate action required.
    - **P1 (High):** Important for a specific project or strategic objective. Action within 48 hours.
    - **P2 (Medium):** Useful but not urgent. Action within 1 week.
    - **P3 (Low):** Nice to have. Can be deferred.

6.  **Determine Sentiment:** Is Phill excited, concerned, frustrated, or neutral about this topic?

### Output Format ###
Return ONLY valid JSON with this structure:
{
  "intents": ["decision", "idea", "task"], // Can be multiple
  "project": "RestoreAssist", // Or 'General', 'Unite-Group', etc.
  "summary": "Clear 1-2 sentence summary.",
  "action_items": [
    {
      "task": "Clear description of the action.",
      "project": "Project name",
      "priority": "P0/P1/P2/P3",
      "due": "YYYY-MM-DD or null",
      "context": "Why this matters."
    }
  ],
  "sentiment": "positive/negative/neutral",
  "confidence": 0.95, // 0.00-1.00
  "tags": ["tag1", "tag2"],
  "raw_transcript_summary": "Brief summary of the full transcript for context."
}
```

## 3. Routing & Delivery

After analysis, insights are delivered based on priority and project:

| Priority | Delivery Method | Example |
|----------|-----------------|---------|
| P0 | Immediate Telegram alert + Email | Critical decision affecting $2B goal |
| P1 | Linear ticket created + Email within 1 hour | High-priority task for a project |
| P2 | Daily email digest | Medium-priority ideas and evaluations |
| P3 | Weekly summary email | Low-priority notes and observations |

### Telegram Alert Format (P0)
```
🚨 P0 INSIGHT — RestoreAssist

Decision recorded: Shift to client-local deployment.

Actions:
- [RA-5642] Strategic ticket already created.
- [ ] Design update mechanism (P1)
- [ ] Assess feasibility (P1)

Confidence: 95% | Sentiment: Positive
```

### Daily Email Digest (P1/P2)
```
Phill's Daily Insights — 2026-05-30

## P1 — Action Required
[RestoreAssist] Evaluate competitive landscape for self-hosted SaaS.
[Pi-Dev-Ops] Build deployment abstraction layer spec.

## P2 — Evaluate Soon
[General] Consider a "white-label" option for RestoreAssist.
[CCW-CRM] Explore franchise model requiring local deployment.

## Notes & Observations
- Noticed strong interest in data privacy from enterprise clients.
- Potential channel partner opportunity for DR-Sandbox.
```

## 4. Integration with Existing Systems

### Linear
- P0/P1 insights automatically create Linear tickets in the correct project.
- Tickets are tagged with `from-voice` and linked back to the Plaud recording.

### Pi-CEO Brain
- Strategic insights (STRATEGY, high-level DECISIONs) are saved to:
  - `/Users/phillmcgurk/Pi-CEO/brain/strategy/`
  - `/Users/phillmcgurk/Pi-CEO/brain/plaud/`
- These files are markdown with Obsidian-compatible frontmatter for easy linking.

### Obsidian Vault (if applicable)
- The structured insights can be synced to your Obsidian vault under a specific `Voice Notes` folder.
- Use Obsidian's graph view to see connections between ideas over time.

## 5. Continuous Improvement

The system learns from your feedback:
- If you frequently mark certain types of insights as "not relevant," the expert's prompt is adjusted.
- If a certain project is consistently mentioned, the routing rules are refined.
- The system will track which insights resulted in actual action (via Linear/Github activity) and which remained dormant, helping to tune the priority model.

## Next Steps

1.  **Configure the 'Phill' Company in Plaud Processor:**
    - Register a company for yourself in the `plaud-processor`.
    - Assign the `Phill's Personal Intelligence` expert.
    - Set your webhook URL to your Telegram bot or email endpoint.

2.  **Connect Plaud webhook:**
    - In your Plaud dashboard, set the webhook URL to your processor's `/webhooks/plaud` endpoint.
    - Use the `company_api_key` for your personal company.

3.  **Start Recording:**
    - Use the intent markers for a week.
    - Review the daily digests.
    - Refine the expert's prompt based on what works and what doesn't.

4.  **Iterate:**
    - This is a living system. The more you use it, the better it gets.
