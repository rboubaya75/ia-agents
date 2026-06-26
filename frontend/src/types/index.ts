// User types
export interface User {
  id: string;
  email?: string;
  username?: string;
}

// Message types
export interface Message {
  id: string;
  content: string;
  sender: 'user' | 'system';
  timestamp: Date;
}

// Chat state types
export interface ChatState {
  messages: Message[];
  sessionId: string;
  isLoading: boolean;
  error: string | null;
}

// Auth state types
export interface AuthState {
  isAuthenticated: boolean;
  user: User | null;
  userId: string | null;
  jwtToken: string | null;
}

// Auth service types
export interface AuthResult {
  user: User;
  userId: string;
  jwtToken: string;
}

export interface AuthService {
  login(username: string, password: string): Promise<AuthResult>;
  logout(): Promise<void>;
  getCurrentUser(): Promise<User>;
  getJwtToken(): Promise<string>;
  extractUserId(token: string): string;
}

// Chat service types
export interface AgentCoreRequest {
  input: {
    prompt: string;
  };
}

export interface AgentCoreResponse {
  output: {
    message: string;
    timestamp?: string;
    model?: string;
  };
}

export interface ChatResponse {
  message: string;
  timestamp?: string;
}

export interface ChatService {
  sendMessage(
    message: string,
    sessionId: string,
    actorId: string,
    jwtToken: string
  ): Promise<ChatResponse>;
}

// Session service types
export interface SessionService {
  generateSessionId(): string;
  getCurrentSessionId(): string | null;
  createNewSession(): string;
}
