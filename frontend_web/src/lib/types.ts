export type ApiEnvelope<T> = {
  code: number;
  message: string;
  data: T;
  request_id: string;
};

export type Conversation = {
  id: string;
  title: string;
  created_at: string;
  message_count?: number;
};

export type DocItem = {
  id: string;
  file_name: string;
  file_type: string;
  parse_status: string;
  chunk_count: number;
  tags?: string[];
  project_id?: string;
  created_at: string;
};

export type DocDetail = {
  id: string;
  file_name: string;
  file_type: string;
  parse_status: string;
  chunk_count: number;
  tags?: string[];
  summary?: string;
  project_id?: string;
  preview?: string;
  created_at: string;
};

export type RagReference = {
  document_id?: string;
  chunk_id?: string;
  source_file?: string;
  page_no?: number;
  section?: string;
  score?: number;
  preview?: string;
  content?: string;
};

export type RagQueryResponse = {
  answer: string;
  references: RagReference[];
  embedding_mode?: string;
};

export type TaskItem = {
  id: number;
  conversation_id?: string;
  title: string;
  description: string;
  task_type: string;
  priority: string;
  difficulty: string;
  estimated_hours: number;
  dependency?: string;
  deliverable?: string;
  status: string;
  assignee?: string;
  deadline?: string;
  created_at: string;
  updated_at?: string;
  source_count?: number;
};

export type TaskSource = {
  id: number;
  task_id: number;
  document_id?: string;
  chunk_id?: string;
  source_file?: string;
  page_no?: number;
  section?: string;
  score?: number;
  created_at: string;
};

export type TaskDetail = {
  task: TaskItem;
  sources: TaskSource[];
};

