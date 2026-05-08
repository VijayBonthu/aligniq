interface Props {
  eyebrow: string;
  title: string;
  body: string;
}

export default function StubPage({ eyebrow, title, body }: Props) {
  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 40,
      }}
    >
      <div
        style={{
          maxWidth: 480,
          textAlign: 'center',
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          padding: '48px 40px',
        }}
      >
        <p
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            letterSpacing: '.14em',
            color: 'var(--accent)',
            margin: 0,
            marginBottom: 12,
          }}
        >
          {eyebrow} · COMING SOON
        </p>
        <h1
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 24,
            fontWeight: 400,
            letterSpacing: '-.02em',
            color: 'var(--fg)',
            margin: 0,
            marginBottom: 14,
          }}
        >
          {title}
        </h1>
        <p
          style={{
            fontSize: 13,
            color: 'var(--fg-dim)',
            lineHeight: 1.6,
            margin: 0,
          }}
        >
          {body}
        </p>
      </div>
    </div>
  );
}
