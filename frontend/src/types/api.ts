export type JsonRecord = Record<string, unknown>;

export interface DashboardData {
  summary: {
    totalTargetAmount?: number;
    totalIncomeAmount?: number;
    completionRate?: number;
    yoyRate?: number;
    riskProjectCount?: number;
  };
  charts: {
    productLineMix?: Array<{ name: string; value: number; yoyRate?: number }>;
    industryTop?: Array<{ name: string; value: number; yoyRate?: number }>;
    unitRank?: Array<{ name: string; value: number; rate?: number }>;
  };
}

export interface QueryInterface {
  interfaceCode: string;
  interfaceName: string;
  groupName: string;
  method: string;
  path: string;
  ownerDept: string;
  paramCount: number;
  fields: string;
  status: "启用" | "停用";
  approvalPolicy: "none" | "manual";
  executable: boolean;
  description: string;
}

export interface AgentSkill {
  id: number;
  skillCode: string;
  skillName: string;
  description: string;
  triggerKeywords: string[];
  stepCount: number;
  status: "启用" | "停用";
  updatedAt: string;
  steps?: Array<{
    stepId?: string;
    action?: "interface" | "derive" | "transform";
    interfaceCode?: string | null;
    params: JsonRecord;
    paramSources?: JsonRecord;
    transform?: JsonRecord;
    dependsOn?: string[];
    purpose?: string;
  }>;
  derivedMetrics?: string[];
  answerSections?: string[];
}

export interface AuditRecord {
  id: number;
  requestId: string;
  sessionId?: number;
  interfaceCode: string;
  requestParams: string | JsonRecord;
  responseRowCount: number;
  durationMs: number;
  status: string;
  errorMessage?: string;
  createdAt: string;
}

export interface FeedbackRecord {
  id: number;
  sessionId?: number;
  question: string;
  answerSnippet: string;
  reason: string;
  status: string;
  handlerName?: string;
  handlerRemark?: string;
  createdAt: string;
}

export interface Session {
  id: number;
  title: string;
  messageCount: number;
  pinned: boolean;
  updatedAt: string;
}

export interface TableColumn {
  field: string;
  label: string;
  type?: string;
  unit?: string;
}

export interface ChartPayload {
  mode?: "single" | "combined" | "split";
  chartType?: string;
  title?: string;
  unit?: string;
  data?: Array<{ label: string; value: number }>;
  series?: Array<{ name: string; chartType: string; unit?: string; axisIndex?: number; data: Array<{ label: string; value: number }> }>;
  charts?: ChartPayload[];
}

export interface AnswerPayload {
  type: "structuredAnswer" | "directAnswer";
  dataFindings?: string[];
  table?: { columns: TableColumn[]; rows: JsonRecord[]; totalRows: number };
  resultSets?: Array<{ stepId?: string; interfaceCode?: string; purpose?: string; columns: TableColumn[]; rows: JsonRecord[]; totalRows: number; summary?: JsonRecord }>;
  stats?: { rowCount: number; numeric?: Array<JsonRecord>; derived?: Array<JsonRecord> };
  visualization?: ChartPayload;
  nextSuggestions?: string[];
  source?: JsonRecord;
  derivedMetrics?: { items?: Array<JsonRecord>; tables?: Array<JsonRecord> };
  process?: Array<JsonRecord>;
}

export interface ChatMessage {
  id?: number;
  role: "user" | "assistant";
  content: string;
  answerPayload?: AnswerPayload;
  chart?: AnswerPayload;
  createdAt?: string;
}

export interface AppConfig {
  greetingEnabled: boolean;
  openingGreeting: string;
  openingQuestions: string[];
  nextSuggestionsEnabled: boolean;
  nextSuggestionsCount: number;
  frequentEnabled: boolean;
  frequentThreshold: number;
  frequentQuestions: Array<{ id: number; question: string; hitCount: number }>;
}

export interface LlmConfig {
  provider: "openai" | "deepseek";
  baseUrl: string;
  modelName: string;
  apiKey: string;
  hasApiKey: boolean;
  streamEnabled: boolean;
  temperature: number;
  maxOutputTokens: number;
  providerOptions: Record<string, { label: string; baseUrl: string; models: string[] }>;
}
