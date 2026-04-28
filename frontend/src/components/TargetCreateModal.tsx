import { useEffect, useState } from 'react';
import {
  Modal, ModalContent, ModalHeader, ModalBody, ModalFooter,
  Button, Input, Select, SelectItem, Tabs, Tab,
} from '@heroui/react';
import { createTarget } from '@/api/targets';
import { getAccounts } from '@/api/accounts';
import type { TargetCreatePayload, AllocationKind } from '@/lib/targets';

interface Account { id: string; name?: string | null; type?: string | null; }

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onCreated: () => void;
}

export function TargetCreateModal({ isOpen, onClose, onCreated }: Props) {
  const [type, setType] = useState<'asset' | 'bucket'>('bucket');
  const [name, setName] = useState('');
  const [targetAmount, setTargetAmount] = useState('');
  const [accounts, setAccounts] = useState<Account[]>([]);

  const [assetAccount, setAssetAccount] = useState('');
  const [assetSymbol, setAssetSymbol] = useState('');

  const [slices, setSlices] = useState<Array<{
    account_id: string; allocation_kind: AllocationKind; allocation_value: number;
  }>>([]);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      getAccounts().then(setAccounts).catch(() => setAccounts([]));
      setName('');
      setTargetAmount('');
      setAssetAccount('');
      setAssetSymbol('');
      setSlices([]);
      setError(null);
    }
  }, [isOpen]);

  async function submit() {
    setError(null);
    const amount = parseFloat(targetAmount);
    if (!name.trim() || !(amount > 0)) {
      setError('Nom et montant cible obligatoires');
      return;
    }
    const payload: TargetCreatePayload = { name, type, target_amount: amount, slices: [] };
    if (type === 'asset') {
      if (!assetAccount || !assetSymbol) {
        setError('Compte et symbole obligatoires pour une cible sur actif');
        return;
      }
      payload.asset_account_id = assetAccount;
      payload.asset_symbol = assetSymbol;
    } else {
      payload.slices = slices;
    }
    setSubmitting(true);
    try {
      await createTarget(payload);
      onCreated();
      onClose();
    } catch (e: any) {
      setError(e?.detail ?? 'Erreur à la création');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="2xl">
      <ModalContent>
        <ModalHeader>Nouvelle cible</ModalHeader>
        <ModalBody className="space-y-4">
          <Tabs selectedKey={type} onSelectionChange={(k) => setType(k as 'asset' | 'bucket')}>
            <Tab key="bucket" title="Bucket abstrait">
              <div className="space-y-2 mt-2">
                <p className="text-sm text-default-500">
                  Composé de slices d'allocation sur tes comptes (ex. 30 % du CTO + 1 500 € du Livret A).
                </p>
              </div>
            </Tab>
            <Tab key="asset" title="Actif précis">
              <div className="space-y-2 mt-2">
                <p className="text-sm text-default-500">
                  Lié à une position spécifique (ex. atteindre 5 000 € sur VWCE).
                </p>
              </div>
            </Tab>
          </Tabs>

          <Input label="Nom" value={name} onValueChange={setName} placeholder="Ex. Apport immo" />
          <Input
            label="Montant cible (€)"
            type="number"
            value={targetAmount}
            onValueChange={setTargetAmount}
          />

          {type === 'asset' && (
            <>
              <Select
                label="Compte"
                selectedKeys={assetAccount ? [assetAccount] : []}
                onSelectionChange={(k) => setAssetAccount(Array.from(k)[0] as string ?? '')}
              >
                {accounts.map((a) => (
                  <SelectItem key={a.id}>{a.name ?? a.id}</SelectItem>
                ))}
              </Select>
              <Input
                label="Symbole / ISIN"
                value={assetSymbol}
                onValueChange={setAssetSymbol}
                placeholder="VWCE / IE00BK5BQT80"
              />
            </>
          )}

          {type === 'bucket' && (
            <SliceListEditor accounts={accounts} slices={slices} onChange={setSlices} />
          )}

          {error && <p className="text-sm text-mm-loss">{error}</p>}
        </ModalBody>
        <ModalFooter>
          <Button variant="flat" onPress={onClose}>Annuler</Button>
          <Button color="primary" onPress={submit} isLoading={submitting}>Créer</Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}

function SliceListEditor({
  accounts, slices, onChange,
}: {
  accounts: Account[];
  slices: Array<{ account_id: string; allocation_kind: AllocationKind; allocation_value: number; }>;
  onChange: (s: typeof slices) => void;
}) {
  function addSlice() {
    onChange([...slices, { account_id: accounts[0]?.id ?? '', allocation_kind: 'percent', allocation_value: 0 }]);
  }
  function update(idx: number, patch: Partial<typeof slices[0]>) {
    const next = slices.slice();
    next[idx] = { ...next[idx], ...patch };
    onChange(next);
  }
  function remove(idx: number) {
    onChange(slices.filter((_, i) => i !== idx));
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">Slices d'allocation</span>
        <Button size="sm" variant="flat" onPress={addSlice}>+ Ajouter</Button>
      </div>
      {slices.length === 0 && (
        <p className="text-xs text-default-500">Ajoute au moins une slice (un compte source + montant ou %).</p>
      )}
      {slices.map((s, i) => (
        <div key={i} className="flex gap-2 items-end">
          <Select
            label="Compte"
            className="flex-1"
            selectedKeys={s.account_id ? [s.account_id] : []}
            onSelectionChange={(k) => update(i, { account_id: Array.from(k)[0] as string ?? '' })}
          >
            {accounts.map((a) => (
              <SelectItem key={a.id}>{a.name ?? a.id}</SelectItem>
            ))}
          </Select>
          <Select
            label="Type"
            className="w-32"
            selectedKeys={[s.allocation_kind]}
            onSelectionChange={(k) => update(i, { allocation_kind: Array.from(k)[0] as AllocationKind })}
          >
            <SelectItem key="percent">%</SelectItem>
            <SelectItem key="amount">€</SelectItem>
          </Select>
          <Input
            label="Valeur"
            type="number"
            className="w-32"
            value={String(s.allocation_value)}
            onValueChange={(v) => update(i, { allocation_value: parseFloat(v) || 0 })}
          />
          <Button size="sm" color="danger" variant="flat" onPress={() => remove(i)}>×</Button>
        </div>
      ))}
    </div>
  );
}
