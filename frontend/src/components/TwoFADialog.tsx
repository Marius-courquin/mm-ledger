import { useState } from 'react';

interface TwoFADialogProps {
  connectorId: string;
  detail: string;
  onSubmit: (code: string) => Promise<void>;
  onClose: () => void;
}

export function TwoFADialog({ connectorId, detail, onSubmit, onClose }: TwoFADialogProps) {
  const [code, setCode] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit() {
    if (!code.trim()) return;
    setIsSubmitting(true);
    try {
      await onSubmit(code.trim());
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    // Backdrop overlay
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      {/* Dialog */}
      <div className="bg-mm-surface border border-mm-border rounded-[16px] w-full max-w-md p-6 flex flex-col gap-5" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-mm-text">Two-Factor Authentication</h2>
        <div className="flex flex-col gap-3">
          <p className="text-sm text-mm-text-secondary">{detail}</p>
          <p className="text-xs text-mm-text-muted">
            Connector: <span className="font-medium text-mm-text-secondary">{connectorId}</span>
          </p>
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-mm-text-secondary">Verification Code</label>
            <input
              type="text"
              placeholder="000000"
              maxLength={6}
              value={code}
              onChange={e => setCode(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleSubmit(); }}
              autoFocus
              className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-3 py-2.5 text-mm-text text-center text-lg tracking-[0.3em] tabular-nums placeholder:text-mm-text-muted outline-none focus:border-mm-gold transition-colors"
            />
          </div>
        </div>
        <div className="flex justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 text-sm text-mm-text-muted hover:text-mm-text-secondary transition-colors">
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={isSubmitting || code.trim().length === 0}
            className="px-5 py-2 bg-mm-gold text-mm-bg text-sm font-semibold rounded-[8px] disabled:opacity-50 transition-opacity"
          >
            {isSubmitting ? 'Submitting...' : 'Submit'}
          </button>
        </div>
      </div>
    </div>
  );
}
