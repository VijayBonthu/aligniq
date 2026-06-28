import React from 'react';
import { Link } from 'react-router-dom';
import LegalPage from './legal/LegalPage';

const note = (
  <>Want to talk through a use case? <Link to="/contact">Get in touch →</Link></>
);

const AboutPage: React.FC = () => (
  <LegalPage
    title="About GroundedIQ"
    path="/about"
    description="Why GroundedIQ exists — closing the gap between what clients ask for and what teams build, by turning a raw brief into an evidence-grounded alignment report before kickoff."
    note={note}
  >
    <p className="legal-lead">
      GroundedIQ exists to close the gap between what a client asks for and what actually gets built.
      That gap is where projects bleed — in change orders, blown timelines, and the slow erosion of
      trust between a consulting team and the people who hired them.
    </p>

    <h2>The problem we kept seeing</h2>
    <p>
      Briefs are optimistic. Clients underplay complexity because they can't see it yet; delivery teams
      overestimate how much they understand because the unknowns haven't surfaced. Everyone signs off,
      work begins, and the buried risks come due weeks later — now as expensive surprises instead of
      cheap questions.
    </p>

    <h2>What we do about it</h2>
    <p>
      GroundedIQ reads a raw brief the way a sharp solution architect would — interrogating it instead
      of just filing it. It surfaces the ambiguities, raises the questions that move the estimate,
      proposes a first-pass architecture and timeline, and grounds every assumption in evidence from
      the source documents. The result is one alignment report the client and the delivery team can
      both sign before a line of code is written.
    </p>

    <h2>How we think about the tool</h2>
    <ul>
      <li>
        <strong>The LLM assists; the human decides.</strong> Outputs are a rigorous starting point for
        your professional judgment, not a replacement for it.
      </li>
      <li>
        <strong>Evidence over assertion.</strong> Recommendations trace back to what's actually in the
        brief, so you can defend them in front of a client.
      </li>
      <li>
        <strong>One source of truth.</strong> No more "what did you mean by X" — the report is the
        shared agreement everyone works from.
      </li>
    </ul>

    <h2>Talk to us</h2>
    <p>
      We build alongside the consultants, architects, and product managers who use this every day.
      If you have feedback, a hard scoping problem, or just want to see it work on your own brief,
      reach out through our <Link to="/contact">contact page</Link> or email{' '}
      <a href="mailto:hello@grounded-iq.com">hello@grounded-iq.com</a>.
    </p>
  </LegalPage>
);

export default AboutPage;
