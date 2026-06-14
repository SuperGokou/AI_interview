import { useState } from 'react';
import PlasmaOrb, { type OrbStatus, type Integrity } from '../../components/PlasmaOrb';
import Button from '../../ui/Button';

const STATUS_OPTIONS: OrbStatus[] = ['idle', 'listening', 'asking', 'alert'];
const INTEGRITY_OPTIONS: Integrity[] = ['green', 'yellow', 'red'];

export default function Landing() {
  const [status, setStatus] = useState<OrbStatus>('asking');
  const [integrity, setIntegrity] = useState<Integrity>('green');

  return (
    <main
      style={{
        minHeight: '100vh',
        background: '#06080F',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '2rem',
        padding: '2rem',
      }}
    >
      <h1 style={{ color: '#E8EEF9', margin: 0, fontSize: '1.5rem', letterSpacing: '0.05em' }}>
        菜鸟庆面试 · 候选人入口
      </h1>

      <PlasmaOrb size={240} status={status} integrity={integrity} />

      {/* Status toggle row */}
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', justifyContent: 'center' }}>
        {STATUS_OPTIONS.map((s) => (
          <Button
            key={s}
            variant={status === s ? 'primary' : 'ghost'}
            onClick={() => setStatus(s)}
          >
            {s}
          </Button>
        ))}
      </div>

      {/* Integrity toggle row */}
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', justifyContent: 'center' }}>
        {INTEGRITY_OPTIONS.map((ig) => (
          <Button
            key={ig}
            variant={integrity === ig ? 'primary' : 'ghost'}
            onClick={() => setIntegrity(ig)}
          >
            {ig}
          </Button>
        ))}
      </div>
    </main>
  );
}
