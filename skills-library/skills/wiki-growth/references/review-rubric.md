# Review-board rubric — the challenge questions and disposition labels

Single source of truth for wiki-growth triage. Subagent prompts inline the ten questions
verbatim; the disposition labels are defined only here (the routing table maps them, it
does not redefine them).

## Stance

Act as a senior review board. Do not agree with the note by default — the note earns its
disposition. Every verdict cites evidence from the note itself or from named vault/repo
context; a claim with no evidence is `UNSUPPORTED` and weakens the idea.

## The ten questions (ask all ten per idea)

1. Is this idea clear?
2. Is it commercially useful?
3. Is it technically possible?
4. Is it source-backed?
5. Is it too vague?
6. Is it already duplicated elsewhere (another note, an existing skill, an existing repo capability)?
7. Is there a better existing framework?
8. Is it ready for implementation, research, training, marketing — or retirement?
9. What would a sceptical expert challenge?
10. What would fail in the real world?

Answer each as PASS / FAIL / UNKNOWN plus one sentence of evidence. Three or more FAILs
on questions 1–7 pushes the disposition toward `Archive` or `Research`, never toward a
promote label.

## Disposition labels (exactly one per idea)

| Label | Meaning |
|---|---|
| Keep | Sound as-is; no action beyond retaining. |
| Strengthen | Core is right; needs sharper framing, structure, or missing sections. |
| Research | Claims need real sources before the idea can be trusted. |
| Merge | Same proposal as another note; name the survivor note. |
| Split | Two+ ideas in one note; name the split lines. |
| Archive | Superseded, disproven, or not worth the upkeep; say why. |
| Turn into skill | Ready to become a Claude skill. |
| Turn into SOP | Ready to become a written operating procedure. |
| Turn into training module | Ready to become teachable material (CARSI-style). |
| Turn into product feature | Ready to become a spec for a portfolio product. |
| Turn into marketing asset | Ready to become campaign/content material. |

## Row format returned by each triage subagent

```
{ note: <vault-relative path>,
  idea: <one line>,
  verdicts: {q1..q10: PASS|FAIL|UNKNOWN + evidence},
  disposition: <one label above>,
  why: <2-3 sentences, sceptic's summary>,
  high_stakes: true|false  # spend, prod change, or new build implied
}
```
