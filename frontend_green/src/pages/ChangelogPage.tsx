import React from 'react';
import { Link } from 'react-router-dom';
import LegalPage from './legal/LegalPage';

const note = (
  <>Spotted something or want a feature? <Link to="/contact">Let us know →</Link></>
);

// Hand-curated list of genuinely shipped features, newest first. Add a new entry
// here when something user-visible lands.
const ChangelogPage: React.FC = () => (
  <LegalPage
    title="What's new"
    path="/changelog"
    description="What's new in GroundedIQ — a running log of shipped, user-visible product updates and improvements."
    note={note}
  >
    <p className="legal-lead">
      A running log of what we've shipped. We update this as user-visible changes land.
    </p>

    <h2>June 2026</h2>
    <ul>
      <li><strong>Contact &amp; support, without an account.</strong> A public contact page so prospects and locked-out users can always reach us, plus our X and Instagram links across the site.</li>
      <li><strong>In-app Help &amp; Support.</strong> Send bugs, feedback, and questions (with screenshots) from inside the app — replies come straight to your email.</li>
      <li><strong>More ways to sign in.</strong> Sign in with GitHub and Microsoft alongside Google, with accounts linked automatically by verified email.</li>
      <li><strong>Flexible usage with credits.</strong> Per-plan message and report allowances, topped up anytime with prepaid credits.</li>
    </ul>

    <h2>Earlier in 2026</h2>
    <ul>
      <li><strong>Version compare.</strong> Diff and rank report versions side by side to see how a scope evolved.</li>
      <li><strong>Deliverable builder.</strong> Assemble client-ready documents from your alignment report.</li>
      <li><strong>Jira workspace.</strong> Two-way Jira integration — push a scope into tickets and manage them from GroundedIQ.</li>
      <li><strong>White-label exports.</strong> Put your own logo and colours on every export on the Plus plan.</li>
      <li><strong>Frontier-model reports.</strong> Sharper analysis on Plus and Pro using our most capable models.</li>
    </ul>
  </LegalPage>
);

export default ChangelogPage;
