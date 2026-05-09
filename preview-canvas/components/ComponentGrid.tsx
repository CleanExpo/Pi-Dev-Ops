import { resolveToken, type DesignTokens } from '@/lib/loadSpecs';

function recipeStyle(tokens: DesignTokens, recipe: Record<string, string | undefined>) {
  const s: Record<string, string | undefined> = {};
  if (recipe.backgroundColor) s.background = resolveToken(tokens, recipe.backgroundColor);
  if (recipe.textColor) s.color = resolveToken(tokens, recipe.textColor);
  if (recipe.rounded) s.borderRadius = resolveToken(tokens, recipe.rounded);
  if (recipe.padding) s.padding = resolveToken(tokens, recipe.padding);
  if (recipe.typography) {
    const m = /^\{typography\.(.+)\}$/.exec(recipe.typography);
    if (m) {
      const t = tokens.typography[m[1]];
      if (t) {
        s.fontFamily = t.fontFamily;
        s.fontSize = t.fontSize;
        s.fontWeight = String(t.fontWeight);
        s.lineHeight = String(t.lineHeight);
      }
    }
  }
  return s as React.CSSProperties;
}

export function ComponentGrid({ tokens }: { tokens: DesignTokens }) {
  const recipes = Object.entries(tokens.components);

  return (
    <section style={{ marginBottom: 32 }}>
      <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600, color: '#8b949b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Components</h3>
      <div style={{ background: tokens.colors['neutral-50'] ?? '#fff', padding: 24, borderRadius: 8, border: '1px solid #1f242a', display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16 }}>
        {recipes.map(([name, recipe]) => (
          <div key={name}>
            <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#6e7780', marginBottom: 6 }}>{name}</div>
            <div style={recipeStyle(tokens, recipe as Record<string, string | undefined>)}>
              {name.includes('chip') || name.includes('badge')
                ? 'NIR-2024-04-15'
                : name.includes('cta')
                ? 'Get the inspection'
                : name.includes('card')
                ? 'Card surface — content goes here'
                : 'Sample'}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
