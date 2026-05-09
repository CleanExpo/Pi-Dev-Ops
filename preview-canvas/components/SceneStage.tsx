'use client';

import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import { Suspense, useMemo } from 'react';
import type { DesignTokens, SceneTokens } from '@/lib/loadSpecs';

// Resolve the cross-spec reference syntax `{ra.design.md:colors.primary}` → hex
// against the provided design tokens.
function resolveCross(value: string, design: DesignTokens, fallback: string): string {
  const m = /^\{[\w.-]+\.design\.md:colors\.(.+)\}$/.exec(value);
  if (m) {
    const hex = design.colors[m[1]];
    if (hex) return hex;
  }
  return value.startsWith('#') ? value : fallback;
}

interface FieldProps {
  primary: string;
  accent: string;
  surface: string;
}

function ParticleField({ primary, accent, surface }: FieldProps) {
  const positions = useMemo(() => {
    const pts: [number, number, number][] = [];
    for (let i = 0; i < 200; i += 1) {
      pts.push([(Math.random() - 0.5) * 6, (Math.random() - 0.5) * 2, (Math.random() - 0.5) * 2]);
    }
    return pts;
  }, []);

  return (
    <>
      <color attach="background" args={[primary]} />
      <ambientLight intensity={0.4} />
      <directionalLight position={[3, 5, 4]} intensity={1.2} />
      <directionalLight position={[-3, 2, -2]} intensity={0.6} color={primary} />
      <group>
        {positions.map((p, i) => (
          <mesh key={i} position={p}>
            <sphereGeometry args={[0.04, 8, 8]} />
            <meshBasicMaterial color={accent} transparent opacity={0.85} />
          </mesh>
        ))}
      </group>
      <mesh position={[0, -0.6, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[8, 4, 16, 8]} />
        <meshStandardMaterial color={surface} roughness={0.6} metalness={0.1} wireframe />
      </mesh>
      <OrbitControls enableZoom={false} enablePan={false} autoRotate autoRotateSpeed={0.5} />
    </>
  );
}

export function SceneStage({ design, scene }: { design: DesignTokens; scene: SceneTokens }) {
  const sceneKeys = Object.keys(scene.scenes);
  const heroKey = sceneKeys[0];
  const hero = scene.scenes[heroKey] as { background: string };

  const primary = resolveCross(hero.background, design, design.colors.primary);
  const accent = design.colors.accent ?? '#22D3EE';
  const surface = design.colors['neutral-100'] ?? '#E4E9EC';

  return (
    <section style={{ marginBottom: 32 }}>
      <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600, color: '#8b949b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        Scene · {heroKey}
      </h3>
      <div style={{ height: 360, borderRadius: 8, overflow: 'hidden', border: '1px solid #1f242a' }}>
        <Canvas camera={{ position: [0, 0.5, 4], fov: 35 }}>
          <Suspense fallback={null}>
            <ParticleField primary={primary} accent={accent} surface={surface} />
          </Suspense>
        </Canvas>
      </div>
      <div style={{ marginTop: 8, fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#6e7780' }}>
        renderer: {scene.renderer} · target {scene.performance.targetFps}fps · {sceneKeys.length} scene preset(s)
      </div>
    </section>
  );
}
