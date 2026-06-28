import React from 'react';
import LegalPage from './LegalPage';

const TermsPage: React.FC = () => (
  <LegalPage
    title="Terms of Service"
    path="/terms"
    description="GroundedIQ Terms of Service — the terms that govern your access to and use of the GroundedIQ websites, applications, and services."
    updated="June 9, 2026"
  >
    <p className="legal-lead">
      These Terms of Service ("Terms") govern your access to and use of GroundedIQ — the
      websites, applications, and services operated by <strong>GroundedIQ, Inc.</strong> ("GroundedIQ",
      "we", "us"). By creating an account or using the service, you agree to these Terms. If you do
      not agree, do not use the service.
    </p>

    <h2>1. The service</h2>
    <p>
      GroundedIQ is an AI-assisted scoping tool. You provide a project brief or documents, and the
      service produces analysis such as risks, clarifying questions, a first-pass architecture,
      timelines, and resourcing. Outputs are generated with the assistance of large language models
      and are intended as a <strong>starting point for your professional judgment</strong> — not as
      a substitute for it.
    </p>

    <h2>2. Eligibility and accounts</h2>
    <ul>
      <li>You must be at least 18 years old and able to form a binding contract.</li>
      <li>You agree to provide accurate account information and to keep it up to date.</li>
      <li>You are responsible for activity under your account and for safeguarding your credentials.
        Notify us promptly of any unauthorized use.</li>
    </ul>

    <h2>3. Acceptable use</h2>
    <p>You agree not to:</p>
    <ul>
      <li>Upload content you do not have the right to share, or that infringes the rights of others;</li>
      <li>Use the service for unlawful purposes or to generate unlawful, harmful, or deceptive content;</li>
      <li>Attempt to reverse-engineer, scrape, overload, disrupt, or circumvent limits or security of the service;</li>
      <li>Resell or provide the service to third parties except as expressly permitted by your plan.</li>
    </ul>

    <h2>4. Your content</h2>
    <p>
      You retain all rights to the documents and inputs you provide and to the reports generated for
      you ("Your Content"). You grant GroundedIQ a limited, worldwide license to host, process, and
      transmit Your Content <strong>solely to operate and provide the service to you</strong>. We do
      not use Your Content to train AI models. See our <a href="/privacy">Privacy Policy</a> for details.
    </p>

    <h2>5. AI outputs — important disclaimer</h2>
    <p>
      AI-generated outputs may be inaccurate, incomplete, or out of date. Estimates, timelines, costs,
      and architectural recommendations are <strong>illustrative, not guarantees</strong>, and may not
      reflect your specific circumstances. You are solely responsible for reviewing outputs and for any
      decisions you make based on them. GroundedIQ does not provide legal, financial, or other
      professional advice.
    </p>

    <h2>6. Plans, billing, and credits</h2>
    <ul>
      <li>Paid plans are billed in advance on a recurring (e.g. monthly) basis through our payment
        processor, <strong>Stripe</strong>, and renew automatically until cancelled.</li>
      <li>Prepaid credits are top-ups consumed by usage. Credits are non-refundable and have no cash
        value except where required by law.</li>
      <li>Fees are exclusive of taxes, which you are responsible for where applicable.</li>
      <li>We may change prices or plan features with reasonable advance notice; changes apply at your
        next billing cycle.</li>
    </ul>

    <h2>7. Cancellation and refunds</h2>
    <p>
      You may cancel at any time from your account settings. Cancellation stops future renewals; you
      keep access through the end of the current paid period. Except where required by law, payments
      and consumed credits are non-refundable.
    </p>

    <h2>8. Third-party services</h2>
    <p>
      The service relies on third-party providers (for example OpenAI for model inference, Stripe for
      payments, and optional integrations such as Jira that you choose to connect). Your use of those
      integrations may also be subject to the third party's terms. We are not responsible for
      third-party services.
    </p>

    <h2>9. Intellectual property</h2>
    <p>
      The GroundedIQ platform, including its software, design, and trademarks, is owned by GroundedIQ
      and protected by law. These Terms do not grant you any right in our intellectual property other
      than the limited right to use the service.
    </p>

    <h2>10. Suspension and termination</h2>
    <p>
      We may suspend or terminate your access if you breach these Terms, create risk or legal exposure
      for us, or for prolonged inactivity. You may stop using the service at any time. Sections that by
      their nature should survive termination (e.g. content licenses already granted, disclaimers,
      limitation of liability) will survive.
    </p>

    <h2>11. Disclaimers</h2>
    <p>
      The service is provided <strong>"as is" and "as available"</strong>, without warranties of any
      kind, whether express or implied, including merchantability, fitness for a particular purpose,
      and non-infringement. We do not warrant that the service will be uninterrupted, error-free, or
      that outputs will be accurate or reliable.
    </p>

    <h2>12. Limitation of liability</h2>
    <p>
      To the maximum extent permitted by law, GroundedIQ will not be liable for any indirect,
      incidental, special, consequential, or punitive damages, or for lost profits or data. Our total
      liability for any claim relating to the service will not exceed the amount you paid us in the
      twelve (12) months before the event giving rise to the claim.
    </p>

    <h2>13. Indemnification</h2>
    <p>
      You agree to indemnify and hold GroundedIQ harmless from claims arising out of Your Content or
      your use of the service in violation of these Terms or applicable law.
    </p>

    <h2>14. Changes to these Terms</h2>
    <p>
      We may update these Terms from time to time. If we make material changes, we will provide notice
      (for example by email or in-app). Continued use after changes take effect constitutes acceptance.
    </p>

    <h2>15. Governing law</h2>
    <p>
      These Terms are governed by the laws of the State of Delaware, United States, without regard to
      its conflict-of-laws rules. The courts located in Delaware will have exclusive jurisdiction over
      disputes, subject to any mandatory consumer protections in your jurisdiction.
    </p>

    <h2>16. Contact</h2>
    <p>
      Questions about these Terms? Email <a href="mailto:hello@grounded-iq.com">hello@grounded-iq.com</a>.
    </p>
  </LegalPage>
);

export default TermsPage;
