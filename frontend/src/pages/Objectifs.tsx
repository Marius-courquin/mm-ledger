import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardBody, CardHeader, Button, Progress, Chip } from '@heroui/react';
import { listTargets, getProgression } from '@/api/targets';
import type { Target, Progression } from '@/lib/targets';
import { TargetCreateModal } from '@/components/TargetCreateModal';

interface TargetWithProgression extends Target {
  progression?: Progression;
}

export function Objectifs() {
  const [targets, setTargets] = useState<TargetWithProgression[]>([]);
  const [loading, setLoading] = useState(true);
  const [showArchived, setShowArchived] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const list = await listTargets(showArchived);
      const withProg = await Promise.all(
        list.map(async (t) => {
          try {
            const p = await getProgression(t.id);
            return { ...t, progression: p } as TargetWithProgression;
          } catch {
            return t as TargetWithProgression;
          }
        })
      );
      setTargets(withProg);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [showArchived]);

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Objectifs</h1>
        <div className="flex gap-2">
          <Button
            variant={showArchived ? 'solid' : 'flat'}
            onPress={() => setShowArchived((v) => !v)}
          >
            {showArchived ? 'Afficher actives' : 'Afficher archivées'}
          </Button>
          <Button color="primary" onPress={() => setCreateOpen(true)}>
            Nouvelle cible
          </Button>
        </div>
      </div>

      {loading && <div className="text-sm text-default-500">Chargement…</div>}

      {!loading && targets.length === 0 && (
        <Card><CardBody className="text-center text-default-500 py-12">
          Aucune cible pour l'instant. Crée ta première cible pour démarrer.
        </CardBody></Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {targets.map((t) => {
          const pct = Math.min(100, t.progression?.progress_pct ?? 0);
          const eta = t.progression?.eta_months;
          const status = t.progression?.eta_status;
          return (
            <Link key={t.id} to={`/objectifs/${t.id}`}>
              <Card className="hover:scale-[1.01] transition-transform">
                <CardHeader className="flex justify-between items-start">
                  <div>
                    <div className="font-medium">{t.name}</div>
                    <Chip size="sm" variant="flat" className="mt-1">
                      {t.type === 'asset' ? 'Actif' : 'Bucket'}
                    </Chip>
                  </div>
                  <div className="text-right">
                    <div className="text-sm text-default-500">cible</div>
                    <div className="font-mono">{t.target_amount.toLocaleString('fr-FR')} €</div>
                  </div>
                </CardHeader>
                <CardBody className="space-y-2">
                  <Progress value={pct} className="w-full" />
                  <div className="flex justify-between text-sm">
                    <span>{(t.progression?.current_value ?? 0).toLocaleString('fr-FR')} €</span>
                    <span className="text-default-500">{pct.toFixed(1)} %</span>
                  </div>
                  <div className="text-xs text-default-500">
                    {status === 'reached' && '🎉 Atteint'}
                    {status === 'ok' && eta != null && `À ton rythme : ${Math.round(eta)} mois`}
                    {status === 'insufficient' && 'Rythme insuffisant'}
                  </div>
                </CardBody>
              </Card>
            </Link>
          );
        })}
      </div>

      <TargetCreateModal isOpen={createOpen} onClose={() => setCreateOpen(false)} onCreated={load} />
    </div>
  );
}
