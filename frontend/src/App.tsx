import { FormEvent, useEffect, useMemo, useState } from 'react';
import { createSession, sendMessage } from './api';
import type { ChatMessage, MagicLinkScriptPayload, NextExpectedInput } from './types';

const NEXT_INPUT_HELPER: Record<NextExpectedInput, string> = {
  work_description: 'Expected input: describe the IAM work you need done.',
  account_id: 'Expected input: provide the 12-digit AWS account ID.',
  role_arn: 'Expected input: provide the IAM role ARN to assume.',
  session_duration: 'Expected input: provide a session duration in seconds (900-43200).',
};

function App() {
  const [sessionId, setSessionId] = useState<string>('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [magicLinkScript, setMagicLinkScript] = useState<MagicLinkScriptPayload | null>(null);
  const [nextExpectedInput, setNextExpectedInput] = useState<NextExpectedInput | null>(null);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const session = await createSession();
        setSessionId(session.session_id);
        setNextExpectedInput(session.next_expected_input ?? null);

        if (session.initial_assistant_message) {
          setMessages([{ role: 'assistant', content: session.initial_assistant_message }]);
        }
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
      setMagicLinkScript(response.magic_link_script ?? null);
      setNextExpectedInput(response.next_expected_input ?? null);
    } catch (messageError) {
      setError((messageError as Error).message);
      setMessages(nextMessages);
    } finally {
      setIsLoading(false);
    }
  };

  const composerHelper = useMemo(() => {
    if (!nextExpectedInput) return null;
    return NEXT_INPUT_HELPER[nextExpectedInput];
  }, [nextExpectedInput]);

  return (
    <main className="chat-shell">
      <header>
        <h1>Agentic Magic Link Chat</h1>
        <p>Session: {sessionId || 'Creating session...'}</p>
      </header>

      <section className="messages" aria-live="polite">
        {messages.length === 0 ? (
          <p className="placeholder">No messages yet.</p>
        ) : (
          messages.map((message, index) => (
            <article key={`${message.role}-${index}`} className={`message ${message.role}`}>
              <h2>{message.role === 'user' ? 'You' : 'Assistant'}</h2>
              <p>{message.content}</p>
            </article>
          ))
        )}
      </section>

      {magicLinkScript ? (
        <section className="script-card" aria-live="polite">
          <h2>Magic Link Script</h2>
          <p>
            <strong>Version:</strong> {magicLinkScript.version ?? 'unknown'}
          </p>
          <p>
            <strong>Checksum (SHA-256):</strong> {magicLinkScript.checksum_sha256 ?? 'unknown'}
          </p>
          <pre>{magicLinkScript.content}</pre>
        </section>
      ) : null}

      <form className="composer" onSubmit={handleSend}>
        <label htmlFor="prompt">Message</label>
        <textarea
          id="prompt"
          value={input}
          rows={3}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask the agent to build a magic link IAM flow..."
        />
        {composerHelper ? <p className="composer-hint">{composerHelper}</p> : null}
        <button type="submit" disabled={isLoading || !sessionId}>
          {isLoading ? 'Sending...' : 'Send'}
        </button>
      </form>

      {error ? <p className="error">{error}</p> : null}
    </main>
  );
}

export default App;
