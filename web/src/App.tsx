import React, { useState, useEffect } from 'react';

const API = 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Types (canonical shapes)
// ---------------------------------------------------------------------------

interface SellerProfile {
  seller_id: string;
  offer_what: string;
  offer_where: string[];
  offer_who: string[];
  offer_positioning: string[];
  constraints_avoid_claims: string[];
  constraints_allowed_channels: string[];
  constraints_languages: string[];
  policy_pack_id: string;
  created_at: string;
  v: number;
}

interface QueryObject {
  query_object_id: string;
  seller_id: string;
  buyer_context: string;
  priority: number;
  keywords: string[];
  exclusions: string[];
  rationale: string;
  v: number;
}

// H4 types
interface DraftListItem {
  draft_id: string;
  contact_id: string;
  account_id: string;
  channel: string;
  language: string;
  created_at: string;
}

interface AnchorOut {
  anchor_key: string;
  span: string;
  evidence_ids: string[];
}

interface EvidenceItemOut {
  evidence_id: string;
  source_type: string;
  url: string | null;
  claim_frame: string | null;
  snippet: string | null;
  captured_at: string | null;
}

interface ContactSummaryOut {
  contact_id: string;
  full_name: string | null;
  role: string | null;
  channels: string[];
}

interface AccountSummaryOut {
  account_id: string;
  name: string;
  domain: string | null;
  country: string | null;
}

interface DraftReviewOut {
  draft_id: string;
  contact: ContactSummaryOut;
  account: AccountSummaryOut;
  subject: string;
  body: string;
  channel: string;
  language: string;
  risk_flags: Array<Record<string, string>>;
  anchors: AnchorOut[];
  evidence_items: EvidenceItemOut[];
  v: number;
}

interface DecisionSubmittedOut {
  work_item_id: string;
  draft_id: string;
  status: string;
  created: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function splitLines(s: string): string[] {
  return s.split('\n').map(l => l.trim()).filter(Boolean);
}

function joinLines(arr: string[]): string {
  return arr.join('\n');
}

// ---------------------------------------------------------------------------
// SellerProfile form
// ---------------------------------------------------------------------------

const EMPTY_FORM = {
  seller_slug: '',
  offer_what: '',
  offer_where: '',
  offer_who: '',
  offer_positioning: '',
  constraints_avoid_claims: '',
  constraints_allowed_channels: '',
  constraints_languages: '',
};

type FormState = typeof EMPTY_FORM;

function SellerProfileForm({
  onProfileSaved,
}: {
  onProfileSaved: (sellerId: string) => void;
}) {
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [loadSlug, setLoadSlug] = useState('');
  const [status, setStatus] = useState('');
  const [loaded, setLoaded] = useState(false);

  function field(key: keyof FormState) {
    return {
      value: form[key],
      onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
        setForm(f => ({ ...f, [key]: e.target.value })),
    };
  }

  async function handleLoad() {
    if (!loadSlug.trim()) return;
    const sid = loadSlug.startsWith('seller:') ? loadSlug : `seller:${loadSlug}`;
    setStatus('Loading…');
    try {
      const r = await fetch(`${API}/seller-profiles/${encodeURIComponent(sid)}`);
      if (!r.ok) { setStatus('Not found'); return; }
      const sp: SellerProfile = await r.json();
      setForm({
        seller_slug: sp.seller_id.replace(/^seller:/, ''),
        offer_what: sp.offer_what,
        offer_where: joinLines(sp.offer_where),
        offer_who: joinLines(sp.offer_who),
        offer_positioning: joinLines(sp.offer_positioning),
        constraints_avoid_claims: joinLines(sp.constraints_avoid_claims),
        constraints_allowed_channels: joinLines(sp.constraints_allowed_channels),
        constraints_languages: joinLines(sp.constraints_languages),
      });
      setLoaded(true);
      setStatus('Loaded.');
    } catch {
      setStatus('Error loading profile.');
    }
  }

  async function handleSave() {
    if (!form.seller_slug.trim()) { setStatus('seller_slug required'); return; }
    const sid = `seller:${form.seller_slug.trim()}`;
    const body: Omit<SellerProfile, 'created_at'> & { created_at: string } = {
      seller_id: sid,
      offer_what: form.offer_what,
      offer_where: splitLines(form.offer_where),
      offer_who: splitLines(form.offer_who),
      offer_positioning: splitLines(form.offer_positioning),
      constraints_avoid_claims: splitLines(form.constraints_avoid_claims),
      constraints_allowed_channels: splitLines(form.constraints_allowed_channels),
      constraints_languages: splitLines(form.constraints_languages),
      policy_pack_id: 'safe_v0_1',
      created_at: new Date().toISOString(),
      v: 1,
    };

    setStatus('Saving…');
    try {
      if (loaded) {
        // Update existing
        const update = {
          offer_what: body.offer_what,
          offer_where: body.offer_where,
          offer_who: body.offer_who,
          offer_positioning: body.offer_positioning,
          constraints_avoid_claims: body.constraints_avoid_claims,
          constraints_allowed_channels: body.constraints_allowed_channels,
          constraints_languages: body.constraints_languages,
        };
        const r = await fetch(`${API}/seller-profiles/${encodeURIComponent(sid)}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(update),
        });
        if (!r.ok) { setStatus(`Update failed: ${r.status}`); return; }
      } else {
        // Create new
        const r = await fetch(`${API}/seller-profiles`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!r.ok) { setStatus(`Create failed: ${r.status}`); return; }
        setLoaded(true);
      }
      setStatus('Saved.');
      onProfileSaved(sid);
    } catch {
      setStatus('Error saving profile.');
    }
  }

  return (
    <section style={{ marginBottom: 32 }}>
      <h2>Seller Profile</h2>

      <div style={{ marginBottom: 12 }}>
        <input
          placeholder="seller_slug (e.g. my-company)"
          value={loadSlug}
          onChange={e => setLoadSlug(e.target.value)}
          style={{ width: 240 }}
        />
        <button onClick={handleLoad} style={{ marginLeft: 8 }}>Load</button>
      </div>

      <table cellPadding={4}>
        <tbody>
          <tr>
            <td><label>seller_slug</label></td>
            <td>
              <input {...field('seller_slug')} placeholder="my-company" style={{ width: 280 }} />
            </td>
          </tr>
          <tr>
            <td><label>offer.what</label></td>
            <td>
              <input {...field('offer_what')} placeholder="What you sell" style={{ width: 280 }} />
            </td>
          </tr>
          <tr>
            <td><label>offer.where</label></td>
            <td>
              <textarea {...field('offer_where')} rows={2} placeholder="One market per line" style={{ width: 280 }} />
            </td>
          </tr>
          <tr>
            <td><label>offer.who</label></td>
            <td>
              <textarea {...field('offer_who')} rows={2} placeholder="One persona per line" style={{ width: 280 }} />
            </td>
          </tr>
          <tr>
            <td><label>offer.positioning</label></td>
            <td>
              <textarea {...field('offer_positioning')} rows={2} placeholder="One point per line" style={{ width: 280 }} />
            </td>
          </tr>
          <tr>
            <td><label>constraints.avoid_claims</label></td>
            <td>
              <textarea {...field('constraints_avoid_claims')} rows={2} placeholder="One claim per line" style={{ width: 280 }} />
            </td>
          </tr>
          <tr>
            <td><label>constraints.allowed_channels</label></td>
            <td>
              <input {...field('constraints_allowed_channels')} placeholder="email, linkedin (one per line)" style={{ width: 280 }} />
            </td>
          </tr>
          <tr>
            <td><label>constraints.languages</label></td>
            <td>
              <input {...field('constraints_languages')} placeholder="en, de (one per line)" style={{ width: 280 }} />
            </td>
          </tr>
        </tbody>
      </table>

      <div style={{ marginTop: 12 }}>
        <button onClick={handleSave}>{loaded ? 'Update Profile' : 'Create Profile'}</button>
        {status && <span style={{ marginLeft: 12, color: '#555' }}>{status}</span>}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// QueryObject review screen
// ---------------------------------------------------------------------------

function QueryObjectRow({
  qo,
  onChange,
}: {
  qo: QueryObject;
  onChange: (updated: QueryObject) => void;
}) {
  const [draft, setDraft] = useState<QueryObject>(qo);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function handleSave() {
    setSaving(true);
    setSaved(false);
    try {
      const patch = {
        buyer_context: draft.buyer_context,
        priority: draft.priority,
        keywords: draft.keywords,
        exclusions: draft.exclusions,
        rationale: draft.rationale,
      };
      const r = await fetch(
        `${API}/query-objects/${encodeURIComponent(qo.query_object_id)}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(patch),
        },
      );
      if (r.ok) {
        const updated: QueryObject = await r.json();
        setDraft(updated);
        onChange(updated);
        setSaved(true);
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <tr style={{ verticalAlign: 'top', borderBottom: '1px solid #eee' }}>
      <td style={{ padding: '8px 4px', minWidth: 60 }}>
        <input
          type="number"
          step="0.01"
          value={draft.priority}
          onChange={e => setDraft(d => ({ ...d, priority: parseFloat(e.target.value) || 0 }))}
          style={{ width: 60 }}
        />
      </td>
      <td style={{ padding: '8px 4px', minWidth: 180 }}>
        <input
          value={draft.buyer_context}
          onChange={e => setDraft(d => ({ ...d, buyer_context: e.target.value }))}
          style={{ width: 220 }}
        />
      </td>
      <td style={{ padding: '8px 4px' }}>
        <textarea
          value={draft.keywords.join('\n')}
          onChange={e => setDraft(d => ({ ...d, keywords: splitLines(e.target.value) }))}
          rows={3}
          style={{ width: 160 }}
        />
      </td>
      <td style={{ padding: '8px 4px' }}>
        <textarea
          value={draft.exclusions.join('\n')}
          onChange={e => setDraft(d => ({ ...d, exclusions: splitLines(e.target.value) }))}
          rows={3}
          style={{ width: 160 }}
        />
      </td>
      <td style={{ padding: '8px 4px' }}>
        <textarea
          value={draft.rationale}
          onChange={e => setDraft(d => ({ ...d, rationale: e.target.value }))}
          rows={3}
          style={{ width: 200 }}
        />
      </td>
      <td style={{ padding: '8px 4px' }}>
        <button onClick={handleSave} disabled={saving}>
          {saving ? '…' : 'Save'}
        </button>
        {saved && <span style={{ marginLeft: 4, color: 'green' }}>✓</span>}
      </td>
    </tr>
  );
}

function QueryObjectReview({ sellerId }: { sellerId: string }) {
  const [queryObjects, setQueryObjects] = useState<QueryObject[]>([]);
  const [status, setStatus] = useState('');

  async function handleGenerate() {
    setStatus('Generating…');
    try {
      const r = await fetch(
        `${API}/seller-profiles/${encodeURIComponent(sellerId)}/query-objects`,
        { method: 'POST' },
      );
      if (!r.ok) { setStatus(`Generate failed: ${r.status}`); return; }
      const items: QueryObject[] = await r.json();
      setQueryObjects(items);
      setStatus(`Generated ${items.length} query objects.`);
    } catch {
      setStatus('Error generating query objects.');
    }
  }

  async function handleLoad() {
    setStatus('Loading…');
    try {
      const r = await fetch(
        `${API}/seller-profiles/${encodeURIComponent(sellerId)}/query-objects`,
      );
      if (!r.ok) { setStatus(`Load failed: ${r.status}`); return; }
      const items: QueryObject[] = await r.json();
      setQueryObjects(items);
      setStatus(items.length ? `Loaded ${items.length} query objects.` : 'No query objects yet.');
    } catch {
      setStatus('Error loading query objects.');
    }
  }

  function handleUpdated(updated: QueryObject) {
    setQueryObjects(qs => qs.map(q => q.query_object_id === updated.query_object_id ? updated : q));
  }

  return (
    <section>
      <h2>Query Objects — {sellerId}</h2>
      <div style={{ marginBottom: 12 }}>
        <button onClick={handleLoad} style={{ marginRight: 8 }}>Load Existing</button>
        <button onClick={handleGenerate}>Generate Query Objects</button>
        {status && <span style={{ marginLeft: 12, color: '#555' }}>{status}</span>}
      </div>

      {queryObjects.length > 0 && (
        <table style={{ borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#f5f5f5' }}>
              <th style={{ padding: '6px 4px' }}>Priority</th>
              <th style={{ padding: '6px 4px' }}>Buyer Context</th>
              <th style={{ padding: '6px 4px' }}>Keywords</th>
              <th style={{ padding: '6px 4px' }}>Exclusions</th>
              <th style={{ padding: '6px 4px' }}>Rationale</th>
              <th style={{ padding: '6px 4px' }}></th>
            </tr>
          </thead>
          <tbody>
            {queryObjects.map(qo => (
              <QueryObjectRow key={qo.query_object_id} qo={qo} onChange={handleUpdated} />
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// H4 — Draft list
// ---------------------------------------------------------------------------

function DraftList({ onSelect }: { onSelect: (draftId: string) => void }) {
  const [drafts, setDrafts] = useState<DraftListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState('');

  async function loadDrafts() {
    setLoading(true);
    setStatus('Loading…');
    try {
      const r = await fetch(`${API}/drafts`);
      if (!r.ok) { setStatus(`Error: ${r.status}`); return; }
      const items: DraftListItem[] = await r.json();
      setDrafts(items);
      setStatus(items.length ? '' : 'No drafts found.');
    } catch {
      setStatus('Failed to load drafts.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <section>
      <h2>Draft Review</h2>
      <div style={{ marginBottom: 12 }}>
        <button onClick={loadDrafts} disabled={loading}>
          {loading ? 'Loading…' : 'Load Drafts'}
        </button>
        {status && <span style={{ marginLeft: 12, color: '#555' }}>{status}</span>}
      </div>
      {drafts.length > 0 && (
        <table style={{ borderCollapse: 'collapse', fontSize: 13, width: '100%' }}>
          <thead>
            <tr style={{ background: '#f5f5f5' }}>
              <th style={{ padding: '6px 8px', textAlign: 'left' }}>Draft ID</th>
              <th style={{ padding: '6px 8px', textAlign: 'left' }}>Contact</th>
              <th style={{ padding: '6px 8px', textAlign: 'left' }}>Account</th>
              <th style={{ padding: '6px 8px', textAlign: 'left' }}>Channel</th>
              <th style={{ padding: '6px 8px', textAlign: 'left' }}>Created</th>
              <th style={{ padding: '6px 8px' }}></th>
            </tr>
          </thead>
          <tbody>
            {drafts.map(d => (
              <tr key={d.draft_id} style={{ borderBottom: '1px solid #eee' }}>
                <td style={{ padding: '6px 8px', fontFamily: 'monospace', fontSize: 11 }}>
                  {d.draft_id}
                </td>
                <td style={{ padding: '6px 8px' }}>{d.contact_id}</td>
                <td style={{ padding: '6px 8px' }}>{d.account_id}</td>
                <td style={{ padding: '6px 8px' }}>{d.channel}</td>
                <td style={{ padding: '6px 8px' }}>{d.created_at.slice(0, 16).replace('T', ' ')}</td>
                <td style={{ padding: '6px 8px' }}>
                  <button onClick={() => onSelect(d.draft_id)}>Review</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// H4 — Draft review screen
// ---------------------------------------------------------------------------

const STOP_CLASS_GATES = new Set(['HardSafetyGate', 'BudgetGate', 'suppression', 'complaint']);

function DraftReviewScreen({ draftId, onClose }: { draftId: string; onClose: () => void }) {
  const [review, setReview] = useState<DraftReviewOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedAnchorKey, setSelectedAnchorKey] = useState<string | null>(null);

  // Decision form
  const [reviewerId, setReviewerId] = useState('');
  const [reviewerRole, setReviewerRole] = useState<'operator' | 'admin'>('operator');
  const [decisionStatus, setDecisionStatus] = useState('approved');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitResult, setSubmitResult] = useState('');

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError('');
      try {
        const r = await fetch(`${API}/drafts/${encodeURIComponent(draftId)}`);
        if (!r.ok) { setError(`Draft not found (${r.status})`); return; }
        const data: DraftReviewOut = await r.json();
        setReview(data);
      } catch {
        setError('Failed to load draft.');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [draftId]);

  async function handleSubmitDecision() {
    if (!reviewerId.trim()) { setSubmitResult('reviewer_id required'); return; }
    setSubmitting(true);
    setSubmitResult('');
    try {
      const r = await fetch(`${API}/drafts/${encodeURIComponent(draftId)}/decision`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          status: decisionStatus,
          reviewer_id: reviewerId.trim(),
          reviewer_role: reviewerRole,
          notes: notes || null,
        }),
      });
      if (!r.ok) {
        const err = await r.json();
        setSubmitResult(`Error: ${err.detail || r.status}`);
        return;
      }
      const result: DecisionSubmittedOut = await r.json();
      setSubmitResult(
        result.created
          ? `Decision submitted (${result.work_item_id})`
          : 'Decision already recorded (idempotent replay).',
      );
    } catch {
      setSubmitResult('Network error submitting decision.');
    } finally {
      setSubmitting(false);
    }
  }

  // Highlight anchor spans in draft body.
  // All anchors are lightly highlighted; the selected one is bright.
  // Clicking a highlighted span selects/deselects its anchor.
  function renderBody(body: string, anchors: AnchorOut[]): React.ReactNode {
    if (!anchors.length) return body;

    // Find all span positions
    const hits: { start: number; end: number; anchorKey: string }[] = [];
    for (const anchor of anchors) {
      let idx = body.indexOf(anchor.span);
      while (idx !== -1) {
        hits.push({ start: idx, end: idx + anchor.span.length, anchorKey: anchor.anchor_key });
        idx = body.indexOf(anchor.span, idx + anchor.span.length);
      }
    }
    hits.sort((a, b) => a.start - b.start);

    // Remove overlaps (keep first match)
    const segments: typeof hits = [];
    let lastEnd = 0;
    for (const h of hits) {
      if (h.start >= lastEnd) { segments.push(h); lastEnd = h.end; }
    }

    const nodes: React.ReactNode[] = [];
    let pos = 0;
    for (const seg of segments) {
      if (seg.start > pos) {
        nodes.push(<React.Fragment key={`t${pos}`}>{body.slice(pos, seg.start)}</React.Fragment>);
      }
      const isSelected = seg.anchorKey === selectedAnchorKey;
      nodes.push(
        <mark
          key={`m${seg.start}`}
          title={`Anchor: ${seg.anchorKey}`}
          onClick={() => setSelectedAnchorKey(isSelected ? null : seg.anchorKey)}
          style={{
            background: isSelected ? '#ffd700' : '#fffacd',
            cursor: 'pointer',
            borderRadius: 2,
            padding: '0 1px',
            outline: isSelected ? '1px solid #cca000' : undefined,
          }}
        >
          {body.slice(seg.start, seg.end)}
        </mark>,
      );
      pos = seg.end;
    }
    if (pos < body.length) {
      nodes.push(<React.Fragment key="tend">{body.slice(pos)}</React.Fragment>);
    }
    return nodes;
  }

  if (loading) return <p style={{ color: '#555' }}>Loading draft…</p>;
  if (error) return (
    <p>
      <span style={{ color: 'red' }}>{error}</span>
      {' '}
      <button onClick={onClose}>Back</button>
    </p>
  );
  if (!review) return null;

  const selectedAnchor = review.anchors.find(a => a.anchor_key === selectedAnchorKey);
  const visibleEvidence = selectedAnchor
    ? review.evidence_items.filter(e => selectedAnchor.evidence_ids.includes(e.evidence_id))
    : review.evidence_items;

  const hasStopGate = review.risk_flags.some(f => STOP_CLASS_GATES.has(f.gate ?? ''));

  return (
    <section>
      {/* Header */}
      <div style={{ marginBottom: 12 }}>
        <button onClick={onClose}>← Back to list</button>
        <span style={{ marginLeft: 12, color: '#777', fontSize: 12, fontFamily: 'monospace' }}>
          {review.draft_id}
        </span>
      </div>

      {/* Evidence digest panel — contact + account summary */}
      <div style={{
        background: '#f9f9f9',
        border: '1px solid #e0e0e0',
        borderRadius: 4,
        padding: '8px 14px',
        marginBottom: 14,
        fontSize: 13,
      }}>
        <strong>Contact:</strong>{' '}
        {review.contact.full_name || review.contact.contact_id}
        {review.contact.role && <span style={{ marginLeft: 6, color: '#555' }}>({review.contact.role})</span>}
        {review.contact.channels.length > 0 && (
          <span style={{ marginLeft: 6, color: '#888' }}>[{review.contact.channels.join(', ')}]</span>
        )}
        <span style={{ margin: '0 14px', color: '#ccc' }}>|</span>
        <strong>Account:</strong>{' '}
        {review.account.name || review.account.account_id}
        {review.account.domain && <span style={{ marginLeft: 6, color: '#555' }}>{review.account.domain}</span>}
        {review.account.country && <span style={{ marginLeft: 6, color: '#888' }}>[{review.account.country}]</span>}
        <span style={{ margin: '0 14px', color: '#ccc' }}>|</span>
        <strong>Channel:</strong> {review.channel}
        <span style={{ margin: '0 6px', color: '#ccc' }}>·</span>
        <strong>Lang:</strong> {review.language}
      </div>

      {/* Gate outcomes panel */}
      {review.risk_flags.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <h4 style={{ margin: '0 0 8px', fontSize: 13 }}>Gate Outcomes</h4>
          {review.risk_flags.map((flag, i) => {
            const isStop = STOP_CLASS_GATES.has(flag.gate ?? '');
            return (
              <div
                key={i}
                style={{
                  background: isStop ? '#ffe8e8' : '#fff8e0',
                  border: `1px solid ${isStop ? '#e00' : '#cc0'}`,
                  borderRadius: 4,
                  padding: '6px 12px',
                  marginBottom: 6,
                  fontSize: 13,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                {isStop && (
                  <span style={{
                    background: '#c00',
                    color: '#fff',
                    borderRadius: 3,
                    padding: '1px 6px',
                    fontSize: 11,
                    fontWeight: 700,
                    flexShrink: 0,
                  }}>
                    STOP
                  </span>
                )}
                <strong>{flag.gate}</strong>
                <span style={{ color: '#555' }}>{flag.outcome}</span>
                {flag.reason && <span style={{ color: '#888' }}>— {flag.reason}</span>}
                {isStop && (
                  <span style={{ marginLeft: 'auto', color: '#c00', fontSize: 11 }}>
                    non-overridable
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Draft preview + anchor list (two columns) */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 14, alignItems: 'flex-start' }}>

        {/* Draft preview panel */}
        <div style={{ flex: 3 }}>
          <h4 style={{ margin: '0 0 6px', fontSize: 13 }}>Draft Preview</h4>
          <div style={{
            border: '1px solid #ddd',
            borderRadius: 4,
            padding: 14,
            background: '#fff',
          }}>
            <div style={{ marginBottom: 8, fontSize: 13 }}>
              <strong>Subject:</strong> {review.subject}
            </div>
            <hr style={{ margin: '8px 0', borderColor: '#eee', borderStyle: 'solid' }} />
            <div style={{ lineHeight: 1.7, fontSize: 14, whiteSpace: 'pre-wrap' }}>
              {renderBody(review.body, review.anchors)}
            </div>
          </div>
          {review.anchors.length > 0 && (
            <p style={{ margin: '4px 0 0', color: '#888', fontSize: 11 }}>
              Click highlighted text to filter evidence cards.
            </p>
          )}
        </div>

        {/* Anchor list panel */}
        <div style={{ flex: 1, minWidth: 200 }}>
          <h4 style={{ margin: '0 0 6px', fontSize: 13 }}>
            Anchors ({review.anchors.length})
            {selectedAnchorKey && (
              <button
                onClick={() => setSelectedAnchorKey(null)}
                style={{ marginLeft: 8, fontSize: 11, padding: '1px 6px' }}
              >
                Clear
              </button>
            )}
          </h4>
          {review.anchors.length === 0 ? (
            <p style={{ color: '#999', fontSize: 13 }}>No anchors.</p>
          ) : (
            <div style={{ border: '1px solid #ddd', borderRadius: 4, overflow: 'hidden' }}>
              {review.anchors.map(anchor => {
                const isSelected = anchor.anchor_key === selectedAnchorKey;
                return (
                  <div
                    key={anchor.anchor_key}
                    onClick={() => setSelectedAnchorKey(isSelected ? null : anchor.anchor_key)}
                    style={{
                      padding: '8px 10px',
                      cursor: 'pointer',
                      background: isSelected ? '#ffd700' : '#fff',
                      borderBottom: '1px solid #eee',
                      fontSize: 12,
                    }}
                  >
                    <div style={{ fontWeight: isSelected ? 600 : 400, marginBottom: 2, lineHeight: 1.3 }}>
                      {anchor.span.length > 70 ? anchor.span.slice(0, 67) + '…' : anchor.span}
                    </div>
                    <div style={{ color: '#999', fontSize: 11 }}>
                      {anchor.evidence_ids.length} evidence link{anchor.evidence_ids.length !== 1 ? 's' : ''}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Evidence cards panel */}
      <div style={{ marginBottom: 16 }}>
        <h4 style={{ margin: '0 0 8px', fontSize: 13 }}>
          Evidence Cards
          {selectedAnchor
            ? <span style={{ marginLeft: 8, fontWeight: 400, color: '#666' }}>
                — filtered by anchor ({visibleEvidence.length} of {review.evidence_items.length})
              </span>
            : <span style={{ marginLeft: 8, fontWeight: 400, color: '#888' }}>
                ({review.evidence_items.length} total)
              </span>
          }
        </h4>
        {visibleEvidence.length === 0 ? (
          <p style={{ color: '#999', fontSize: 13 }}>No evidence items.</p>
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
            {visibleEvidence.map(ev => (
              <div
                key={ev.evidence_id}
                style={{
                  border: '1px solid #ddd',
                  borderRadius: 4,
                  padding: 12,
                  width: 280,
                  fontSize: 13,
                  background: '#fff',
                  boxSizing: 'border-box',
                }}
              >
                <div style={{ marginBottom: 6, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  <span style={{
                    background: '#e8f4fd',
                    borderRadius: 3,
                    padding: '1px 6px',
                    fontSize: 11,
                  }}>
                    {ev.source_type}
                  </span>
                  {ev.captured_at && (
                    <span style={{ color: '#999', fontSize: 11, alignSelf: 'center' }}>
                      {ev.captured_at.slice(0, 10)}
                    </span>
                  )}
                </div>
                {ev.claim_frame && (
                  <div style={{ fontWeight: 600, marginBottom: 4, lineHeight: 1.3 }}>
                    {ev.claim_frame}
                  </div>
                )}
                {ev.snippet && (
                  <div style={{ color: '#444', marginBottom: 6, lineHeight: 1.4, fontStyle: 'italic' }}>
                    "{ev.snippet}"
                  </div>
                )}
                {ev.url && (
                  <a
                    href={ev.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ fontSize: 11, color: '#0066cc', wordBreak: 'break-all', display: 'block' }}
                  >
                    {ev.url}
                  </a>
                )}
                <div style={{ marginTop: 8, color: '#ccc', fontSize: 10, fontFamily: 'monospace' }}>
                  {ev.evidence_id}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Decision controls panel */}
      <div style={{
        border: '1px solid #ddd',
        borderRadius: 4,
        padding: 16,
        background: '#fafafa',
      }}>
        <h4 style={{ margin: '0 0 12px', fontSize: 13 }}>Decision Controls</h4>
        <table cellPadding={4}>
          <tbody>
            <tr>
              <td style={{ fontSize: 13 }}><label>Reviewer ID</label></td>
              <td>
                <input
                  value={reviewerId}
                  onChange={e => setReviewerId(e.target.value)}
                  placeholder="reviewer:alice"
                  style={{ width: 220 }}
                />
              </td>
            </tr>
            <tr>
              <td style={{ fontSize: 13 }}><label>Reviewer Role</label></td>
              <td>
                <select
                  value={reviewerRole}
                  onChange={e => setReviewerRole(e.target.value as 'operator' | 'admin')}
                >
                  <option value="operator">operator</option>
                  <option value="admin">admin</option>
                </select>
              </td>
            </tr>
            <tr>
              <td style={{ fontSize: 13 }}><label>Decision</label></td>
              <td>
                <select value={decisionStatus} onChange={e => setDecisionStatus(e.target.value)}>
                  <option value="approved">approved</option>
                  <option value="rejected">rejected</option>
                  <option value="needs_rewrite">needs_rewrite</option>
                  <option value="needs_more_evidence">needs_more_evidence</option>
                </select>
              </td>
            </tr>
            <tr>
              <td style={{ fontSize: 13, verticalAlign: 'top', paddingTop: 8 }}>
                <label>Notes</label>
              </td>
              <td>
                <textarea
                  value={notes}
                  onChange={e => setNotes(e.target.value)}
                  rows={3}
                  placeholder="Optional reviewer notes"
                  style={{ width: 340 }}
                />
              </td>
            </tr>
          </tbody>
        </table>
        <div style={{ marginTop: 12 }}>
          {hasStopGate && (
            <div style={{ color: '#c00', marginBottom: 8, fontSize: 12 }}>
              STOP-class gate active — decision recorded but downstream send will be blocked.
            </div>
          )}
          <button onClick={handleSubmitDecision} disabled={submitting}>
            {submitting ? 'Submitting…' : 'Submit Decision'}
          </button>
          {submitResult && (
            <span style={{ marginLeft: 12, color: '#555', fontSize: 13 }}>{submitResult}</span>
          )}
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// App root
// ---------------------------------------------------------------------------

function App() {
  const [activeSellerId, setActiveSellerId] = useState('');
  const [activeTab, setActiveTab] = useState<'setup' | 'review'>('setup');
  const [selectedDraftId, setSelectedDraftId] = useState<string | null>(null);

  return (
    <div style={{ fontFamily: 'sans-serif', maxWidth: 1100, margin: '32px auto', padding: '0 16px' }}>
      <h1>AOSE</h1>

      {/* Tab navigation */}
      <div style={{ marginBottom: 24, borderBottom: '2px solid #eee' }}>
        {(['setup', 'review'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '8px 20px',
              marginRight: 4,
              border: 'none',
              borderBottom: activeTab === tab ? '2px solid #333' : '2px solid transparent',
              background: 'none',
              cursor: 'pointer',
              fontWeight: activeTab === tab ? 600 : 400,
              fontSize: 14,
              marginBottom: -2,
            }}
          >
            {tab === 'setup' ? 'Seller Setup' : 'Draft Review'}
          </button>
        ))}
      </div>

      {activeTab === 'setup' && (
        <>
          <SellerProfileForm onProfileSaved={setActiveSellerId} />
          {activeSellerId && <QueryObjectReview sellerId={activeSellerId} />}
        </>
      )}

      {activeTab === 'review' && (
        selectedDraftId
          ? (
            <DraftReviewScreen
              draftId={selectedDraftId}
              onClose={() => setSelectedDraftId(null)}
            />
          )
          : <DraftList onSelect={setSelectedDraftId} />
      )}
    </div>
  );
}

export default App;
