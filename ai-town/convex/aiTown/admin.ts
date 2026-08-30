import { v } from 'convex/values';
import { mutation } from '../_generated/server';
import { Id } from '../_generated/dataModel';

/**
 * Delete a world and everything hanging off it.
 *
 * Experiments accumulate worlds (PLAN.md §7), and there is no upstream way to
 * remove one -- `testing:wipeAllTables` is all-or-nothing, which would take the
 * experiment you are actually running with it. This removes exactly one world:
 * its engine, map, descriptions, archives, messages and queued inputs.
 *
 * Refuses the default world unless `force`, since deleting it leaves the
 * frontend with nothing to show when no `?experiment=` is given.
 */
export const deleteWorld = mutation({
  args: {
    worldId: v.id('worlds'),
    force: v.optional(v.boolean()),
  },
  handler: async (ctx, args) => {
    const status = await ctx.db
      .query('worldStatus')
      .withIndex('worldId', (q) => q.eq('worldId', args.worldId))
      .unique();
    if (!status) {
      throw new Error(`No worldStatus for ${args.worldId}`);
    }
    if (status.isDefault && !args.force) {
      throw new Error(`Refusing to delete the default world without force:true`);
    }

    const deleted: Record<string, number> = {};
    const drop = async (label: string, ids: Id<any>[]) => {
      for (const id of ids) await ctx.db.delete(id);
      deleted[label] = ids.length;
    };

    // Queued inputs belong to the engine, everything else to the world.
    const inputs = await ctx.db
      .query('inputs')
      .withIndex('byInputNumber', (q) => q.eq('engineId', status.engineId))
      .collect();
    await drop('inputs', inputs.map((d) => d._id));

    for (const table of [
      'maps',
      'playerDescriptions',
      'agentDescriptions',
      'archivedPlayers',
      'archivedConversations',
      'archivedAgents',
      'participatedTogether',
      'messages',
    ] as const) {
      const rows = await ctx.db
        .query(table)
        .filter((q) => q.eq(q.field('worldId'), args.worldId))
        .collect();
      await drop(table, rows.map((d) => d._id));
    }

    await ctx.db.delete(status._id);
    await ctx.db.delete(status.engineId);
    await ctx.db.delete(args.worldId);
    deleted.world = 1;
    return deleted;
  },
});

/**
 * Point the default world at an experiment.
 *
 * Only the unnamed world is normally `isDefault` (see init.ts), so once the
 * unnamed world is deleted a bare URL with no `?experiment=` resolves to
 * nothing. This lets the experiment you are actually running answer there.
 */
export const setDefaultWorld = mutation({
  args: {
    worldId: v.id('worlds'),
  },
  handler: async (ctx, args) => {
    const all = await ctx.db.query('worldStatus').collect();
    for (const status of all) {
      const shouldBeDefault = status.worldId === args.worldId;
      if (status.isDefault !== shouldBeDefault) {
        await ctx.db.patch(status._id, { isDefault: shouldBeDefault });
      }
    }
    return { default: args.worldId };
  },
});
