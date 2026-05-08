export const surface = {
  pageGradient:
    'bg-gradient-to-br from-[#0f0c29] via-[#302b63] to-[#24243e]',
  card: 'bg-[#1a1745] border border-white/10',
  cardHover: 'hover:bg-[#221e55] hover:border-white/20',
  cardElevated: 'bg-[#2b2a63] border border-white/10',
  header: 'bg-[#141332]/90 border-b border-white/10',
  footer: 'bg-indigo-950/50 border-t border-white/10',
  subtle: 'bg-white/5 border border-white/10',
  railBg: 'bg-[#1c1b3b] border-white/10',
} as const;

export const accent = {
  brandGradient: 'bg-gradient-to-br from-blue-400 to-purple-600',
  actionGradient: 'bg-gradient-to-r from-blue-600 to-purple-600',
  actionHover: 'hover:from-blue-500 hover:to-purple-500',
  textGradient:
    'bg-clip-text text-transparent bg-gradient-to-r from-blue-300 to-purple-300',
  ring: 'focus:ring-1 focus:ring-purple-500',
} as const;

export const text = {
  primary: 'text-white',
  secondary: 'text-gray-300',
  muted: 'text-gray-400',
  dim: 'text-gray-500',
} as const;

export const status = {
  ok: 'bg-green-500/20 text-green-300 border border-green-500/20',
  warn: 'bg-yellow-500/20 text-yellow-300 border border-yellow-500/20',
  danger: 'bg-red-500/20 text-red-300 border border-red-500/20',
  info: 'bg-blue-500/20 text-blue-300 border border-blue-500/20',
  neutral: 'bg-white/5 text-gray-300 border border-white/10',
} as const;

export const readinessColor = (score: number): string => {
  if (score >= 0.8) return 'text-green-400';
  if (score >= 0.5) return 'text-yellow-400';
  return 'text-red-400';
};

export const readinessBar = (score: number): string => {
  if (score >= 0.8) return 'bg-green-500';
  if (score >= 0.5) return 'bg-yellow-500';
  return 'bg-red-500';
};
