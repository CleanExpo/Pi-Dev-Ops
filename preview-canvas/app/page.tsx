import Link from 'next/link';
import { listBrands, listIterationJobs, loadDesign } from '@/lib/loadSpecs';

export default function HomePage() {
  const brands = listBrands();
  const jobs = listIterationJobs();

  return (
    <main className="shell">
      <h1>Pi-CEO Design Canvas</h1>
      <p className="lede">
        Live preview of every brand&apos;s design system, motion choreography, and 3D scenes.
        Each route reads `.design.md` / `.motion.md` / `.scene.md` directly from `packages/brand-config/src/brands/`.
      </p>

      <h2>Brands ({brands.length})</h2>
      <div className="brand-grid">
        {brands.map((slug) => {
          let name = slug;
          try {
            name = loadDesign(slug).name;
          } catch {
            // Brand may have a .ts but not yet a .design.md; show slug only.
          }
          return (
            <Link key={slug} className="brand-card" href={`/brand/${slug}`}>
              <div className="slug">{slug}</div>
              <div className="name">{name}</div>
            </Link>
          );
        })}
      </div>

      <h2>Iteration jobs ({jobs.length})</h2>
      {jobs.length === 0 ? (
        <p className="lede">No iteration jobs yet. Run `design-board` or `design-iterate` to create one — variants will land in `.research/design/iterations/{'{jobId}'}/`.</p>
      ) : (
        <div className="brand-grid">
          {jobs.map((jobId) => (
            <Link key={jobId} className="brand-card" href={`/board/${jobId}`}>
              <div className="slug">job</div>
              <div className="name">{jobId}</div>
            </Link>
          ))}
        </div>
      )}

      <h2>Families</h2>
      <div className="brand-grid">
        {(['restoration', 'safety', 'industrial', 'consumer', 'training'] as const).map((fam) => (
          <Link key={fam} className="brand-card" href={`/family/${fam}`}>
            <div className="slug">family</div>
            <div className="name">{fam}</div>
          </Link>
        ))}
      </div>
    </main>
  );
}
