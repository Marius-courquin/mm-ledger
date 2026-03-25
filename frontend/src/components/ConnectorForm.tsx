import { useState, useMemo } from 'react';
import type { Connector, ConnectorTypeInfo, ConnectorType, CredentialField } from '@/lib/types';

const BP_REGIONS: { code: string; label: string }[] = [
  { code: '14707', label: 'Alsace Lorraine Champagne' },
  { code: '10907', label: 'Aquitaine Centre Atlantique' },
  { code: '16807', label: 'Auvergne Rhône Alpes' },
  { code: '10807', label: 'Bourgogne Franche Comté' },
  { code: '13807', label: 'Grand Ouest' },
  { code: '14607', label: 'Méditerranée' },
  { code: '13507', label: 'Nord' },
  { code: '17807', label: 'Occitane' },
  { code: '10207', label: 'Rives de Paris' },
  { code: '16607', label: 'Sud' },
  { code: '18707', label: 'Val de France' },
];

interface ConnectorFormProps {
  isOpen: boolean;
  onClose: () => void;
  connectorTypes: ConnectorTypeInfo[];
  onSubmit: (data: {
    type: ConnectorType;
    label: string;
    credentials: Record<string, string>;
    config: Record<string, string>;
  }) => Promise<void>;
  initial?: Connector;
}

function buildDefaults(fields: CredentialField[]): Record<string, string> {
  const defaults: Record<string, string> = {};
  for (const f of fields) {
    if (f.default !== undefined) {
      defaults[f.name] = String(f.default);
    }
  }
  return defaults;
}

export function ConnectorForm({
  isOpen,
  onClose,
  connectorTypes,
  onSubmit,
  initial,
}: ConnectorFormProps) {
  const isEdit = !!initial;

  const [selectedType, setSelectedType] = useState<ConnectorType | ''>(
    initial?.type ?? '',
  );
  const [label, setLabel] = useState(initial?.label ?? '');
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [config, setConfig] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const typeInfo = useMemo(
    () => connectorTypes.find((ct) => ct.type === selectedType),
    [connectorTypes, selectedType],
  );

  function handleTypeChange(type: ConnectorType) {
    setSelectedType(type);
    const info = connectorTypes.find((ct) => ct.type === type);
    if (info) {
      setCredentials(buildDefaults(info.credential_fields));
      setConfig(buildDefaults(info.config_fields));
    }
  }

  function setCredentialField(name: string, value: string) {
    setCredentials((prev) => ({ ...prev, [name]: value }));
  }

  function setConfigField(name: string, value: string) {
    setConfig((prev) => ({ ...prev, [name]: value }));
  }

  async function handleSubmit() {
    if (!selectedType || !label.trim()) return;
    setIsSubmitting(true);
    try {
      await onSubmit({
        type: selectedType as ConnectorType,
        label: label.trim(),
        credentials,
        config,
      });
      onClose();
    } finally {
      setIsSubmitting(false);
    }
  }

  function isRegionField(field: CredentialField): boolean {
    return field.name === 'region' && selectedType === 'woob_bank';
  }

  function renderField(
    field: CredentialField,
    values: Record<string, string>,
    onChange: (name: string, value: string) => void,
  ) {
    const fieldLabel = field.name.replace(/_/g, ' ').toLowerCase();

    // Special: BP region dropdown
    if (isRegionField(field)) {
      return (
        <div key={field.name} className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-mm-text-secondary capitalize">
            Région
          </label>
          <select
            value={values[field.name] ?? ''}
            onChange={(e) => onChange(field.name, e.target.value)}
            className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-3 py-2 text-sm text-mm-text outline-none focus:border-mm-gold transition-colors appearance-none cursor-pointer"
          >
            <option value="">Sélectionner une région</option>
            {BP_REGIONS.map((r) => (
              <option key={r.code} value={r.code}>{r.label}</option>
            ))}
          </select>
        </div>
      );
    }

    // Skip bank_module for woob — hardcoded to banquepopulaire
    if (field.name === 'bank_module' && selectedType === 'woob_bank') {
      return null;
    }

    return (
      <div key={field.name} className="flex flex-col gap-1.5">
        <label className="text-xs font-medium text-mm-text-secondary capitalize">
          {fieldLabel}
          {field.required && <span className="text-red-400 ml-0.5">*</span>}
        </label>
        <input
          type={field.type === 'password' ? 'password' : 'text'}
          placeholder={field.placeholder}
          value={values[field.name] ?? ''}
          onChange={(e) => onChange(field.name, e.target.value)}
          className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-3 py-2 text-sm text-mm-text placeholder:text-mm-text-muted outline-none focus:border-mm-gold transition-colors"
        />
      </div>
    );
  }

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-mm-surface border border-mm-border rounded-[16px] w-full max-w-lg p-6 flex flex-col gap-5 max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-mm-text">
          {isEdit ? 'Modifier le connecteur' : 'Ajouter un connecteur'}
        </h2>

        <div className="flex flex-col gap-4">
          {/* Connector Type */}
          {isEdit ? (
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-mm-text-secondary">Type</label>
              <div className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-3 py-2 text-sm text-mm-text opacity-60">
                {connectorTypes.find((ct) => ct.type === selectedType)?.label ?? selectedType}
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-mm-text-secondary">Type de connecteur</label>
              <select
                value={selectedType}
                onChange={(e) => {
                  const val = e.target.value as ConnectorType;
                  if (val) handleTypeChange(val);
                }}
                className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-3 py-2 text-sm text-mm-text outline-none focus:border-mm-gold transition-colors appearance-none cursor-pointer"
              >
                <option value="" disabled>Choisir un type</option>
                {connectorTypes.map((ct) => (
                  <option key={ct.type} value={ct.type}>{ct.label}</option>
                ))}
              </select>
            </div>
          )}

          {/* Label — the only required user input */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-mm-text-secondary">
              Nom <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              placeholder="ex: Mon Trade Republic"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              className="bg-mm-surface-elevated border border-mm-border rounded-[8px] px-3 py-2 text-sm text-mm-text placeholder:text-mm-text-muted outline-none focus:border-mm-gold transition-colors"
            />
          </div>

          {/* Credential fields (skip hidden ones) */}
          {typeInfo && typeInfo.credential_fields.length > 0 && (
            <div className="flex flex-col gap-3">
              {typeInfo.credential_fields.map((field) =>
                renderField(field, credentials, setCredentialField)
              )}
            </div>
          )}

          {/* Config fields */}
          {typeInfo && typeInfo.config_fields.length > 0 && (
            <div className="flex flex-col gap-3">
              {typeInfo.config_fields.map((field) =>
                renderField(field, config, setConfigField)
              )}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-mm-text-muted hover:text-mm-text-secondary transition-colors"
          >
            Annuler
          </button>
          <button
            onClick={handleSubmit}
            disabled={isSubmitting || !selectedType || !label.trim()}
            className="px-5 py-2 bg-mm-gold text-mm-bg text-sm font-semibold rounded-[8px] disabled:opacity-50 transition-opacity"
          >
            {isSubmitting ? 'En cours...' : isEdit ? 'Enregistrer' : 'Ajouter'}
          </button>
        </div>
      </div>
    </div>
  );
}
