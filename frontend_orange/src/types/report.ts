export type BasisKind = 'document_quote' | 'retrieved_url' | 'model_knowledge' | 'inferred';

export type Confidence = 'high' | 'medium' | 'low';

export interface BasisEvidence {
  id: string;
  basis: BasisKind;
  evidence?: string;
  evidence_quote?: string;
  confidence?: Confidence;
  retrieved_at?: string;
}

export type EvidenceMap = Record<string, BasisEvidence>;
