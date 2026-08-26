export interface SchoolClass {
  id: string;
  name: string;
}

export interface Subject {
  id: string;
  name: string;
}

export type ChatRole = "user" | "tutor";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  text: string;
}

export interface AskTutorRequest {
  classId: string;
  subjectId: string;
  question: string;
}

export interface AskTutorResponse {
  answer: string;
}
