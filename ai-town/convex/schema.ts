import { defineSchema, defineTable } from 'convex/server';
import { v } from 'convex/values';
import { agentTables } from './agent/schema';
import { aiTownTables } from './aiTown/schema';
import { conversationId, playerId } from './aiTown/ids';
import { engineTables } from './engine/schema';

export default defineSchema({
  music: defineTable({
    storageId: v.string(),
    type: v.union(v.literal('background'), v.literal('player')),
  }),

  messages: defineTable({
    conversationId,
    messageUuid: v.string(),
    author: playerId,
    text: v.string(),
    worldId: v.optional(v.id('worlds')),
  })
    .index('conversationId', ['worldId', 'conversationId'])
    .index('messageUuid', ['conversationId', 'messageUuid']),

  // Health of the Headlong identities driving the bodies. Written by the
  // bridge, read by the top bar. See convex/mindStatus.ts.
  mindStatus: defineTable({
    worldId: v.id('worlds'),
    name: v.string(),
    playerId: v.optional(v.string()),
    running: v.boolean(),
    lastWakeAt: v.optional(v.number()),
    lastFinalAt: v.optional(v.number()),
    lastError: v.optional(v.string()),
    lastErrorAt: v.optional(v.number()),
    updatedAt: v.number(),
  }).index('worldName', ['worldId', 'name']),

  budgetStatus: defineTable({
    worldId: v.id('worlds'),
    spent: v.number(),
    limit: v.optional(v.number()),
    updatedAt: v.number(),
  }).index('worldId', ['worldId']),

  ...agentTables,
  ...aiTownTables,
  ...engineTables,
});
