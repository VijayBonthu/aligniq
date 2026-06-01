import React from 'react';
import { useInView } from '../../hooks/useInView';

type Variant = 'up' | 'left' | 'right';

interface Props {
  children: React.ReactNode;
  /** Entrance direction. Defaults to a gentle rise. */
  variant?: Variant;
  /** Stagger in ms — apply to siblings for a cascade. */
  delay?: number;
  className?: string;
  style?: React.CSSProperties;
  id?: string;
}

const VARIANT_CLASS: Record<Variant, string> = {
  up: 'reveal-u',
  left: 'reveal-l',
  right: 'reveal-r',
};

/**
 * Wraps content in a scroll-triggered entrance animation. Latches on first
 * view; respects `prefers-reduced-motion` via the `.reveal` rules in globals.
 */
export const Reveal: React.FC<Props> = ({
  children,
  variant = 'up',
  delay = 0,
  className = '',
  style,
  id,
}) => {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.15 });
  return (
    <div
      ref={ref}
      id={id}
      className={`reveal ${VARIANT_CLASS[variant]} ${inView ? 'in' : ''} ${className}`.trim()}
      style={{ transitionDelay: delay ? `${delay}ms` : undefined, ...style }}
    >
      {children}
    </div>
  );
};
