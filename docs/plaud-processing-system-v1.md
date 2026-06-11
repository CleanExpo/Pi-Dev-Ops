# Plaud NotePin Processing System v1

## Overview

A Node.js API that receives recordings from Plaud NotePin devices, stores them in S3, routes them to company-configured AI experts for analysis, and delivers structured insights back to the originating company.

## Architecture

```
┌─────────────────┐     HTTP POST     ┌──────────────────┐     Upload     ┌─────────────┐
│ Plaud NotePin   │─────────────────────│  Node.js API     │────────────────│ AWS S3      │
│ (User Device)   │  sig + payload      │  /webhooks/plaud │                │ (Recordings)│
└─────────────────┘                     └──────────────────┘                └─────────────┘
                                               │
                                               │ Auth + Queue
                                               ▼
                                        ┌──────────────────┐
                                        │  Expert Router   │
                                        │  (Company → Expert)
                                        └──────────────────┘
                                               │
                                               │ Analysis Request
                                               ▼
                                        ┌──────────────────┐
                                        │  AI Expert Engine│
                                        │  (LLM Analysis)  │
                                        └──────────────────┘
                                               │
                                               │ Structured Insights
                                               ▼
                                        ┌──────────────────┐
                                        │  Delivery Service│
                                        │  (Webhook/Email/ └──────────────────┐
                                        │   Slack/Telegram)                  │
                                        └──────────────────┘                │
                                               │                              │
                                               ▼                              │
                                        ┌──────────────────┐              ┌──┴─────────────┐
                                        │ Company Endpoint │◄─────────────│ Insight Store  │
                                        │ (Receives results)              │ (S3 + DB)      │
                                        └──────────────────┘              └────────────────┘
```

## Database Schema

### `companies`
| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| name | VARCHAR(255) | Company name |
| plaud_api_key | VARCHAR(255) | Plaud API key for validation |
| webhook_url | VARCHAR(500) | Where to deliver insights |
| webhook_secret | VARCHAR(255) | HMAC secret for signing deliveries |
| expert_id | UUID | FK → experts.id |
| is_active | BOOLEAN | Enabled/disabled |
| created_at | TIMESTAMP | |

### `experts`
| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| name | VARCHAR(255) | Expert persona name |
| description | TEXT | What this expert does |
| system_prompt | TEXT | The LLM system prompt |
| analysis_config | JSONB | Model, temperature, output format |
| is_active | BOOLEAN | |

### `recordings`
| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| company_id | UUID | FK → companies |
| plaud_tsf_id | VARCHAR(255) | Plaud timestamp field ID |
| content | TEXT | Transcribed text |
| file_url | VARCHAR(500) | S3 URL |
| file_size | INTEGER | Bytes |
| duration_seconds | INTEGER | Recording length |
| recorded_at | TIMESTAMP | When user recorded |
| received_at | TIMESTAMP | When API received |

### `insights`
| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| recording_id | UUID | FK → recordings |
| expert_id | UUID | FK → experts |
| status | VARCHAR(50) | pending/processing/completed/failed |
| summary | TEXT | High-level summary |
| action_items | JSONB | Structured action items |
| sentiment | VARCHAR(50) | positive/neutral/negative |
| confidence | DECIMAL(3,2) | 0.00 - 1.00 |
| raw_response | JSONB | Full LLM response |
| delivered_at | TIMESTAMP | When sent to company |
| created_at | TIMESTAMP | |

## API Endpoints

### POST /webhooks/plaud
**Purpose:** Receives recordings from Plaud devices
**Auth:** HMAC-SHA256 signature in `X-Plaud-Signature` header
**Body:**
```json
{
  "tsf_id": "1748563200_abc123",
  "content": "Meeting notes about Q3 planning...",
  "file_url": "https://s3.plaud.ai/recordings/abc123.mp3",
  "file_size": 2458000,
  "duration_seconds": 180,
  "recorded_at": "2026-05-30T12:00:00Z",
  "company_api_key": "ug_live_abc123xyz789"
}
```

**Response:**
```json
{
  "success": true,
  "recording_id": "uuid-here",
  "status": "queued",
  "estimated_seconds": 30
}
```

### POST /experts
**Purpose:** Create new expert persona
**Auth:** Admin API key

### GET /experts/:id
**Purpose:** Get expert details

### POST /companies
**Purpose:** Register a company
**Auth:** Admin API key

### GET /companies/:id/insights
**Purpose:** Get all insights for a company
**Auth:** Company API key

## Security

1. **Plaud Webhook Validation**
   - HMAC-SHA256 of payload body
   - Compare against `X-Plaud-Signature` header
   - Reject if mismatch

2. **S3 Security**
   - Pre-signed URLs for uploads (15 min expiry)
   - Private bucket, no public access
   - SSE-S3 encryption at rest

3. **Expert Analysis Isolation**
   - Each company's data processed independently
   - No cross-company data leakage
   - LLM prompts scoped to expert's domain

## Expert Personas (Examples)

### Business Strategist
- **System Prompt:** You are a senior business strategy consultant with 20+ years experience. Analyze recordings for strategic insights, market opportunities, competitive threats, and actionable business recommendations.
- **Output Format:** Executive summary + 3-5 strategic recommendations + risk assessment

### Technical Architect
- **System Prompt:** You are a principal software architect. Analyze technical discussions for architecture decisions, tech debt, scalability concerns, and implementation risks.
- **Output Format:** Architecture summary + technical recommendations + feasibility rating

### Compliance Officer
- **System Prompt:** You are a regulatory compliance expert. Analyze conversations for compliance risks, policy gaps, audit findings, and remediation steps.
- **Output Format:** Compliance summary + findings + remediation priority matrix

### Sales Coach
- **System Prompt:** You are an elite sales performance coach. Analyze sales calls for technique, objections handling, closing opportunities, and coaching points.
- **Output Format:** Call score + key moments + improvement actions

### Meeting Facilitator
- **System Prompt:** You are a professional meeting facilitator. Analyze meetings for effectiveness, participation equity, decision clarity, and action item tracking.
- **Output Format:** Meeting effectiveness score + decisions made + action items + follow-ups

## Delivery Channels

1. **Webhook** (primary): POST structured JSON to company's webhook_url
2. **Email**: Send formatted report to configured addresses
3. **Slack**: Post to company Slack channel via webhook
4. **Telegram**: Send via bot to company chat
5. **Dashboard**: Store for retrieval via API/UI

## Implementation Phases

### Phase 1: Core Pipeline
- [ ] Webhook endpoint with Plaud auth
- [ ] S3 upload/fetch
- [ ] Recording storage (DB)
- [ ] Basic expert routing
- [ ] LLM analysis (OpenAI/Anthropic)
- [ ] Insight storage (DB + S3)

### Phase 2: Delivery
- [ ] Webhook delivery to companies
- [ ] Email formatting
- [ ] Retry logic for failed deliveries
- [ ] Delivery status tracking

### Phase 3: Scale
- [ ] Queue system (SQS/Bull)
- [ ] Expert marketplace (multiple experts per company)
- [ ] Analytics dashboard
- [ ] White-label options
