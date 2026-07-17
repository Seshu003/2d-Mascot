# Vedika ↔ Vyomantha LMS Integration Guide

This document explains how to wire the **Vyomantha Next.js LMS** to the **Vedika desktop mascot** running locally on the student's machine.

## Architecture Overview

```
Vyomantha Next.js LMS
        │
        ├─ POST localhost:7000/api/activity  ← LMS events (quiz, navigate, error…)
        ├─ POST localhost:7000/api/chat      ← Chat messages to Vedika
        ├─ GET  localhost:7000/api/status    ← Fetch current user memory
        │
        └─ WebSocket ws://localhost:7001     ← REAL-TIME push from Vedika → LMS
                    │
                    ├─ { event: "stateChange", state: "thinking" }
                    ├─ { event: "speech", text: "..." }
                    ├─ { event: "chat", userId, state, userMessage, reply }
                    ├─ { event: "activity", activityType, state, speech, userId }
                    └─ { event: "sleeping" }
```

---

## Quick Start

### 1. Install `VedikaClient.ts`

Copy `VedikaClient.ts` into your Next.js project:

```bash
cp VedikaClient.ts src/lib/vedika/VedikaClient.ts
```

### 2. Use in a component

```tsx
import { VedikaClient } from '@/lib/vedika/VedikaClient';

const vedika = new VedikaClient();

// Send a quiz result
await vedika.sendActivity('submit_quiz', '/ai-tutor', {
  quizTopic: 'Recursion',
  quizScore: 87,
});

// Send a chat message and get the reply
const reply = await vedika.sendChat('Can you explain pointers?');
console.log(reply.message.text);

// Listen for real-time mascot events
vedika.connectWebSocket((event) => {
  if (event.event === 'speech') {
    console.log('Vedika says:', event.text);
  }
});
```

---

## HTTP API Reference

### Base URL
```
http://localhost:7000
```

---

### `POST /api/activity`

Report a student activity. Vedika will react with the appropriate animation and speech.

**Request body:**

```json
{
  "action":       "submit_quiz",
  "userId":       "student@example.com",
  "currentRoute": "/ai-tutor",
  "timestamp":    1700000000,
  "contextData": {
    "quizTopic": "Recursion",
    "quizScore": 87
  }
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `action` | string | ✅ | One of `navigate`, `submit_quiz`, `compile_code`, `chat_message`, `idle_start` |
| `userId` | string | ✅ recommended | Student email — enables multi-user memory |
| `currentRoute` | string | | Current page path, e.g. `/dashboard` |
| `timestamp` | number | | Unix timestamp (ms) |
| `contextData` | object | | Action-specific data (see below) |

**`contextData` per action:**

| `action` | contextData fields |
|---|---|
| `submit_quiz` | `quizTopic: string`, `quizScore: number (0–100)` |
| `compile_code` | `errorMessage?: string`, `language?: string`, `codeSnippet?: string` |
| `navigate` | `moduleId: string`, `lessonId: string`, `lessonTitle: string` |
| `chat_message` | `chatMessageText: string` |

**Response:**

```json
{
  "ok": true,
  "state": "dance",
  "speech": "Wow! 87% on Recursion! You're amazing! 🎉",
  "message": { "text": "...", "tone": "friendly" },
  "actions": [],
  "mascot": { "state": "dance", "bubbleText": "...", "customAnimation": "wave" }
}
```

---

### `POST /api/chat`

Send a chat message to Vedika and get an AI-generated reply.

**Request body:**

```json
{
  "action":       "chat_message",
  "userId":       "student@example.com",
  "currentRoute": "/ai-tutor",
  "contextData": {
    "chatMessageText": "Can you explain recursion with an example?"
  }
}
```

**Response:**

```json
{
  "response": "Think of a function that calls itself...",
  "message": { "text": "...", "tone": "friendly" },
  "actions": [],
  "mascot":  { "state": "idle", "bubbleText": "..." }
}
```

---

### `POST /api/onboard`

Register/update the current user profile (call on first login).

```json
{
  "userId": "student@example.com",
  "name":   "Priya",
  "age":    17
}
```

---

### `GET /api/status`

Returns the full memory object for the current active user.

---

## WebSocket API Reference

### Connect

```
ws://localhost:7001
```

Vedika pushes events automatically whenever her state changes. Your LMS just needs to listen.

### Event types

| event | payload fields | description |
|---|---|---|
| `stateChange` | `state: string`, `userId?: string` | Mascot changed state |
| `speech` | `text: string` | Mascot spoke a line |
| `chat` | `userId, state, userMessage, reply` | Chat completed |
| `activity` | `activityType, state, speech, userId` | Activity processed |
| `sleeping` | — | Mascot went to sleep |
| `openAITutor`| `tab: string, userId?: string` | Mascot triggered AI Tutor page opening & circular menu spin animation |

### Detecting if Vedika is running

```ts
// Try HTTP first
const isAlive = await fetch('http://localhost:7000/api/status')
  .then(r => r.ok)
  .catch(() => false);
```

---

## Integration Checklist

- [ ] Copy `VedikaClient.ts` to `src/lib/vedika/`
- [ ] Add `userId` (student email) to every API call
- [ ] Call `sendActivity('navigate', ...)` on route change
- [ ] Call `sendActivity('submit_quiz', ...)` after quiz submission
- [ ] Call `sendActivity('compile_code', ...)` on code run/error
- [ ] Call `sendChat(message)` in your AI tutor chat UI
- [ ] Optional: `connectWebSocket()` to mirror mascot state in browser UI

---

## Common Pitfalls

> **CORS**: The local server already sends `Access-Control-Allow-Origin: *`. No proxy needed for localhost requests from the browser.

> **Vedika not running**: Always check `isVedikaRunning()` before making calls — silently skip if false so the LMS works without the desktop app.

> **Mixed content**: If your LMS is deployed over HTTPS, browsers will block HTTP requests to localhost. Use the provided `VedikaClient` which catches errors silently, or run your LMS on HTTP in dev.
