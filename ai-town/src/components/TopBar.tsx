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
// "how long since" in the shortest form that is still honest.
function since(ms: number): string {
  const s = Math.max(0, Math.round((Date.now() - ms) / 1000));
  if (s < 90) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 90) return `${m}m ago`;
  return `${Math.round(m / 60)}h ago`;
}

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
  const health = useQuery(api.mindStatus.forWorld, worldId ? { worldId } : 'skip');

  const world = worldState?.world;
  const engine = worldState?.engine;
  const status = worldStatus?.status;
  // `running` is the engine's own flag; the world can also be paused by a
  // developer or idled out, and those are different things to a watcher.
  const live = status === 'running' && engine?.running;

  const npcCount = world?.agents.length ?? 0;
  const mindCount = (world?.players.length ?? 0) - npcCount;

  // How many minds are mid-run, and how long since the quietest one last
  // finished anything. A body can stand in the street looking well while the
  // identity driving it is wedged, deadlocked or out of credit -- which is how
  // every long outage in this project stayed invisible.
  const minds = health?.minds ?? [];
  const runningNow = minds.filter((m) => m.running).length;
  const lastFinals = minds.map((m) => m.lastFinalAt).filter((t): t is number => !!t);
  const stalest = lastFinals.length === minds.length && lastFinals.length > 0
    ? Math.min(...lastFinals)
    : undefined;
  // A mind whose most recent outcome was an error, not a completed run.
  const failing = minds.filter(
    (m) => m.lastError && (!m.lastFinalAt || (m.lastErrorAt ?? 0) > m.lastFinalAt),
  );
  const thinkingLabel = minds.length
    ? `${runningNow}/${minds.length}` +
      (stalest ? ` · ${since(stalest)}` : '') +
      (failing.length ? ` · ${failing.length} failing` : '')
    : undefined;

  const budget = health?.budget;
  const budgetLabel = budget
    ? budget.limit != null
      ? `$${Math.max(budget.limit - budget.spent, 0).toFixed(2)} left`
      : `$${budget.spent.toFixed(2)} spent`
    : undefined;

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
        {/* `players` is every body in the town. Headlong minds take their
            bodies through the same path a human does, so this counts them --
            it is NOT a count of humans. `agents` is AI Town's own stateless
            NPCs, which most experiments run none of. Labelling those "people"
            and "agents" had it exactly backwards for this project. */}
        <Readout label="minds" value={mindCount} />
        {npcCount > 0 && <Readout label="npcs" value={npcCount} />}
        <Readout label="talking" value={world?.conversations.length} />
        <span title={failing.length ? failing.map((m) => `${m.name}: ${m.lastError}`).join('\n') : 'minds mid-run / total, and how long since the quietest one finished anything'}>
          <Readout label="thinking" value={thinkingLabel} />
        </span>
        <Readout label="budget" value={budgetLabel} />
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
