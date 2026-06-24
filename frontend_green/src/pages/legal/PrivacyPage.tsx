import React from 'react';
import LegalPage from './LegalPage';

const PrivacyPage: React.FC = () => (
  <LegalPage title="Privacy Policy" updated="June 9, 2026">
    <p className="legal-lead">
      This Privacy Policy explains how <strong>GroundedIQ, Inc.</strong> ("GroundedIQ", "we", "us")
      collects, uses, and shares information when you use our service. We aim to collect only what we
      need to run the product, and we <strong>never use your documents to train AI models</strong>.
    </p>

    <h2>1. Information we collect</h2>
    <h3>Information you provide</h3>
    <ul>
      <li><strong>Account details</strong> — name, username, email address, password (stored hashed),
        and optionally your company and role.</li>
      <li><strong>Content</strong> — the briefs, documents, and text you upload or enter, and the
        reports generated for you.</li>
      <li><strong>Payment information</strong> — handled by our payment processor, Stripe. We do not
        store full card numbers; we receive limited billing metadata (e.g. plan, status).</li>
      <li><strong>Communications</strong> — messages you send us, such as support requests.</li>
    </ul>
    <h3>Information collected automatically</h3>
    <ul>
      <li><strong>Usage and technical data</strong> — IP address, browser/device type, and product
        usage events.</li>
      <li><strong>A device identifier</strong> — a probabilistic device signal used to detect and
        prevent fraud and abuse of free usage.</li>
      <li><strong>Cookies</strong> — see "Cookies" below.</li>
    </ul>

    <h2>2. How we use information</h2>
    <ul>
      <li>To provide, maintain, and improve the service and generate your reports;</li>
      <li>To authenticate you and keep your account secure;</li>
      <li>To process payments and manage subscriptions and credits;</li>
      <li>To prevent fraud, abuse, and violations of our Terms;</li>
      <li>To respond to support requests and send service-related communications;</li>
      <li>To comply with legal obligations.</li>
    </ul>

    <h2>3. AI processing and training</h2>
    <p>
      To generate your reports, the content you submit is sent to our AI provider(s) (for example
      OpenAI) for processing. This processing is performed to provide the service to you. Your content
      is <strong>not used to train GroundedIQ's or our providers' models</strong>. To ground analysis
      in current information, the service may send non-identifying search queries to a web research
      provider.
    </p>

    <h2>4. Cookies and similar technologies</h2>
    <p>
      We use a small number of strictly necessary cookies — most importantly an HTTP-only session
      cookie that keeps you signed in. We do not use third-party advertising or cross-site tracking
      cookies. The device identifier described above is used only for fraud and abuse prevention.
    </p>

    <h2>5. How we share information</h2>
    <p>
      We do not sell your personal information. We share it only with service providers
      ("subprocessors") that help us run GroundedIQ, under contracts that limit their use of it:
    </p>
    <ul>
      <li><strong>OpenAI</strong> — AI model inference;</li>
      <li><strong>Amazon Web Services (AWS)</strong> — application hosting, database, and document storage;</li>
      <li><strong>Stripe</strong> — payment processing;</li>
      <li><strong>Chroma</strong> — vector storage used for retrieval over your reports;</li>
      <li><strong>Cloudflare</strong> — content delivery, DNS, and security;</li>
      <li><strong>Resend</strong> — transactional email (verification, password reset);</li>
      <li><strong>A web research provider</strong> — to ground reports in current information;</li>
      <li><strong>Atlassian / Jira</strong> — only if you choose to connect a Jira integration.</li>
    </ul>
    <p>
      We may also share information to comply with law or legal process, to protect rights and safety,
      or in connection with a merger, acquisition, or sale of assets (with notice where required).
    </p>

    <h2>6. Data retention</h2>
    <p>
      We keep your information for as long as your account is active or as needed to provide the
      service. You can delete content or request account deletion; we will delete or de-identify your
      personal information within a reasonable period, except where we must retain it for legal,
      accounting, or security reasons.
    </p>

    <h2>7. Security</h2>
    <p>
      We protect information using measures such as encryption in transit and at rest, access controls,
      and hashed passwords. No method of transmission or storage is completely secure, so we cannot
      guarantee absolute security.
    </p>

    <h2>8. Your rights and choices</h2>
    <p>
      Depending on where you live, you may have the right to access, correct, delete, or export your
      personal information, to object to or restrict certain processing, and to withdraw consent. You
      can update much of your information in your account settings, or contact us to exercise these
      rights. We will not discriminate against you for exercising them.
    </p>

    <h2>9. International data transfers</h2>
    <p>
      GroundedIQ and several of its providers are based in the United States, so your information may
      be processed in the U.S. and other countries. Where required, we rely on appropriate safeguards
      for such transfers.
    </p>

    <h2>10. Children</h2>
    <p>
      GroundedIQ is not intended for individuals under 18, and we do not knowingly collect personal
      information from children.
    </p>

    <h2>11. Changes to this policy</h2>
    <p>
      We may update this Privacy Policy from time to time. If we make material changes, we will provide
      notice (for example by email or in-app) and update the "Last updated" date above.
    </p>

    <h2>12. Contact</h2>
    <p>
      Questions or requests? Email <a href="mailto:hello@grounded-iq.com">hello@grounded-iq.com</a>.
    </p>
  </LegalPage>
);

export default PrivacyPage;
