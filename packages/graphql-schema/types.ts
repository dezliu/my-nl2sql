type AskStreamEvent = {
  eventType: string;
  data: Record<string, unknown>;
};

type Datasource = {
  id: number;
  name: string;
  connectionUrl: string;
  isActive: boolean;
};

type SystemPrompt = {
  id: number;
  role: string;
  version: number;
  content: string;
  isActive: boolean;
};

type CacheStats = {
  totalHits: number;
  exactHits: number;
  semanticHits: number;
  totalTokensSaved: number;
};

type CacheHitLog = {
  id: number;
  sessionId: string | null;
  hitType: string;
  savedTokens: number;
  similarity: number | null;
  latencyMs: number;
};

type RagAlert = {
  id: number;
  chunkId: number;
  question: string;
  score: number;
  isResolved: boolean;
};

export type { AskStreamEvent, Datasource, SystemPrompt, CacheStats, CacheHitLog, RagAlert };
