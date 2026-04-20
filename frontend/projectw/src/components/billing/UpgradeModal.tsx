import React from 'react';
import { useNavigate } from 'react-router-dom';
import { createCheckoutSession } from '../../services/billingService';

interface UpgradeModalProps {
  limitType: 'max_chats' | 'messages_per_chat' | 'monthly_report_regen';
  current: number;
  limit: number;
  onClose: () => void;
}

const LIMIT_MESSAGES: Record<string, string> = {
  max_chats: 'You have reached your active chat limit.',
  messages_per_chat: 'You have reached the message limit for this chat.',
  monthly_report_regen: 'You have used all your monthly report regenerations.',
};

export default function UpgradeModal({ limitType, current, limit, onClose }: UpgradeModalProps) {
  const navigate = useNavigate();
  const [loading, setLoading] = React.useState<string | null>(null);

  async function handleUpgrade(tier: 'basic' | 'plus') {
    setLoading(tier);
    try {
      const { checkout_url } = await createCheckoutSession(tier);
      window.location.href = checkout_url;
    } catch {
      setLoading(null);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl p-6 w-full max-w-md mx-4">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">Upgrade Your Plan</h2>
        <p className="text-gray-600 dark:text-gray-300 mb-1">{LIMIT_MESSAGES[limitType]}</p>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
          Usage: {current} / {limit}
        </p>

        <div className="space-y-3 mb-6">
          <button
            onClick={() => handleUpgrade('basic')}
            disabled={loading !== null}
            className="w-full py-2.5 px-4 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-lg font-medium transition-colors"
          >
            {loading === 'basic' ? 'Redirecting…' : 'Upgrade to Basic — $30/mo'}
          </button>
          <button
            onClick={() => handleUpgrade('plus')}
            disabled={loading !== null}
            className="w-full py-2.5 px-4 bg-indigo-900 hover:bg-indigo-800 disabled:opacity-50 text-white rounded-lg font-medium transition-colors"
          >
            {loading === 'plus' ? 'Redirecting…' : 'Upgrade to Plus — $50/mo'}
          </button>
          <button
            onClick={() => { onClose(); navigate('/pricing'); }}
            className="w-full py-2.5 px-4 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 rounded-lg font-medium hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
          >
            View All Plans
          </button>
        </div>

        <button
          onClick={onClose}
          className="w-full text-sm text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}
