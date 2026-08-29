import { useQuery } from 'convex/react';
import { api } from '../../convex/_generated/api';
import { useExperimentName, useWorldStatus } from '../hooks/useWorldStatus';
import FreezeButton from './FreezeButton';
import MusicButton from './buttons/MusicButton';
import InteractButton from './buttons/InteractButton';
import Button from './buttons/Button';
import helpImg from '../../assets/help.svg';

/**
 * The instrument rail.
 *
 * This is a research instrument, not a landing page: the scarce resource is
 * screen space for the world, so the header is one thin strip and everything
 * in it is live state a watcher actually wants — which experiment they are
 * looking at, and whether its engine is still ticking.
 */
function Readout({ label, value }: { label: string; value: string | number | undefined }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="text-[10px] uppercase tracking-[0.15em] text-clay-500">{label}</span>
      <span className="text-sm tabular-nums text-clay-100">{value ?? '—'}</span>
    </div>
  );
}

export default function TopBar({ onHelp }: { onHelp: () => void }) {
  const experiment = useExperimentName();
  const worldStatus = useWorldStatus();
  const worldId = worldStatus?.worldId;
  const worldState = useQuery(api.world.worldState, worldId ? { worldId } : 'skip');

  const world = worldState?.world;
  const engine = worldState?.engine;
  const status = worldStatus?.status;
  // `running` is the engine's own flag; the world can also be paused by a
  // developer or idled out, and those are different things to a watcher.
  const live = status === 'running' && engine?.running;

  return (
    <header className="z-20 flex shrink-0 items-center gap-x-5 gap-y-2 flex-wrap border-b-2 border-black/60 bg-brown-900/95 px-4 py-2 backdrop-blur">
      <div className="flex items-baseline gap-2">
        <span className="font-display text-lg leading-none text-brown-200">headlong</span>
        <span className="font-display text-lg leading-none text-brown-500">town</span>
      </div>

      <div className="flex items-center gap-2" title="Which experiment this tab is watching">
        <span className="text-[10px] uppercase tracking-[0.15em] text-clay-500">experiment</span>
        <span className="border border-clay-700 bg-black/30 px-1.5 py-0.5 text-sm text-brown-300">
          {experiment ?? 'default'}
        </span>
      </div>

      <div className="flex items-center gap-1.5" title={`Engine status: ${status ?? 'unknown'}`}>
        <span
          className={
            'h-2 w-2 shrink-0 ' +
            (live ? 'animate-pulse bg-brown-300' : 'bg-clay-500')
          }
        />
        <span className="text-sm text-clay-100">{live ? 'live' : status ?? 'connecting'}</span>
      </div>

      <div className="hidden items-center gap-5 sm:flex">
        {/* Generation increments on every engine restart, so it doubles as a
            liveness tell: frozen number, stalled engine. */}
        <Readout label="gen" value={engine?.generationNumber} />
        <Readout label="agents" value={world?.agents.length} />
        <Readout label="people" value={world?.players.length} />
        <Readout label="talking" value={world?.conversations.length} />
      </div>

      <div className="ml-auto flex items-center gap-2">
        <FreezeButton />
        <MusicButton />
        <InteractButton />
        <Button imgUrl={helpImg} onClick={onHelp} compact>
          Help
        </Button>
      </div>
    </header>
  );
}
