## Layout Patterns

### Timeline Layout (Primary)

Replaces card grids:

```tsx
<div className="relative pl-4">
  {/* Vertical spine */}
  <div className="absolute top-0 bottom-0 left-8 w-px bg-gradient-to-b from-white/10 via-white/5 to-transparent" />

  <div className="space-y-8">
    {items.map((item, index) => (
      <TimelineNode key={item.id} item={item} index={index} />
    ))}
  </div>
</div>
```

### Data Strip Layout

Horizontal inline metrics:

```tsx
<div className="flex items-center gap-8 border-[0.5px] border-white/[0.06] bg-white/[0.01] px-6 py-3">
  {metrics.map((metric, index) => (
    <React.Fragment key={metric.label}>
      {index > 0 && <div className="h-4 w-px bg-white/10" />}
      <div className="flex items-baseline gap-2">
        <span className="text-[10px] tracking-widest text-white/30 uppercase">{metric.label}</span>
        <span className="font-mono text-lg" style={{ color: metric.colour }}>
          {metric.value}
        </span>
      </div>
    </React.Fragment>
  ))}
</div>
```

### Asymmetrical Splits

Avoid 50/50. Use asymmetrical ratios:

```tsx
// 60/40 split
<div className="flex">
  <div className="flex-[3]">Main content</div>
  <div className="flex-[2]">Sidebar</div>
</div>

// 70/30 split
<div className="flex">
  <div className="flex-[7]">Main content</div>
  <div className="flex-[3]">Sidebar</div>
</div>
```
