'use client';

interface FeaturedProgrammeCardProps {
  status: 'not_applied' | 'applied' | 'in_production' | 'published';
  clientId: string;
  onOptIn?: () => void;
}

const STATUS_CONFIG = {
  not_applied: {
    heading: 'Get Featured in Synthex',
    subtext: 'Turn your results into a case study video published on our YouTube channel.',
    cta: 'Apply to get featured',
    badge: null,
  },
  applied: {
    heading: 'Application received',
    subtext: "We'll review your results and be in touch within 5 business days.",
    cta: null,
    badge: 'Under review',
  },
  in_production: {
    heading: 'Your video is in production',
    subtext: "We're creating your case study video. You'll receive a preview before it goes live.",
    cta: null,
    badge: 'In production',
  },
  published: {
    heading: 'You\'re featured in Synthex',
    subtext: 'Your case study video is live on our YouTube channel and linked from your Authority Hub.',
    cta: 'Watch your video',
    badge: 'Published',
  },
};

export function FeaturedProgrammeCard({ status, clientId, onOptIn }: FeaturedProgrammeCardProps) {
  const config = STATUS_CONFIG[status];

  const handleOptIn = async () => {
    await fetch('/api/clients/featured-opt-in', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_id: clientId }),
    });
    onOptIn?.();
  };

  const benefits = [
    'Free professional case study video',
    'Indexed by Google via VideoObject schema',
    'Linked from your Authority Hub page',
  ];

  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-6 space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="font-semibold text-neutral-900">{config.heading}</h3>
          <p className="text-sm text-neutral-500 mt-1">{config.subtext}</p>
        </div>
        {config.badge && (
          <span className="text-xs font-medium px-2 py-1 rounded-full bg-blue-50 text-blue-700 shrink-0 ml-4">
            {config.badge}
          </span>
        )}
      </div>

      {status === 'not_applied' && (
        <ul className="space-y-1">
          {benefits.map((b) => (
            <li key={b} className="text-sm text-neutral-600 flex items-center gap-2">
              <span className="text-green-500">✓</span> {b}
            </li>
          ))}
        </ul>
      )}

      {config.cta && status === 'not_applied' && (
        <button
          onClick={handleOptIn}
          className="w-full rounded-lg bg-neutral-900 text-white text-sm font-medium py-2.5 hover:bg-neutral-700 transition-colors"
        >
          {config.cta}
        </button>
      )}
    </div>
  );
}
