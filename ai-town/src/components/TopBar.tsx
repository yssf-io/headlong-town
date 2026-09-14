import { useQuery } from 'convex/react';
import { api } from '../../convex/_generated/api';
import { useExperimentName, useWorldStatus } from '../hooks/useWorldStatus';
import { mindDashboardUrl } from '../mindDashboard';
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
  if (s < 90) return `${s}s`;
  const m = Math.round(s / 60);
  if (m < 90) return `${m}m`;
  return `${Math.round(m / 60)}h`;
}

// One mind: thinking right now, or how long since it last finished anything.
// A body can stand in the street looking perfectly well while the identity
// driving it is wedged, deadlocked or out of credit -- "green and recent" is
// the reassurance the town itself cannot give.
type MindHealth = {
  name: string;
  running: boolean;
  lastWakeAt?: number;
  lastFinalAt?: number;
  lastError?: string;
  lastErrorAt?: number;
};

function MindChip({ mind }: { mind: MindHealth }) {
  const failing =
    mind.lastError && (!mind.lastFinalAt || (mind.lastErrorAt ?? 0) > mind.lastFinalAt);
  const dot = failing ? 'bg-red-400' : mind.running ? 'bg-green-400' : 'bg-clay-500';
  const detail = failing
    ? String(mind.lastError)
    : mind.running
      ? `thinking${mind.lastWakeAt ? ` (started ${since(mind.lastWakeAt)} ago)` : ''}`
      : mind.lastFinalAt
        ? `idle, last finished ${since(mind.lastFinalAt)} ago`
        : 'idle, nothing finished yet';
  return (
    <a
      href={mindDashboardUrl(mind.name)}
      target="_blank"
      rel="noreferrer"
      className="flex items-baseline gap-1 text-sm text-clay-100 hover:text-white hover:underline decoration-clay-500 underline-offset-2"
      title={`${mind.name}: ${detail}\nOpen its mind log`}
    >
      <span className={`inline-block h-1.5 w-1.5 rounded-full ${dot}`} />
      <span>{mind.name}</span>
      <span className="text-clay-500 tabular-nums">
        {failing ? '!' : mind.running ? '…' : mind.lastFinalAt ? since(mind.lastFinalAt) : '—'}
      </span>
    </a>
  );
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

  // Per mind, not an aggregate: with a handful of minds the question is
  // "which one is stuck", and a fraction cannot answer it.
  const minds = (health?.minds ?? []).slice().sort((a, b) => a.name.localeCompare(b.name));

  const budget = health?.budget;
  const budgetLabel = budget
    ? `$${budget.spent.toFixed(2)}${budget.limit != null ? ` / $${budget.limit.toFixed(0)}` : ''}`
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
        <div className="flex items-baseline gap-2">
          <span className="text-[10px] uppercase tracking-[0.15em] text-clay-500">minds</span>
          {minds.length === 0 ? (
            <span className="text-sm text-clay-100">—</span>
          ) : (
            minds.map((m) => <MindChip key={m.name} mind={m} />)
          )}
        </div>
        {npcCount > 0 && <Readout label="npcs" value={npcCount} />}
        {/* AI Town keeps a conversation object alive from acceptance until
            somebody leaves, so this counts OPEN CONVERSATIONS -- not whether
            anyone is speaking. Two minds who said goodbye but never ran
            `town leave` still read 1. */}
        <span title="Open conversations. One stays open until someone leaves, so this can read 1 through a long silence.">
          <Readout label="in conversation" value={world?.conversations.length} />
        </span>
        <span title="Spent on this API key so far.">
          <Readout label="spent" value={budgetLabel} />
        </span>
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
