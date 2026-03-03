import { FormEvent, useEffect, useState } from 'react';
import { createSession, sendMessage } from './api';
import type { ChatMessage } from './types';

function App() {
  const [sessionId, setSessionId] = useState<string>('');
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      content:
        "Hello, I'm the Contractor Access Agent. Please describe the work your contractor will be doing and the services they will need access to?",
    },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const session = await createSession();
        setSessionId(session.session_id);
      } catch (sessionError) {
        setError((sessionError as Error).message);
      }
    })();
  }, []);

  const handleSend = async (event: FormEvent) => {
    event.preventDefault();
    if (!input.trim() || !sessionId) return;

    const userMessage: ChatMessage = { role: 'user', content: input.trim() };
    const nextMessages = [...messages, userMessage];

    setMessages(nextMessages);
    setInput('');
    setIsLoading(true);
    setError(null);

    try {
      const response = await sendMessage(sessionId, userMessage.content, messages);
      setMessages(response.messages);
    } catch (messageError) {
      setError((messageError as Error).message);
      setMessages(nextMessages);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="chat-shell">
      <header>
        <h1>Agentic Magic Link Chat</h1>
        <p>Session: {sessionId || 'Creating session...'}</p>
      </header>

      <section className="messages" aria-live="polite">
        {messages.length === 0 ? (
          <p className="placeholder">Start by describing the IAM workflow you need.</p>
        ) : (
          messages.map((message, index) => (
            <article key={`${message.role}-${index}`} className={`message ${message.role}`}>
              <h2>{message.role === 'user' ? 'You' : 'Assistant'}</h2>
              <p>{message.content}</p>
            </article>
          ))
        )}
      </section>

      <form className="composer" onSubmit={handleSend}>
        <label htmlFor="prompt">Message</label>
        <textarea
          id="prompt"
          value={input}
          rows={3}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask the agent to build a magic link IAM flow..."
        />
        <button type="submit" disabled={isLoading || !sessionId}>
          {isLoading ? 'Sending...' : 'Send'}
        </button>
      </form>

      {error ? <p className="error">{error}</p> : null}
    </main>
  );
}

export default App;
