import React from 'react';

interface State {
  hasError: boolean;
}

/**
 * Catches render/runtime errors anywhere below it and shows a small, branded "reload"
 * fallback instead of a silent white page. Logs the error to the console so it's
 * debuggable. (Cannot help a fully JS-blocked sandbox — nothing can run there — but it
 * turns every real crash into a visible state.)
 */
export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: unknown, info: unknown) {
    // eslint-disable-next-line no-console
    console.error('App crashed:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            minHeight: '100vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: '#0d0d11',
            color: '#ece7dc',
            fontFamily: 'Segoe UI, Roboto, Helvetica, Arial, sans-serif',
            padding: 24,
            textAlign: 'center',
          }}
        >
          <div style={{ maxWidth: 420 }}>
            <div style={{ fontSize: 20, fontWeight: 700, letterSpacing: '-.02em', marginBottom: 20 }}>
              Grounded<span style={{ color: '#34a37b' }}>IQ</span>
            </div>
            <h1 style={{ fontSize: 22, margin: '0 0 12px' }}>Something went wrong.</h1>
            <p style={{ color: '#a39d8e', fontSize: 14, lineHeight: 1.6, margin: '0 0 22px' }}>
              The page hit an unexpected error. Reloading usually fixes it.
            </p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              style={{
                background: '#34a37b',
                color: '#fff',
                border: 'none',
                fontWeight: 600,
                fontSize: 14,
                padding: '10px 22px',
                borderRadius: 10,
                cursor: 'pointer',
              }}
            >
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
