// Health of the minds behind the bodies.
//
// AI Town knows about players; it knows nothing about whether the Headlong
// identity driving one is actually thinking. That gap is why every long outage
// in this project looked fine in the UI: a mind can be wedged, deadlocked, or
// out of API credit while its body stands in the town looking perfectly well.
//
// The bridge already reads every trajectory step, so it knows when a run starts
// (shellm-run), finishes (final) and dies (error). It reports that here, and the
// frontend subscribes like it does to everything else.
import { v } from 'convex/values';
import { mutation, query } from './_generated/server';

export const report = mutation({
  args: {
    worldId: v.id('worlds'),
    name: v.string(),
    playerId: v.optional(v.string()),
    running: v.boolean(),
    lastWakeAt: v.optional(v.number()),
    lastFinalAt: v.optional(v.number()),
    lastError: v.optional(v.string()),
    lastErrorAt: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query('mindStatus')
      .withIndex('worldName', (q) => q.eq('worldId', args.worldId).eq('name', args.name))
      .unique();
    const doc = { ...args, updatedAt: Date.now() };
    if (existing) {
      await ctx.db.patch(existing._id, doc);
    } else {
      await ctx.db.insert('mindStatus', doc);
    }
  },
});

// Budget is per API key, not per mind, so it is reported once for the world.
// It is the number this project has most often wished were on screen: we have
// twice woken up to a town that stopped overnight because the key ran dry.
export const reportBudget = mutation({
  args: {
    worldId: v.id('worlds'),
    spent: v.number(),
    limit: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query('budgetStatus')
      .withIndex('worldId', (q) => q.eq('worldId', args.worldId))
      .unique();
    const doc = { ...args, updatedAt: Date.now() };
    if (existing) {
      await ctx.db.patch(existing._id, doc);
    } else {
      await ctx.db.insert('budgetStatus', doc);
    }
  },
});

export const forWorld = query({
  args: { worldId: v.id('worlds') },
  handler: async (ctx, args) => {
    const minds = await ctx.db
      .query('mindStatus')
      .withIndex('worldName', (q) => q.eq('worldId', args.worldId))
      .collect();
    const budget = await ctx.db
      .query('budgetStatus')
      .withIndex('worldId', (q) => q.eq('worldId', args.worldId))
      .unique();
    return { minds, budget };
  },
});
