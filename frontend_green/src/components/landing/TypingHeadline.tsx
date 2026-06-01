import React, { useEffect, useRef, useState } from 'react';

interface Props {
  prefix: string;
  suffix: string;
}

export const TypingHeadline: React.FC<Props> = ({ prefix, suffix }) => {
  const [typed, setTyped] = useState('');
  const [done, setDone] = useState(false);
  const [started, setStarted] = useState(false);
  const ref = useRef<HTMLHeadingElement | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const obs = new IntersectionObserver(
      entries => {
        if (entries[0].isIntersecting) {
          setStarted(true);
          obs.disconnect();
        }
      },
      { threshold: 0.4 }
    );
    obs.observe(ref.current);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    if (!started) return;
    let i = 0;
    let timer: number;
    const step = () => {
      if (i > suffix.length) {
        setDone(true);
        return;
      }
      setTyped(suffix.slice(0, i));
      const ch = suffix[i - 1];
      const delay = ch === '.' || ch === ',' ? 180 : 55 + Math.random() * 45;
      i += 1;
      timer = window.setTimeout(step, delay);
    };
    step();
    return () => window.clearTimeout(timer);
  }, [started, suffix]);

  return (
    <h2 ref={ref} className="display section-h typing-h">
      {prefix}
      <span className="type-suffix">{typed}</span>
      <span className={`type-caret ${done ? 'done' : ''}`} />
    </h2>
  );
};
