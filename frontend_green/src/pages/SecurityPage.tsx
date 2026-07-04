import React from 'react';
import { Link } from 'react-router-dom';
import LegalPage from './legal/LegalPage';

const note = (
  <>
    Have a security question or want to report a vulnerability? Email{' '}
    <a href="mailto:support@grounded-iq.com">support@grounded-iq.com</a> or use our{' '}
    <Link to="/contact">contact form</Link>.
  </>
);

const SecurityPage: React.FC = () => (
  <LegalPage
    title="Security & data privacy"
    path="/security"
    description="How GroundedIQ protects your data — encryption in transit and at rest, least-privilege access, and a commitment to never use your documents to train AI models."
    updated="June 28, 2026"
    note={note}
  >
    <p className="legal-lead">
      The documents and briefs you upload are often your clients' confidential material. We treat them
      that way. This page explains, in plain terms, how we handle your data.
    </p>

    <h2>Your data is processed only to serve you</h2>
    <p>
      The documents and content you upload are used for one purpose: to generate <em>your</em> analysis
      and reports inside your account. We don't sell your data, and we don't share it with third parties
      to market to you.
    </p>

    <h2>Never used to train AI models</h2>
    <p>
      Your documents and the reports we generate from them are <strong>never used to train any AI
      models</strong> — not ours and not a third party's. Your work stays your work.
    </p>

    <h2>Deletion on request</h2>
    <p>
      You stay in control of your data. You can delete a project from your account, and you can ask us
      to delete the data associated with your account entirely — just email{' '}
      <a href="mailto:support@grounded-iq.com">support@grounded-iq.com</a> and we'll take care of it.
    </p>

    <h2>Reporting a concern</h2>
    <p>
      If you believe you've found a security issue, please tell us privately at{' '}
      <a href="mailto:support@grounded-iq.com">support@grounded-iq.com</a> rather than disclosing it
      publicly, and we'll work with you to resolve it. For how we collect and process personal data,
      see our <Link to="/privacy">Privacy Policy</Link>.
    </p>
  </LegalPage>
);

export default SecurityPage;
