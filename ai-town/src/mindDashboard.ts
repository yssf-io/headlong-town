// Where the mind dashboard (headlong-web) lives.
//
// The town shows you a body; the dashboard shows you the mind behind it. Being
// able to get from one to the other without knowing a second URL is most of
// what makes this watchable.
//
// Defaults to the same host the town is served from, on headlong-web's default
// port, so localhost and a tailnet address both work with no configuration.
// Override with VITE_MIND_DASHBOARD_URL when it runs somewhere else.
export function mindDashboardBase(): string {
  const configured = import.meta.env.VITE_MIND_DASHBOARD_URL as string | undefined;
  const base = configured ?? `${window.location.protocol}//${window.location.hostname}:8080`;
  return base.replace(/\/$/, '');
}

/** The identity id headlong-web uses in its routes, e.g. `identities~ada`. */
export function identityId(name: string): string {
  return `identities~${encodeURIComponent(name)}`;
}

/** A mind's log — what it is thinking, run by run. */
export function mindDashboardUrl(name: string, view: 'mindlog' | 'memories' | 'health' | '' = 'mindlog'): string {
  const suffix = view ? `/${view}` : '';
  return `${mindDashboardBase()}/i/${identityId(name)}${suffix}`;
}
