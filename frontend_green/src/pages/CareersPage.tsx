import React from 'react';
import { Link } from 'react-router-dom';
import LegalPage from './legal/LegalPage';

const note = (
  <>Think you'd be a fit anyway? <Link to="/contact">Tell us why →</Link></>
);

const CareersPage: React.FC = () => (
  <LegalPage
    title="Careers"
    path="/careers"
    description="Careers at GroundedIQ — join a small, focused team building the alignment layer between what clients ask for and what gets built."
    note={note}
  >
    <p className="legal-lead">
      We're a small, focused team building GroundedIQ — the alignment layer between what clients ask for
      and what gets built.
    </p>

    <h2>No open roles right now</h2>
    <p>
      We don't have any positions open at the moment. But we're always glad to hear from people who care
      about the problem we're working on: helping consulting and delivery teams scope work that actually
      holds up.
    </p>

    <h2>Still want to reach out?</h2>
    <p>
      If you're excited about what we're building and think there's a fit — engineering, design, product,
      or go-to-market — send us a note at{' '}
      <a href="mailto:hello@grounded-iq.com">hello@grounded-iq.com</a> or through our{' '}
      <Link to="/contact">contact page</Link>. Tell us what you'd want to work on and why. We read
      everything.
    </p>
  </LegalPage>
);

export default CareersPage;
