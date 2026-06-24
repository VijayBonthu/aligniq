import { useState } from 'react';
import { useTheme } from '../../context/ThemeContext';

// Sun → shown in dark mode (click to go light). Moon → shown in light mode.
function SunIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="4" strokeWidth="1.8" />
      <path
        d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function MoonIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}

interface Props {
  /** Fixed top-right pill for pages without the app rail (landing/auth/pricing). */
  floating?: boolean;
  /** Square hit area + icon scale for inline use (rail = 40, nav = 38). */
  size?: number;
}

export default function ThemeToggle({ floating = false, size = 40 }: Props) {
  const { theme, toggleTheme } = useTheme();
  const [hov, setHov] = useState(false);
  const isDark = theme === 'dark';
  const label = isDark ? 'Switch to light theme' : 'Switch to dark theme';
  const iconSize = Math.round(size * 0.42);

  const base: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    transition: 'background .15s, color .15s, border-color .15s, transform .15s',
  };

  const style: React.CSSProperties = floating
    ? {
        ...base,
        position: 'fixed',
        top: 18,
        right: 18,
        zIndex: 60,
        width: 40,
        height: 40,
        borderRadius: 999,
        border: `1px solid ${hov ? 'var(--accent)' : 'var(--border-strong)'}`,
        background: 'color-mix(in oklab, var(--surface) 88%, transparent)',
        color: hov ? 'var(--accent)' : 'var(--fg-dim)',
        boxShadow: 'var(--shadow-card)',
        backdropFilter: 'blur(10px)',
        WebkitBackdropFilter: 'blur(10px)',
      }
    : {
        ...base,
        width: size,
        height: size,
        borderRadius: 8,
        border: 'none',
        background: hov ? 'var(--surface-2)' : 'transparent',
        color: hov ? 'var(--fg)' : 'var(--fg-muted)',
      };

  return (
    <button
      type="button"
      onClick={toggleTheme}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      title={label}
      aria-label={label}
      style={style}
    >
      {isDark ? <SunIcon size={iconSize} /> : <MoonIcon size={iconSize} />}
    </button>
  );
}
