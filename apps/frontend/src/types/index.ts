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

export type TeachingStyle = "socratic" | "direct" | "exam_prep";

export interface TutorProfile {
  subject?: string;
  level?: string;
  style?: TeachingStyle;
  language?: string;
  studentName?: string;
}

export interface AskTutorRequest {
  message: string;
  sessionId?: string;
  profile?: TutorProfile;
}

export interface AskTutorResponse {
  sessionId: string;
  answer: string;
}
