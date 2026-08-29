import { useQuery } from 'convex/react';
import { api } from '../../convex/_generated/api';

/**
 * Which experiment this browser tab is watching, from `?experiment=<name>`.
 *
 * Several towns run at once (PLAN.md §7) — different personas, different
 * framings — and each is its own world with its own engine. No parameter means
 * the default world, so the stock single-town setup is unaffected.
 */
export function useExperimentName(): string | undefined {
  if (typeof window === 'undefined') return undefined;
  const value = new URLSearchParams(window.location.search).get('experiment');
  return value ?? undefined;
}

/** The world status for this tab's experiment, or the default world. */
export function useWorldStatus() {
  return useQuery(api.world.worldStatusForExperiment, { experiment: useExperimentName() });
}
