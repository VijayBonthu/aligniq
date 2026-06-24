import { useEffect, useRef, useState } from 'react';

/**
 * Reports whether the observed element is on screen. Used to drive the
 * landing-page reveal animations and the live product-screen demos so motion
 * only happens while a section is actually visible.
 *
 * @param options IntersectionObserver options (defaults to 25% visible).
 * @param once    When true (default) it latches on first intersection. When
 *                false it tracks enter/leave so animations can replay.
 */
export function useInView<T extends Element = HTMLDivElement>(
  options: IntersectionObserverInit = { threshold: 0.25 },
  once = true,
) {
  const ref = useRef<T | null>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // Guard environments without the API (and honour the latched value).
    if (typeof IntersectionObserver === 'undefined') {
      setInView(true);
      return;
    }
    const obs = new IntersectionObserver(entries => {
      const entry = entries[0];
      if (entry.isIntersecting) {
        setInView(true);
        if (once) obs.disconnect();
      } else if (!once) {
        setInView(false);
      }
    }, options);
    obs.observe(el);
    return () => obs.disconnect();
    // Observer is created once on mount; options/once are treated as static.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { ref, inView } as const;
}
