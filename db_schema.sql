-- 经管之星数据库表结构草案
-- SQLite single database

PRAGMA foreign_keys = ON;

CREATE TABLE dim_org_unit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  unit_code TEXT NOT NULL UNIQUE,
  unit_name TEXT NOT NULL,
  unit_type TEXT,
  parent_code TEXT,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_org_unit_name ON dim_org_unit (unit_name);

CREATE TABLE dim_industry (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  industry_code TEXT NOT NULL UNIQUE,
  industry_name TEXT NOT NULL,
  industry_category TEXT,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_industry_name ON dim_industry (industry_name);
CREATE INDEX idx_industry_category ON dim_industry (industry_category);

CREATE TABLE dim_product_line (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  line_code TEXT NOT NULL UNIQUE,
  line_name TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE dim_product_model (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  model_code TEXT NOT NULL UNIQUE,
  model_name TEXT NOT NULL,
  line_code TEXT,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_product_model_name ON dim_product_model (model_name);
CREATE INDEX idx_product_model_line ON dim_product_model (line_code);

CREATE TABLE dim_customer (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_name TEXT NOT NULL UNIQUE,
  customer_level TEXT,
  customer_category TEXT,
  sensitive_level TEXT NOT NULL DEFAULT 'internal',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE ledger_commercial_contract (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_pk TEXT,
  year INTEGER NOT NULL,
  seller_name TEXT,
  dept_level1 TEXT,
  dept_level2 TEXT,
  province TEXT,
  industry_category TEXT,
  industry_name TEXT,
  product_line_code TEXT,
  product_model_name TEXT,
  sales_name TEXT,
  marketing_name TEXT,
  org_unit_name TEXT,
  sales_admin_contact TEXT,
  sign_date TEXT,
  contract_no TEXT,
  pre_sales_no TEXT,
  opportunity_name TEXT,
  opportunity_no TEXT,
  contract_name TEXT,
  buyer_name TEXT,
  final_customer_name TEXT,
  customer_level TEXT,
  special_project TEXT,
  quantity INTEGER,
  redundant_quantity INTEGER,
  tax_rate NUMERIC,
  contract_total_amount NUMERIC,
  legacy_recognition_amount NUMERIC,
  legacy_collection_amount NUMERIC,
  recognized_amount NUMERIC,
  unrecognized_amount NUMERIC,
  collected_amount NUMERIC,
  uncollected_amount NUMERIC,
  receivable_amount NUMERIC,
  pod_income_ytd NUMERIC,
  delivery_income_ytd NUMERIC,
  income_diff_amount NUMERIC,
  income_diff_desc TEXT,
  diff_category TEXT,
  legacy_delivery_confirm_amount NUMERIC,
  is_stat INTEGER NOT NULL DEFAULT 1,
  product_model_name_1 TEXT,
  product_model_name_2 TEXT,
  sub_industry_name TEXT,
  is_new_product INTEGER,
  order_amount NUMERIC,
  is_order_stat INTEGER NOT NULL DEFAULT 1,
  internet_special TEXT,
  extra_json TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_commercial_year_unit ON ledger_commercial_contract (year, org_unit_name);
CREATE INDEX idx_commercial_year_industry ON ledger_commercial_contract (year, industry_name);
CREATE INDEX idx_commercial_product_line ON ledger_commercial_contract (year, product_line_code);
CREATE INDEX idx_commercial_contract_no ON ledger_commercial_contract (contract_no);
CREATE INDEX idx_commercial_sign_date ON ledger_commercial_contract (sign_date);

CREATE TABLE ledger_commercial_monthly_metric (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  contract_id INTEGER NOT NULL,
  year INTEGER NOT NULL,
  metric_type TEXT NOT NULL,
  metric_month INTEGER NOT NULL,
  amount NUMERIC NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (contract_id, metric_type, metric_month),
  FOREIGN KEY (contract_id) REFERENCES ledger_commercial_contract(id) ON DELETE CASCADE
);
CREATE INDEX idx_monthly_metric_query ON ledger_commercial_monthly_metric (year, metric_type, metric_month);

CREATE TABLE ledger_ppl_pipeline (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  row_no INTEGER,
  contract_no TEXT,
  pre_sales_or_opp_no TEXT,
  industry_category TEXT,
  industry_name TEXT,
  org_unit_name TEXT,
  sales_name TEXT,
  project_name TEXT,
  final_customer_name TEXT,
  product_type TEXT,
  product_model_name TEXT,
  new_product_model_name TEXT,
  quantity INTEGER,
  amount NUMERIC,
  amount_without_tax NUMERIC,
  landing_month TEXT,
  project_competition_risk TEXT,
  contract_signing_risk TEXT,
  supply_delivery_risk TEXT,
  risk_level TEXT,
  project_stage TEXT,
  special_action TEXT,
  approval_level TEXT,
  listing_date TEXT,
  bidding_date TEXT,
  contract_signing_date TEXT,
  customer_delivery_date TEXT,
  payment_date TEXT,
  is_scheduled INTEGER,
  signing_entity TEXT,
  progress_risk_desc TEXT,
  customer_category TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_ppl_unit_risk ON ledger_ppl_pipeline (org_unit_name, risk_level);
CREATE INDEX idx_ppl_stage ON ledger_ppl_pipeline (project_stage);
CREATE INDEX idx_ppl_contract_no ON ledger_ppl_pipeline (contract_no);
CREATE INDEX idx_ppl_landing_month ON ledger_ppl_pipeline (landing_month);

CREATE TABLE ledger_goal_target (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  org_unit_name TEXT NOT NULL,
  year INTEGER NOT NULL,
  commercial_target_amount NUMERIC NOT NULL DEFAULT 0,
  solution_target_amount NUMERIC NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (org_unit_name, year)
);

CREATE TABLE rpt_unit_achievement (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  stat_date TEXT NOT NULL,
  year INTEGER NOT NULL,
  org_unit_name TEXT NOT NULL,
  target_amount NUMERIC NOT NULL DEFAULT 0,
  income_amount NUMERIC NOT NULL DEFAULT 0,
  old_income_amount NUMERIC NOT NULL DEFAULT 0,
  yoy_rate NUMERIC,
  completion_rate NUMERIC,
  guaranteed_amount NUMERIC,
  q2_forecast_amount NUMERIC,
  forecast_completion_rate NUMERIC,
  product_line_mix TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (stat_date, year, org_unit_name)
);
CREATE INDEX idx_rpt_unit_year_income ON rpt_unit_achievement (year, income_amount);

CREATE TABLE rpt_product_line_summary (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  stat_date TEXT NOT NULL,
  year INTEGER NOT NULL,
  compare_year INTEGER,
  product_line_name TEXT NOT NULL,
  amount NUMERIC NOT NULL DEFAULT 0,
  compare_amount NUMERIC NOT NULL DEFAULT 0,
  yoy_rate NUMERIC,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (stat_date, year, product_line_name)
);

CREATE TABLE rpt_product_model_breakdown (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  stat_date TEXT NOT NULL,
  year INTEGER NOT NULL,
  compare_year INTEGER,
  product_line_name TEXT NOT NULL,
  product_model_name TEXT NOT NULL,
  amount NUMERIC NOT NULL DEFAULT 0,
  compare_amount NUMERIC NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (stat_date, year, product_line_name, product_model_name)
);

CREATE TABLE rpt_industry_achievement (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  stat_date TEXT NOT NULL,
  year INTEGER NOT NULL,
  industry_name TEXT NOT NULL,
  income_amount NUMERIC NOT NULL DEFAULT 0,
  yoy_rate NUMERIC,
  guaranteed_amount NUMERIC,
  q2_forecast_amount NUMERIC,
  q2_yoy_rate NUMERIC,
  general_compute_amount NUMERIC NOT NULL DEFAULT 0,
  general_compute_yoy_rate NUMERIC,
  intelligent_compute_amount NUMERIC NOT NULL DEFAULT 0,
  intelligent_compute_yoy_rate NUMERIC,
  business_solution_amount NUMERIC NOT NULL DEFAULT 0,
  business_solution_yoy_rate NUMERIC,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (stat_date, year, industry_name)
);
CREATE INDEX idx_rpt_industry_income ON rpt_industry_achievement (year, income_amount);

CREATE TABLE rpt_key_unit_product_analysis (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  stat_date TEXT NOT NULL,
  year INTEGER NOT NULL,
  org_unit_name TEXT NOT NULL,
  product_line_name TEXT NOT NULL,
  amount NUMERIC NOT NULL DEFAULT 0,
  compare_amount NUMERIC NOT NULL DEFAULT 0,
  yoy_rate NUMERIC,
  model_breakdown TEXT,
  industry_breakdown TEXT,
  analysis_text TEXT,
  updated_by INTEGER,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (stat_date, year, org_unit_name, product_line_name)
);

CREATE TABLE ai_query_interface (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  interface_code TEXT NOT NULL UNIQUE,
  interface_name TEXT NOT NULL,
  group_name TEXT NOT NULL,
  method TEXT NOT NULL DEFAULT 'POST',
  path TEXT NOT NULL,
  owner_dept TEXT,
  description TEXT,
  security_policy TEXT,
  approval_policy TEXT NOT NULL DEFAULT 'none',
  cache_policy TEXT,
  rate_limit_policy TEXT,
  status TEXT NOT NULL DEFAULT '启用',
  created_by INTEGER,
  updated_by INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_ai_interface_status ON ai_query_interface (status);
CREATE INDEX idx_ai_interface_group ON ai_query_interface (group_name);

CREATE TABLE ai_query_interface_param (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  interface_code TEXT NOT NULL,
  param_name TEXT NOT NULL,
  param_type TEXT NOT NULL,
  required INTEGER NOT NULL DEFAULT 0,
  enum_json TEXT,
  default_value TEXT,
  description TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  UNIQUE (interface_code, param_name),
  FOREIGN KEY (interface_code) REFERENCES ai_query_interface(interface_code) ON DELETE CASCADE
);
CREATE INDEX idx_ai_param_interface ON ai_query_interface_param (interface_code);

CREATE TABLE ai_query_interface_field (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  interface_code TEXT NOT NULL,
  field_name TEXT NOT NULL,
  field_label TEXT NOT NULL,
  field_type TEXT NOT NULL,
  unit TEXT,
  sensitive_level TEXT NOT NULL DEFAULT 'internal',
  description TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  UNIQUE (interface_code, field_name),
  FOREIGN KEY (interface_code) REFERENCES ai_query_interface(interface_code) ON DELETE CASCADE
);
CREATE INDEX idx_ai_field_interface ON ai_query_interface_field (interface_code);

CREATE TABLE ai_query_call_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id TEXT NOT NULL UNIQUE,
  session_id INTEGER,
  client_name TEXT,
  interface_code TEXT NOT NULL,
  request_params TEXT,
  response_row_count INTEGER,
  duration_ms INTEGER,
  status TEXT NOT NULL,
  error_message TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_ai_audit_session ON ai_query_call_audit (session_id);
CREATE INDEX idx_ai_audit_interface_time ON ai_query_call_audit (interface_code, created_at);
CREATE INDEX idx_ai_audit_client_time ON ai_query_call_audit (client_name, created_at);

CREATE TABLE agent_skill (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  skill_code TEXT NOT NULL UNIQUE,
  skill_name TEXT NOT NULL,
  description TEXT,
  instructions TEXT,
  trigger_keywords TEXT,
  steps_json TEXT NOT NULL,
  derived_metrics_json TEXT,
  answer_sections_json TEXT,
  status TEXT NOT NULL DEFAULT '启用',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_agent_skill_status ON agent_skill (status);

CREATE TABLE qa_session (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  client_name TEXT,
  pinned INTEGER NOT NULL DEFAULT 0,
  user_feedback TEXT,
  admin_feedback TEXT,
  message_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_qa_session_client_time ON qa_session (client_name, updated_at);
CREATE INDEX idx_qa_session_pinned ON qa_session (pinned);

CREATE TABLE qa_message (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  interface_calls TEXT,
  chart_config TEXT,
  token_count INTEGER,
  latency_ms INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (session_id) REFERENCES qa_session(id) ON DELETE CASCADE
);
CREATE INDEX idx_qa_message_session ON qa_message (session_id, created_at);

CREATE TABLE qa_feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER,
  message_id INTEGER,
  question TEXT,
  answer_snippet TEXT,
  reason TEXT,
  submitter_id INTEGER,
  submitter_name TEXT,
  status TEXT NOT NULL DEFAULT '待处理',
  handler_id INTEGER,
  handler_name TEXT,
  handler_remark TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  handled_at TEXT
);
CREATE INDEX idx_qa_feedback_status_time ON qa_feedback (status, created_at);
CREATE INDEX idx_qa_feedback_session ON qa_feedback (session_id);

CREATE TABLE llm_config (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  provider TEXT NOT NULL DEFAULT 'openai',
  base_url TEXT NOT NULL DEFAULT 'https://api.openai.com/v1',
  model_name TEXT NOT NULL,
  api_key TEXT,
  stream_enabled INTEGER NOT NULL DEFAULT 1,
  temperature NUMERIC NOT NULL DEFAULT 0.2,
  max_output_tokens INTEGER NOT NULL DEFAULT 2048,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE app_config (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  greeting_enabled INTEGER NOT NULL DEFAULT 1,
  opening_greeting TEXT,
  opening_questions TEXT,
  next_suggestions TEXT,
  next_suggestions_enabled INTEGER NOT NULL DEFAULT 1,
  next_suggestions_count INTEGER NOT NULL DEFAULT 3,
  frequent_enabled INTEGER NOT NULL DEFAULT 1,
  frequent_threshold INTEGER NOT NULL DEFAULT 3,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE qa_frequent_question (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  question TEXT NOT NULL,
  normalized_question TEXT NOT NULL UNIQUE,
  hit_count INTEGER NOT NULL DEFAULT 3,
  last_asked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_qa_frequent_last ON qa_frequent_question (last_asked_at);
