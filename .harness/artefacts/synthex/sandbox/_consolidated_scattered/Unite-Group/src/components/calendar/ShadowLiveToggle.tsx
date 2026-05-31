'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';

interface ShadowLiveToggleProps {
  currentMode: 'shadow' | 'live';
  approvalRate: number; // 0-100
  onModeChange: (newMode: 'shadow' | 'live') => Promise<void>;
}

export default function ShadowLiveToggle({
  currentMode,
  approvalRate,
  onModeChange,
}: ShadowLiveToggleProps) {
  const [mode, setMode] = useState<'shadow' | 'live'>(currentMode);
  const [showModal, setShowModal] = useState(false);
  const [showNudge, setShowNudge] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleToggle(requested: 'shadow' | 'live') {
    if (requested === mode) return;

    if (requested === 'live') {
      if (approvalRate < 100) {
        setShowNudge(true);
      }
      // Always show confirmation modal when switching to live
      setShowModal(true);
    } else {
      // Switching to shadow: no confirmation needed
      performSwitch('shadow');
    }
  }

  async function performSwitch(newMode: 'shadow' | 'live') {
    const previous = mode;
    setMode(newMode); // optimistic
    setShowModal(false);
    setShowNudge(false);
    setLoading(true);
    setError(null);
    try {
      await onModeChange(newMode);
    } catch {
      setMode(previous); // revert on error
      setError('Failed to update mode. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  const modeDescription =
    mode === 'shadow'
      ? 'You approve each post before it goes live'
      : 'Synthex posts automatically on schedule';

  return (
    <div className="space-y-2">
      {/* Toggle pill */}
      <div className="inline-flex items-center rounded-full border border-gray-200 bg-gray-100 p-1 gap-1">
        <button
          onClick={() => handleToggle('shadow')}
          disabled={loading}
          className={`px-4 py-1.5 rounded-full text-sm font-medium transition-all ${
            mode === 'shadow'
              ? 'bg-white text-gray-900 shadow-sm'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          Shadow
        </button>
        <button
          onClick={() => handleToggle('live')}
          disabled={loading}
          className={`px-4 py-1.5 rounded-full text-sm font-medium transition-all ${
            mode === 'live'
              ? 'bg-indigo-600 text-white shadow-sm'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          Live
        </button>
      </div>

      {/* Mode description */}
      <p className="text-xs text-gray-500">{modeDescription}</p>

      {/* Nudge message */}
      {showNudge && (
        <p className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded px-3 py-1.5">
          {approvalRate}% of posts approved this week. Consider reviewing remaining drafts before going live.
        </p>
      )}

      {/* Error */}
      {error && (
        <p className="text-xs text-red-500">{error}</p>
      )}

      {/* Confirmation modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-xl p-6 max-w-sm w-full mx-4 space-y-4">
            <h3 className="text-base font-semibold text-gray-900">Switch to Live Mode?</h3>
            <p className="text-sm text-gray-600">
              Posts will publish automatically on schedule. You can switch back at any time.
            </p>
            {approvalRate < 100 && (
              <p className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded px-3 py-2">
                Only {approvalRate}% of this week's posts have been approved. Unapproved posts may still go live automatically.
              </p>
            )}
            <div className="flex gap-3 justify-end pt-1">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setShowModal(false);
                  setShowNudge(false);
                }}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                className="bg-indigo-600 hover:bg-indigo-700 text-white"
                onClick={() => performSwitch('live')}
              >
                Confirm
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
