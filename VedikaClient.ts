/**
 * VedikaClient.ts
 * ================
 * Drop-in TypeScript client for connecting the Vyomantha Next.js LMS
 * to the Vedika desktop mascot companion running locally on port 7000/7001.
 *
 * Usage:
 *   import { VedikaClient } from '@/lib/vedika/VedikaClient';
 *   const vedika = new VedikaClient();
 *   await vedika.sendActivity('submit_quiz', '/ai-tutor', { quizTopic: 'Recursion', quizScore: 87 });
 */

// ─── Types ──────────────────────────────────────────────────────────────────

export type VedikaAction =
  | 'navigate'
  | 'submit_quiz'
  | 'compile_code'
  | 'chat_message'
  | 'idle_start';

export type MascotState =
  | 'idle'
  | 'thinking'
  | 'dance'
  | 'sad'
  | 'sleep'
  | 'wake';

/** contextData fields for each action */
export interface NavigateContext {
  moduleId:    string;
  lessonId:    string;
  lessonTitle: string;
}

export interface QuizContext {
  quizTopic:  string;
  quizScore:  number; // 0–100
}

export interface CompileContext {
  errorMessage?: string;
  language?:     string;
  codeSnippet?:  string;
}

export interface ChatContext {
  chatMessageText: string;
}

export type VedikaContextData =
  | NavigateContext
  | QuizContext
  | CompileContext
  | ChatContext
  | Record<string, unknown>;

/** Payload sent to /api/activity or /api/chat */
export interface VedikaRequest {
  action:        VedikaAction;
  userId?:       string;
  currentRoute?: string;
  timestamp?:    number;
  contextData?:  VedikaContextData;
}

/** Mascot message returned in every AgentDecision response */
export interface MascotMessage {
  text: string;
  tone: string;
}

/** Action the LMS should execute (e.g. navigate to a page) */
export interface ClientAction {
  type:    string;
  params?: Record<string, unknown>;
}

/** Mascot display info */
export interface MascotInfo {
  state:            MascotState;
  bubbleText:       string;
  customAnimation?: string;
}

/** Response from /api/activity */
export interface ActivityResponse {
  ok:      boolean;
  state:   MascotState;
  speech:  string;
  message: MascotMessage;
  actions: ClientAction[];
  mascot:  MascotInfo;
}

/** Response from /api/chat */
export interface ChatResponse {
  response: string; // legacy key
  message:  MascotMessage;
  actions:  ClientAction[];
  mascot:   MascotInfo;
}

/** WebSocket event pushed by Vedika */
export interface VedikaWSEvent {
  event:         string;
  state?:        MascotState;
  text?:         string;
  userId?:       string;
  userMessage?:  string;
  reply?:        string;
  activityType?: string;
  speech?:       string;
  tab?:          string; // Added for openAITutor events
}

// ─── Client ─────────────────────────────────────────────────────────────────

export class VedikaClient {
  private readonly baseUrl: string;
  private readonly wsUrl:   string;
  private userId:           string | null = null;
  private ws:               WebSocket | null = null;
  private reconnectTimer:   ReturnType<typeof setTimeout> | null = null;

  constructor(options: { baseUrl?: string; wsUrl?: string } = {}) {
    this.baseUrl = options.baseUrl ?? 'http://localhost:7000';
    this.wsUrl   = options.wsUrl   ?? 'ws://localhost:7001';
  }

  // ── Identity ──────────────────────────────────────────────────

  /** Set the current user. Call once after login. */
  setUser(email: string): this {
    this.userId = email;
    return this;
  }

  // ── Availability ──────────────────────────────────────────────

  /** Returns true if the Vedika desktop app is running. */
  async isRunning(): Promise<boolean> {
    try {
      const res = await fetch(`${this.baseUrl}/api/status`, {
        signal: AbortSignal.timeout(1500),
      });
      return res.ok;
    } catch {
      return false;
    }
  }

  // ── HTTP API ──────────────────────────────────────────────────

  /**
   * Report a student activity to Vedika.
   * @param action  — one of the VedikaAction values
   * @param route   — current page route, e.g. '/ai-tutor'
   * @param context — action-specific data
   */
  async sendActivity(
    action: VedikaAction,
    route: string,
    context: VedikaContextData = {},
  ): Promise<ActivityResponse | null> {
    const payload: VedikaRequest = {
      action,
      userId:       this.userId ?? undefined,
      currentRoute: route,
      timestamp:    Date.now() / 1000,
      contextData:  context,
    };
    return this._post<ActivityResponse>('/api/activity', payload);
  }

  /**
   * Send a chat message to Vedika and get her AI reply.
   * @param message — the user's message text
   * @param route   — current page route
   */
  async sendChat(message: string, route = '/'): Promise<ChatResponse | null> {
    const payload: VedikaRequest = {
      action:       'chat_message',
      userId:       this.userId ?? undefined,
      currentRoute: route,
      timestamp:    Date.now() / 1000,
      contextData:  { chatMessageText: message },
    };
    return this._post<ChatResponse>('/api/chat', payload);
  }

  /**
   * Register or update the student's profile.
   * Call this once after login / onboarding.
   */
  async onboard(name: string, age: number): Promise<{ ok: boolean } | null> {
    return this._post<{ ok: boolean }>('/api/onboard', {
      userId: this.userId ?? undefined,
      name,
      age,
    });
  }

  /**
   * Convenience: report navigation to a new lesson.
   */
  async reportNavigation(
    route: string,
    moduleId: string,
    lessonId: string,
    lessonTitle: string,
  ): Promise<ActivityResponse | null> {
    return this.sendActivity('navigate', route, { moduleId, lessonId, lessonTitle });
  }

  /**
   * Convenience: report a quiz result.
   */
  async reportQuiz(
    route: string,
    topic: string,
    score: number,
  ): Promise<ActivityResponse | null> {
    return this.sendActivity('submit_quiz', route, { quizTopic: topic, quizScore: score });
  }

  /**
   * Convenience: report a code compile (with optional error).
   */
  async reportCompile(
    route: string,
    errorMessage?: string,
    language = 'python',
  ): Promise<ActivityResponse | null> {
    return this.sendActivity('compile_code', route, {
      errorMessage,
      language,
    });
  }

  // ── WebSocket ─────────────────────────────────────────────────

  /**
   * Connect to Vedika's WebSocket and receive real-time mascot events.
   * Auto-reconnects on disconnect.
   *
   * @param onEvent   — callback fired for each event
   * @param onConnect — optional callback when connected
   */
  connectWebSocket(
    onEvent:   (event: VedikaWSEvent) => void,
    onConnect?: () => void,
  ): void {
    this._openWS(onEvent, onConnect);
  }

  /** Disconnect the WebSocket. */
  disconnectWebSocket(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.onclose = null; // prevent auto-reconnect
      this.ws.close();
      this.ws = null;
    }
  }

  private _openWS(
    onEvent:   (event: VedikaWSEvent) => void,
    onConnect?: () => void,
  ): void {
    try {
      this.ws = new WebSocket(this.wsUrl);

      this.ws.onopen = () => {
        console.log('[Vedika WS] Connected');
        onConnect?.();
      };

      this.ws.onmessage = (msg: MessageEvent<string>) => {
        try {
          const data = JSON.parse(msg.data) as VedikaWSEvent;
          onEvent(data);
        } catch {
          // ignore malformed frames
        }
      };

      this.ws.onerror = () => {
        // Silently ignore — will reconnect on close
      };

      this.ws.onclose = () => {
        console.log('[Vedika WS] Disconnected — retrying in 5s');
        this.reconnectTimer = setTimeout(() => {
          this._openWS(onEvent, onConnect);
        }, 5000);
      };
    } catch {
      // WebSocket not available (SSR context)
    }
  }

  // ── Internal ──────────────────────────────────────────────────

  private async _post<T>(path: string, body: unknown): Promise<T | null> {
    try {
      const res = await fetch(`${this.baseUrl}${path}`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(body),
        signal:  AbortSignal.timeout(8000),
      });
      if (!res.ok) return null;
      return res.json() as Promise<T>;
    } catch {
      // Vedika not running — fail silently
      return null;
    }
  }
}

// ─── Singleton helper ────────────────────────────────────────────────────────

/**
 * Pre-built singleton instance.
 * Import this instead of creating a new VedikaClient() in every component.
 *
 * Usage:
 *   import { vedika } from '@/lib/vedika/VedikaClient';
 *   vedika.setUser(session.user.email);
 */
export const vedika = new VedikaClient();
