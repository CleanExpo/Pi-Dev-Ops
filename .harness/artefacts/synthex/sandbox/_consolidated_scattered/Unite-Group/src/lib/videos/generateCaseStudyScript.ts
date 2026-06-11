import { trackPipelineCost, calculateCostUsd } from '@/lib/pipelines/track-cost';

export interface CaseStudyScript {
  intro: string;       // ~10s (~25 words)
  results: string;     // ~20s (~50 words)
  quote: string;       // ~10s (~25 words)
  cta: string;         // ~10s (~25 words)
  full_script: string; // concatenated
}

export async function generateCaseStudyScript(
  client_id: string,
  clientName: string,
  digestData: {
    avg_engagement_rate: number;
    best_platform: string;
    top_content_types: string[];
  }
): Promise<CaseStudyScript> {
  const engagementPct = (digestData.avg_engagement_rate * 100).toFixed(1);

  const prompt = `You are writing a YouTube Short script (60-90 seconds) for a case study featuring ${clientName}, a Synthex client.

Performance data:
- Average engagement rate: ${engagementPct}%
- Best platform: ${digestData.best_platform}
- Top content types: ${digestData.top_content_types.join(', ')}

Write exactly 4 sections as JSON:
{
  "intro": "10-second opener about who ${clientName} is and the challenge they faced (max 25 words)",
  "results": "20-second results highlight with the actual engagement metrics above (max 50 words)",
  "quote": "10-second client quote or paraphrase about the transformation (max 25 words)",
  "cta": "10-second call to action for viewers to try Synthex (max 25 words)"
}

Be specific and concrete. Use the actual numbers. Sound authentic, not salesy.`;

  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'x-api-key': process.env.ANTHROPIC_API_KEY!,
      'anthropic-version': '2023-06-01',
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      model: 'claude-haiku-4-5-20251001',
      max_tokens: 800,
      messages: [{ role: 'user', content: prompt }],
    }),
  });

  const data = await res.json();
  const rawText = data?.content?.[0]?.text ?? '{}';

  // Extract JSON from response
  const jsonMatch = rawText.match(/\{[\s\S]*\}/);
  let script: Omit<CaseStudyScript, 'full_script'>;

  try {
    script = JSON.parse(jsonMatch?.[0] ?? '{}');
  } catch {
    script = {
      intro: `${clientName} needed a smarter way to grow their online presence.`,
      results: `With Synthex, they achieved ${engagementPct}% average engagement on ${digestData.best_platform}.`,
      quote: `"Synthex transformed how we show up online." — ${clientName}`,
      cta: 'Ready to build your digital authority? Try Synthex today.',
    };
  }

  const full_script = [script.intro, script.results, script.quote, script.cta].join('\n\n');

  // Track cost using the exact trackPipelineCost signature
  const inputTokens = data?.usage?.input_tokens ?? 0;
  const outputTokens = data?.usage?.output_tokens ?? 0;
  const model = 'claude-haiku-4-5-20251001';

  await trackPipelineCost({
    pipeline_name: 'case_study_script_generation',
    client_id,
    run_id: `case-study-${client_id}-${Date.now()}`,
    model,
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    cost_usd: calculateCostUsd(model, inputTokens, outputTokens),
  });

  return { ...script, full_script };
}
