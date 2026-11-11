## Animation Patterns

### Framer Motion Required

All animations must use Framer Motion. CSS animations are prohibited.

### Approved Easings

```typescript
const EASINGS = {
  outExpo: [0.19, 1, 0.22, 1], // Primary - smooth deceleration
  smooth: [0.4, 0, 0.2, 1], // Gentle ease
  snappy: [0.68, -0.55, 0.265, 1.55], // Snappy with overshoot
};
```

### Breathing Animation

For active/live elements:

```tsx
<motion.div
  animate={{
    opacity: [1, 0.6, 1],
    scale: [1, 1.05, 1],
  }}
  transition={{
    duration: 2,
    repeat: Infinity,
    ease: 'easeInOut',
  }}
/>
```

### Glow Pulse

For error or attention states:

```tsx
<motion.div
  animate={{
    boxShadow: [`0 0 0 ${colour}00`, `0 0 20px ${colour}40`, `0 0 0 ${colour}00`],
  }}
  transition={{
    duration: 1.5,
    repeat: Infinity,
  }}
/>
```

### Staggered Entry

For lists:

```tsx
<motion.div
  initial={{ opacity: 0, x: -20 }}
  animate={{ opacity: 1, x: 0 }}
  transition={{
    delay: index * 0.1,
    duration: 0.5,
    ease: [0.19, 1, 0.22, 1],
  }}
/>
```

## Component Patterns

### Breathing Orb (Status Indicator)

```tsx
function BreathingOrb({ colour, isActive, size = 'md' }) {
  const sizes = { sm: 'h-8 w-8', md: 'h-12 w-12', lg: 'h-16 w-16' };

  return (
    <motion.div
      className={cn(sizes[size], 'flex items-center justify-center rounded-full border-[0.5px]')}
      style={{
        borderColor: isActive ? `${colour}50` : 'rgba(255,255,255,0.1)',
        backgroundColor: isActive ? `${colour}10` : 'rgba(255,255,255,0.02)',
        boxShadow: isActive ? `0 0 30px ${colour}40` : 'none',
      }}
    >
      <motion.div
        className="h-2 w-2 rounded-full"
        style={{ backgroundColor: colour }}
        animate={isActive ? { scale: [1, 1.3, 1], opacity: [1, 0.6, 1] } : {}}
        transition={{ duration: 2, repeat: Infinity }}
      />
    </motion.div>
  );
}
```
