import Link from 'next/link';
import { notFound } from 'next/navigation';
import { Palette } from '@/components/Palette';
import { Typography } from '@/components/Typography';
import { ComponentGrid } from '@/components/ComponentGrid';
import { MotionStrip } from '@/components/MotionStrip';
import { SceneStage } from '@/components/SceneStage';
import { loadDesign, tryLoadMotion, tryLoadScene } from '@/lib/loadSpecs';

export default async function BrandPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let design;
  try {
    design = loadDesign(slug);
  } catch {
    notFound();
  }
  const motion = tryLoadMotion(slug);
  const scene = tryLoadScene(slug);

  return (
    <main className="shell">
      <div style={{ marginBottom: 8, fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }}>
        <Link href="/" style={{ color: '#6e7780' }}>← all brands</Link>
      </div>
      <h1>{design.name}</h1>
      {design.description && <p className="lede">{design.description}</p>}

      <Palette tokens={design} />
      <Typography tokens={design} />
      <ComponentGrid tokens={design} />
      {motion && <MotionStrip design={design} motion={motion} />}
      {scene && <SceneStage design={design} scene={scene} />}
    </main>
  );
}
