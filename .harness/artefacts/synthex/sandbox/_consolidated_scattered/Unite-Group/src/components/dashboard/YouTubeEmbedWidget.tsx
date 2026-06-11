'use client';

import { useState } from 'react';
import type { ClientVideoWithStats } from '@/lib/dashboard/getClientYouTubeVideos';

interface YouTubeEmbedWidgetProps {
  videos: ClientVideoWithStats[];
}

function formatViewCount(count: number): string {
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`;
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}K`;
  return String(count);
}

function VideoCard({ video, onSelect }: { video: ClientVideoWithStats; onSelect: (id: string) => void }) {
  const thumbnail = video.thumbnail_url ?? `https://img.youtube.com/vi/${video.youtube_video_id}/mqdefault.jpg`;

  return (
    <button
      onClick={() => onSelect(video.youtube_video_id)}
      className="group relative w-full rounded-lg overflow-hidden border border-neutral-200 bg-neutral-50 hover:border-neutral-300 transition-colors text-left"
      aria-label={`Play ${video.title}`}
    >
      <div className="relative aspect-video">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={thumbnail}
          alt={video.title}
          className="w-full h-full object-cover"
          loading="lazy"
        />
        <div className="absolute inset-0 flex items-center justify-center bg-black/20 group-hover:bg-black/30 transition-colors">
          <div className="w-12 h-12 rounded-full bg-red-600 flex items-center justify-center">
            <span className="text-white text-lg ml-1">▶</span>
          </div>
        </div>
      </div>
      <div className="p-3">
        <p className="text-sm font-medium text-neutral-900 line-clamp-2">{video.title}</p>
        {video.view_count > 0 && (
          <p className="text-xs text-neutral-500 mt-1">{formatViewCount(video.view_count)} views</p>
        )}
      </div>
    </button>
  );
}

function VideoModal({ videoId, title, onClose }: { videoId: string; title: string; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
      onClick={onClose}
      role="dialog"
      aria-label={`Playing: ${title}`}
      aria-modal="true"
    >
      <div
        className="relative w-full max-w-3xl"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute -top-10 right-0 text-white text-sm hover:text-neutral-300"
          aria-label="Close video"
        >
          ✕ Close
        </button>
        <div className="aspect-video">
          <iframe
            src={`https://www.youtube.com/embed/${videoId}?autoplay=1`}
            title={title}
            className="w-full h-full rounded-lg"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
        </div>
      </div>
    </div>
  );
}

export function YouTubeEmbedWidget({ videos }: YouTubeEmbedWidgetProps) {
  const [activeVideoId, setActiveVideoId] = useState<string | null>(null);
  const activeVideo = videos.find((v) => v.youtube_video_id === activeVideoId);

  if (videos.length === 0) {
    return (
      <div className="rounded-xl border border-neutral-200 bg-neutral-50 p-6 text-center">
        <div className="text-3xl mb-3">🎬</div>
        <p className="text-sm font-medium text-neutral-700">Your first Synthex video is coming soon</p>
        <p className="text-xs text-neutral-500 mt-1">
          Opt in to the Featured in Synthex programme to get your free case study video.
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-neutral-900">Your Synthex Videos</h3>
          <a
            href={`https://www.youtube.com/@SynthexMedia`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-600 hover:underline"
          >
            View all on YouTube →
          </a>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {videos.map((video) => (
            <VideoCard key={video.id} video={video} onSelect={setActiveVideoId} />
          ))}
        </div>
      </div>

      {activeVideoId && activeVideo && (
        <VideoModal
          videoId={activeVideoId}
          title={activeVideo.title}
          onClose={() => setActiveVideoId(null)}
        />
      )}
    </>
  );
}
