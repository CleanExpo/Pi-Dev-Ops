# TurboQuant Assessment for Pi-CEO

**Date:** 2026-04-12
**Question:** Can Google's TurboQuant help Pi-CEO compress memory to assist with what we're building for each business?
**Short answer:** Not directly — it solves a different problem than the one we have. But the conversation is the right one to have, because Pi-CEO absolutely does have a memory-compression problem, and there's a better tool for it.

---

## What TurboQuant actually is (not what the name suggests)

The repo at `tonbistudio/turboquant-pytorch` is a community PyTorch implementation of the ICLR 2026 paper *"TurboQuant: Online Vector Quantization with Near-optimal Distortion Rate"* by researchers at Google. It's real, it's well-regarded, and the technique is genuinely interesting.

What it does: it compresses the **KV cache** of a running transformer language model. The KV cache is the block of numbers an LLM uses to remember everything it's read so far in a prompt — the "attention state." Normally each number is stored in 16-bit floating point (FP16). TurboQuant squeezes those 16 bits down to 2-4 bits per number using a two-step trick:

1. Rotate each vector by a random orthogonal matrix so the distribution of values becomes a predictable bell curve.
2. Quantize each rotated coordinate to the nearest of a small number of precomputed centroids (Lloyd-Max quantization), with more bits assigned to "key" vectors and fewer to "value" vectors — because keys decide attention and errors in them hurt more.

The practical result: a model that would normally handle an 8,000-token context can now handle 16,000-40,000 tokens in the same GPU memory. Accuracy stays high, sometimes with perfect text generation even at 3x compression.

## What problem TurboQuant is designed to solve

**GPU memory constraints during LLM inference.** If you run Llama-70B or similar on your own hardware and want to stuff more context into the prompt without paying for bigger GPUs, TurboQuant lets you cheat the memory budget.

## What problem Pi-CEO actually has

**Semantic memory management for a fleet of per-project Claude agents.** When Pi-CEO spins up a session to work on CCW, it needs to bring the agent up to speed on:

- The Pi-CEO Standard (the seven pillars)
- CCW's specific charter and roadmap
- The latest Pi-SEO scan findings for CCW
- The last 30 days of Linear activity for CCW
- The house style from CCW's `CLAUDE.md`
- The open PRs and their review comments
- The lessons from `.harness/lessons.jsonl` that are relevant to this work

That's a lot of text. It easily exceeds the Claude context window if dumped in raw. And we don't want to dump it raw anyway — most of it is irrelevant to any given ticket.

So the Pi-CEO memory problem is: **given a new task, select and condense the right background context so the agent starts with a tight, relevant briefing instead of a wall of text.**

## Why TurboQuant doesn't solve that problem

Five reasons, any one of which would be enough:

1. **It operates on the wrong layer.** TurboQuant compresses model internals (KV cache). Pi-CEO compresses business data (markdown files, Linear issues, scan JSON) BEFORE it reaches the model. Different layer, different toolbox.
2. **We don't run the model.** Anthropic runs Claude on their servers and we hit the API. We never touch a KV cache — that's Anthropic's business, not ours. We can't apply TurboQuant to a black-box API.
3. **It needs an NVIDIA CUDA GPU.** Pi-CEO runs on Railway (CPU-only dynos) and in Cowork sandboxes (also CPU). Neither has the CUDA compute TurboQuant assumes.
4. **It's a research-grade PyTorch library.** The README is candid that TurboQuant V3 is still being validated, that the original paper's QJL correction "doesn't work for LLM attention," and that the implementation has been patched by six community teams. That's fine for research but not where we want our production memory system.
5. **Our bottleneck isn't model memory, it's relevance.** Even if Claude had unlimited context, we wouldn't want to pump every scan file and every Linear comment into every session. That wastes tokens and dilutes the agent's focus. The goal is a smart *selector*, not a better *compressor*.

## The related-but-different insight we should steal from TurboQuant

The TurboQuant paper's core idea — rotate-then-quantize — is a general trick for compressing high-dimensional vectors without destroying their geometry. That trick actually IS useful for Pi-CEO, just in a completely different context: **embedding-based retrieval** for the business memory store.

If we build a semantic retrieval system for Pi-CEO (see "What we should actually build" below), it will use embeddings. Embedding stores get big fast — 1,536-dimensional FP32 vectors are 6KB each, and a few thousand documents per project times several projects means hundreds of megabytes of vectors. Rotate-then-quantize compression could cut that 4-8x with negligible accuracy loss. That's a useful byproduct, but it's an optimization for later, not a reason to pull in TurboQuant now.

## What we SHOULD actually build for Pi-CEO "per-business memory"

This is the real answer to Phill's question. Strip the name TurboQuant out of it — what we need is a **per-project memory layer** that feeds the right context to each session.

### The four pieces

**1. Per-project knowledge base on disk**

One folder per project, under a stable location that Railway can read (not `.harness/` in an ephemeral sandbox). Structure:

```
memory/
  ccw/
    charter.md
    scan-latest.json
    lessons-relevant.jsonl
    linear-recent.jsonl
    house-style.md
  restoreassist/
    ...
  disaster-recovery/
    ...
```

Size budget: aim for ≤ 50KB per project of high-signal text. That's what a "compressed business memory" looks like in practice.

**2. A retrieval step that runs before every session**

When the autonomy poller decides to fire a session on CCW ticket RA-597, it first runs a retrieval step:

- Read the ticket title and description
- Embed the query into a vector (using OpenAI's `text-embedding-3-small` or a small local model — not the expensive ones)
- Do a similarity search against CCW's chunked knowledge base
- Return the top N chunks (N = 10-15, total ≤ 8KB)
- Prepend those chunks to the session's system prompt

This is classic RAG (retrieval-augmented generation). It's boring. It works. It solves exactly the problem Pi-CEO has.

**3. Summarization for the long-running history**

Linear issue histories, PR review comments, and board meeting minutes are append-only and grow without bound. Every week, a scheduled job runs over each project's history and produces a `summary.md` that condenses the last 30 days into 1-2 pages. Old detail doesn't get deleted, it just gets demoted to a secondary tier the retrieval step only touches when the summary isn't enough.

This is where "compression" literally happens — but it's semantic summarization, not bitwise quantization. The model you use for the summarization can be a cheap one (Claude Haiku or Gemini Flash), because the summary gets reviewed once a week by the agent or by Phill.

**4. Embedding compression (the TurboQuant-adjacent optimization, later)**

Once the knowledge base grows beyond a few megabytes per project, the vectors start to matter. At that point, we apply a rotate-then-quantize pass to shrink them 4-8x with tiny accuracy loss. The technique behind TurboQuant's KV quantization is the right idea — just applied to embeddings rather than attention state. Libraries like `faiss` already support this (product quantization, scalar quantization) and are battle-tested on production retrieval systems.

**Order of implementation:** 1 → 2 → 3 → 4. Don't skip ahead. The first version can have literally zero embedding compression and still work — Pi-CEO's data volume is small enough today that the optimization doesn't matter until we have years of history.

## Concrete first step (this week)

One small deliverable that makes the whole picture real:

Create `memory/pi-dev-ops/charter.md` — a 1-page summary of what Pi-CEO is, what it's for, what's in the codebase, and what the house rules are. Wire it into the build session startup so every Pi-Dev-Ops session begins with that charter in context. Measure: does the agent's first response for any ticket feel better informed than the current baseline?

If yes, clone the pattern to `memory/ccw/charter.md`, `memory/restoreassist/charter.md`, `memory/disaster-recovery/charter.md`. We already have the charters from the overnight marathon — the hard work of authoring them is done. We just need to move them into the memory layer and hook them into the session creation path.

Total cost: 4 hours. No GPUs required. No PyTorch. No research-grade library. No TurboQuant.

## The two-sentence verdict on TurboQuant

TurboQuant is a real, clever, useful piece of research for people running their own LLMs on CUDA hardware who need to stretch a context window. Pi-CEO isn't one of those people, so the right answer is to build a per-project RAG memory layer now and revisit rotate-then-quantize embedding compression only when the vector store grows big enough to care.

Thank you for flagging it, though — the underlying intuition (compress high-dimensional signals by pre-conditioning them) is exactly the right intuition for where Pi-CEO is heading, just applied to a different layer of the stack than the one TurboQuant targets.
