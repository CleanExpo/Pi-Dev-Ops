import { interpolate, spring, Easing, SpringConfig } from 'remotion';
import { BrandMotion, SignatureMotion } from '../brands/types';

export interface MotionContext {
  frame: number;
  fps: number;
  motion: BrandMotion;
}

/**
 * Brand-aware fade-in over `motion.durations.base` frames starting at `startFrame`.
 */
export function brandFadeIn(ctx: MotionContext, startFrame: number = 0): number {
  return interpolate(
    ctx.frame,
    [startFrame, startFrame + ctx.motion.durations.base],
    [0, 1],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic) },
  );
}

/**
 * Signature entry motion per brand. Returns { translateX, translateY, scale, opacity }.
 */
export function signatureEntry(
  ctx: MotionContext,
  startFrame: number,
  amplitude: number = 80,
): { translateX: number; translateY: number; scale: number; opacity: number } {
  const t = interpolate(
    ctx.frame,
    [startFrame, startFrame + ctx.motion.durations.base],
    [0, 1],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic) },
  );
  const opacity = t;
  const inverse = 1 - t;

  switch (ctx.motion.signature as SignatureMotion) {
    case 'rise':
      return { translateX: 0, translateY: amplitude * inverse, scale: 1, opacity };
    case 'sweep':
      return { translateX: -amplitude * inverse, translateY: 0, scale: 1, opacity };
    case 'iris': {
      const scale = 0.7 + 0.3 * t;
      return { translateX: 0, translateY: 0, scale, opacity };
    }
    case 'pulse': {
      const cfg: Partial<SpringConfig> = { damping: 10, stiffness: 120, mass: 0.7 };
      const s = spring({ frame: ctx.frame - startFrame, fps: ctx.fps, config: cfg });
      return { translateX: 0, translateY: 0, scale: 0.85 + 0.15 * s, opacity };
    }
    case 'whip':
      return { translateX: amplitude * inverse * inverse, translateY: 0, scale: 1, opacity };
    default:
      return { translateX: 0, translateY: 0, scale: 1, opacity };
  }
}

/**
 * Stagger helper — child index N starts (N * stride) frames after the parent.
 */
export function staggerStart(parentStart: number, index: number, stride: number = 4): number {
  return parentStart + index * stride;
}
