import React, { useState, useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { MessageCircle, X, Send, Mic, MicOff, Loader2 } from 'lucide-react';
import { fetchApi, getUserId } from '../utils/api';

// Voice upload uchun (multipart) — fetchApi JSON bilan bog'liq, shuning uchun fetch ishlatamiz
const API_BASE_URL = '/api';

// Format timer mm:ss
const fmtTimer = (ms) => {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const ss = String(s % 60).padStart(2, '0');
  return `${m}:${ss}`;
};

/* ─── ChatWidget: o'ng past burchakdagi suzuvchi AI yordamchi ───
 * - Bossam bottom sheet chat ochiladi
 * - Text input + voice tugmasi (Telegram bot'ga yo'naltiradi)
 * - Backend /api/chat dan actions massivini olib bajaradi:
 *   navigate / change_language / change_theme / open_modal / refresh_data
 */
const ChatWidget = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { i18n } = useTranslation();

  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([
    { role: 'assistant', text: "Salom! Men Somly AI yordamchingizman. Nimaga yordam bera olaman?" }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);

  // Voice recording state
  const [isRecording, setIsRecording] = useState(false);
  const [recordMs, setRecordMs] = useState(0);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const recordStreamRef = useRef(null);
  const recordTimerRef = useRef(null);
  const recordStartTsRef = useRef(0);

  // Pulse animation flag (yangi xabar bo'lganda diqqat tortish uchun)
  const [hasUnread, setHasUnread] = useState(false);

  useEffect(() => {
    // Auto-scroll to bottom on new messages
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  // Auto-focus input when modal opens (Apple-like)
  useEffect(() => {
    if (isOpen && inputRef.current) {
      setTimeout(() => inputRef.current?.focus(), 350);
    }
  }, [isOpen]);

  // Action handler — backend dan kelgan har bir action'ni bajaradi
  const executeAction = useCallback((action) => {
    if (!action || !action.type) return;
    switch (action.type) {
      case 'navigate':
        if (action.to && action.to !== location.pathname) {
          navigate(action.to);
        }
        break;
      case 'change_language':
        if (action.code) {
          i18n.changeLanguage(action.code);
          fetchApi('/settings/language', {
            method: 'POST',
            body: JSON.stringify({ user_id: getUserId(), language: action.code })
          }).catch(() => {});
        }
        break;
      case 'change_theme':
        if (action.mode) {
          document.documentElement.setAttribute('data-theme', action.mode);
          localStorage.setItem('user_theme', action.mode);
          window.dispatchEvent(new CustomEvent('theme_changed', { detail: action.mode }));
        }
        break;
      case 'open_modal':
        // Mini App'da QuickActions modal'ini ochish uchun custom event
        window.dispatchEvent(new CustomEvent('chat_open_modal', { detail: action.modal }));
        // Bosh sahifaga o'tamiz (QuickActions u yerda)
        if (location.pathname !== '/') navigate('/');
        break;
      case 'refresh_data':
        // Mini App sahifalari WS / app_online event'iga reaktsiya qiladi
        window.dispatchEvent(new Event('app_online'));
        break;
      default:
        // Noma'lum action — e'tibor bermaymiz
        break;
    }
  }, [navigate, location.pathname, i18n]);

  const sendMessage = async (text) => {
    const trimmed = (text ?? input).trim();
    if (!trimmed || loading) return;

    const userMsg = { role: 'user', text: trimmed };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const res = await fetchApi('/chat', {
        method: 'POST',
        body: JSON.stringify({
          user_id: getUserId(),
          message: trimmed,
          current_page: location.pathname,
        })
      });

      const reply = res?.reply || 'Hozir javob bera olmadim.';
      setMessages(prev => [...prev, { role: 'assistant', text: reply }]);

      // Bajariladigan action'lar
      const actions = Array.isArray(res?.actions) ? res.actions : [];
      actions.forEach(executeAction);

      if (!isOpen) setHasUnread(true);
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        text: "⚠️ Xabar yuborib bo'lmadi. Internet aloqasini tekshiring."
      }]);
    } finally {
      setLoading(false);
    }
  };

  // ── Voice cleanup helper ──
  const cleanupRecording = useCallback(() => {
    if (recordTimerRef.current) {
      clearInterval(recordTimerRef.current);
      recordTimerRef.current = null;
    }
    if (recordStreamRef.current) {
      recordStreamRef.current.getTracks().forEach(t => t.stop());
      recordStreamRef.current = null;
    }
    mediaRecorderRef.current = null;
    audioChunksRef.current = [];
  }, []);

  // ── Voice yozishni boshlash ──
  const startRecording = async () => {
    const tg = window.Telegram?.WebApp;
    if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        text: "🎤 Bu qurilmada ovoz yozish mavjud emas. Matn yozib yuboring."
      }]);
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recordStreamRef.current = stream;

      // Eng yaxshi mavjud mimetype'ni tanlaymiz
      const mimes = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/ogg;codecs=opus',
        'audio/ogg',
        'audio/mp4',
      ];
      let chosenMime = '';
      for (const m of mimes) {
        if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(m)) {
          chosenMime = m;
          break;
        }
      }

      const recorder = chosenMime
        ? new MediaRecorder(stream, { mimeType: chosenMime })
        : new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        const chunks = audioChunksRef.current;
        const mime = recorder.mimeType || 'audio/webm';
        const blob = new Blob(chunks, { type: mime });
        cleanupRecording();
        setIsRecording(false);
        setRecordMs(0);

        // Juda qisqa (< 0.5s) — yubormaymiz
        if (blob.size < 1024) {
          setMessages(prev => [...prev, {
            role: 'assistant',
            text: "🎤 Ovoz juda qisqa. Mikrofonni 1+ soniya ushlab turib gapiring."
          }]);
          return;
        }

        await sendVoice(blob, mime);
      };

      recordStartTsRef.current = Date.now();
      setRecordMs(0);
      recordTimerRef.current = setInterval(() => {
        const elapsed = Date.now() - recordStartTsRef.current;
        setRecordMs(elapsed);
        // Auto-stop at 60 seconds
        if (elapsed >= 60_000) {
          stopRecording();
        }
      }, 100);

      recorder.start(250); // collect chunks every 250ms
      setIsRecording(true);
    } catch (err) {
      console.error('Mic access denied or failed:', err);
      let msg = "🎤 Mikrofonga ruxsat berilmadi.";
      if (err && err.name === 'NotAllowedError') {
        msg = "🎤 Mikrofonga ruxsat bering — Telegram sozlamalarida ruxsatni yoqing.";
      } else if (err && err.name === 'NotFoundError') {
        msg = "🎤 Qurilmangizda mikrofon topilmadi.";
      }
      setMessages(prev => [...prev, { role: 'assistant', text: msg }]);
      cleanupRecording();
      setIsRecording(false);
    }
  };

  // ── Voice yozishni to'xtatish ──
  const stopRecording = () => {
    const tg = window.Telegram?.WebApp;
    if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
    try {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      } else {
        cleanupRecording();
        setIsRecording(false);
        setRecordMs(0);
      }
    } catch (e) {
      console.error('stopRecording error:', e);
      cleanupRecording();
      setIsRecording(false);
      setRecordMs(0);
    }
  };

  // ── Voice yozishni bekor qilish (yuborishsiz) ──
  const cancelRecording = () => {
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.onstop = () => {}; // bekor — sendVoice chaqirilmasin
      try { mediaRecorderRef.current.stop(); } catch (e) {}
    }
    cleanupRecording();
    setIsRecording(false);
    setRecordMs(0);
  };

  // ── Voice blob'ni backend'ga yuborish ──
  const sendVoice = async (blob, mime) => {
    const ext = mime.includes('webm') ? 'webm'
              : mime.includes('ogg')  ? 'ogg'
              : mime.includes('mp4')  ? 'm4a'
              : 'webm';
    const fileName = `voice.${ext}`;

    // Placeholder xabar — "🎤 Ovoz tahlil qilinmoqda..."
    setMessages(prev => [...prev, { role: 'user', text: '🎤 Ovoz xabar...' }]);
    setLoading(true);

    try {
      const form = new FormData();
      form.append('audio', blob, fileName);
      form.append('user_id', String(getUserId()));
      form.append('current_page', location.pathname);

      const resp = await fetch(`${API_BASE_URL}/chat/voice`, {
        method: 'POST',
        body: form,
        // NOTE: Content-Type'ni o'rnatmaymiz — brauzer o'zi boundary bilan o'rnatadi
      });

      let data = null;
      try { data = await resp.json(); } catch (e) { data = null; }

      const transcript = data?.transcript || '';
      const reply = data?.reply || (resp.ok ? "Tushundim." : "⚠️ Ovoz qabul bo'lmadi.");

      // Oxirgi placeholder'ni transcribed text bilan almashtiramiz, keyin AI javobini qo'shamiz
      setMessages(prev => {
        const next = [...prev];
        // oxirgi user xabar — placeholder
        for (let i = next.length - 1; i >= 0; i--) {
          if (next[i].role === 'user' && next[i].text === '🎤 Ovoz xabar...') {
            next[i] = { role: 'user', text: transcript ? `🎤 ${transcript}` : '🎤 Ovoz xabar' };
            break;
          }
        }
        next.push({ role: 'assistant', text: reply });
        return next;
      });

      // Actions bajaramiz
      const actions = Array.isArray(data?.actions) ? data.actions : [];
      actions.forEach(executeAction);

      if (!isOpen) setHasUnread(true);
    } catch (err) {
      console.error('sendVoice error:', err);
      setMessages(prev => [...prev, {
        role: 'assistant',
        text: "⚠️ Ovoz yuborib bo'lmadi. Internet aloqasini tekshiring."
      }]);
    } finally {
      setLoading(false);
    }
  };

  // Component unmount paytida ham tozalash
  useEffect(() => {
    return () => cleanupRecording();
  }, [cleanupRecording]);

  const handleOpen = () => {
    setIsOpen(true);
    setHasUnread(false);
    if (window.Telegram?.WebApp?.HapticFeedback) {
      window.Telegram.WebApp.HapticFeedback.impactOccurred('light');
    }
  };

  return createPortal(
    <>
      {/* Floating Button */}
      {!isOpen && (
        <button
          onClick={handleOpen}
          aria-label="AI Chat ochish"
          className="chat-fab"
          style={{
            position: 'fixed',
            bottom: 'calc(90px + env(safe-area-inset-bottom))',
            right: '20px',
            width: '58px',
            height: '58px',
            borderRadius: '50%',
            background: 'linear-gradient(135deg, #0A84FF 0%, #5E5CE6 100%)',
            border: 'none',
            color: '#FFF',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            zIndex: 9998,
          }}
        >
          <MessageCircle size={26} />
          {hasUnread && (
            <span style={{
              position: 'absolute',
              top: '8px',
              right: '8px',
              width: '10px',
              height: '10px',
              borderRadius: '50%',
              background: '#FF453A',
              border: '2px solid #FFF',
            }} />
          )}
        </button>
      )}

      {/* Bottom Sheet Chat */}
      {isOpen && (
        <div
          onClick={() => setIsOpen(false)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            backdropFilter: 'blur(8px)',
            WebkitBackdropFilter: 'blur(8px)',
            zIndex: 9999,
            display: 'flex',
            alignItems: 'flex-end',
            justifyContent: 'center',
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: 'var(--card-solid, var(--card))',
              width: '100%',
              maxWidth: '560px',
              height: '80vh',
              maxHeight: '720px',
              borderRadius: '24px 24px 0 0',
              display: 'flex',
              flexDirection: 'column',
              boxSizing: 'border-box',
              animation: 'slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
              overflow: 'hidden',
            }}
          >
            {/* Header */}
            <div style={{
              padding: '14px 16px',
              borderBottom: '1px solid var(--border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexShrink: 0,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <div style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '50%',
                  background: 'linear-gradient(135deg, #0A84FF 0%, #5E5CE6 100%)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}>
                  <MessageCircle size={18} color="#FFF" />
                </div>
                <div>
                  <div style={{ fontWeight: 700, fontSize: '15px' }}>Somly AI</div>
                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                    Sizning yordamchingiz
                  </div>
                </div>
              </div>
              <button
                onClick={() => setIsOpen(false)}
                aria-label="Yopish"
                style={{
                  background: 'var(--bg)',
                  border: 'none',
                  width: '32px',
                  height: '32px',
                  borderRadius: '50%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                  color: 'var(--text-secondary)',
                }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Messages */}
            <div
              ref={scrollRef}
              style={{
                flex: 1,
                overflowY: 'auto',
                padding: '16px',
                display: 'flex',
                flexDirection: 'column',
                gap: '10px',
              }}
            >
              {messages.map((m, i) => (
                <div
                  key={i}
                  className="chat-message-bubble"
                  style={{
                    alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                    maxWidth: '85%',
                    background: m.role === 'user'
                      ? 'linear-gradient(135deg, #0A84FF 0%, #5E5CE6 100%)'
                      : 'var(--bg)',
                    color: m.role === 'user' ? '#FFF' : 'var(--text-primary)',
                    padding: '10px 14px',
                    borderRadius: m.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                    fontSize: '14px',
                    lineHeight: '1.45',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    boxShadow: m.role === 'user' ? '0 4px 12px rgba(10,132,255,0.25)' : '0 2px 6px rgba(0,0,0,0.08)',
                  }}
                >
                  {m.text}
                </div>
              ))}
              {loading && (
                <div style={{
                  alignSelf: 'flex-start',
                  background: 'var(--bg)',
                  padding: '10px 14px',
                  borderRadius: '16px 16px 16px 4px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  color: 'var(--text-secondary)',
                  fontSize: '13px',
                }}>
                  <Loader2 size={14} className="animate-spin" />
                  AI o'ylayapti...
                </div>
              )}
            </div>

            {/* Input area */}
            <div style={{
              padding: '12px 16px',
              paddingBottom: 'max(12px, calc(12px + env(safe-area-inset-bottom)))',
              borderTop: '1px solid var(--border)',
              display: 'flex',
              gap: '8px',
              alignItems: 'center',
              flexShrink: 0,
              background: 'var(--card-solid, var(--card))',
            }}>
              {isRecording ? (
                <>
                  <button
                    onClick={cancelRecording}
                    aria-label="Bekor qilish"
                    title="Bekor qilish"
                    style={{
                      width: '40px',
                      height: '40px',
                      minWidth: '40px',
                      borderRadius: '50%',
                      background: 'var(--bg)',
                      border: '1px solid var(--border)',
                      color: 'var(--text-secondary)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      cursor: 'pointer',
                    }}
                  >
                    <X size={18} />
                  </button>
                  <div style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    background: 'rgba(255, 69, 58, 0.1)',
                    border: '1px solid rgba(255, 69, 58, 0.3)',
                    borderRadius: '20px',
                    padding: '10px 16px',
                  }}>
                    <span style={{
                      width: '10px',
                      height: '10px',
                      borderRadius: '50%',
                      background: '#FF453A',
                      animation: 'sendPulse 1.2s ease-in-out infinite',
                    }} />
                    <span style={{
                      flex: 1,
                      fontSize: '13px',
                      color: 'var(--text-primary)',
                      fontWeight: 600,
                      fontVariantNumeric: 'tabular-nums',
                    }}>
                      Yozilmoqda... {fmtTimer(recordMs)}
                    </span>
                  </div>
                  <button
                    onClick={stopRecording}
                    aria-label="Yuborish"
                    style={{
                      width: '40px',
                      height: '40px',
                      minWidth: '40px',
                      borderRadius: '50%',
                      background: 'linear-gradient(135deg, #0A84FF 0%, #5E5CE6 100%)',
                      border: 'none',
                      color: '#FFF',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      cursor: 'pointer',
                      boxShadow: '0 4px 12px rgba(10, 132, 255, 0.4)',
                    }}
                  >
                    <Send size={16} />
                  </button>
                </>
              ) : (
                <button
                  onClick={startRecording}
                  disabled={loading}
                  aria-label="Ovoz yozish"
                  title="Bosing va gapiring"
                  style={{
                    width: '40px',
                    height: '40px',
                    minWidth: '40px',
                    borderRadius: '50%',
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    color: 'var(--primary)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: loading ? 'not-allowed' : 'pointer',
                    opacity: loading ? 0.5 : 1,
                    transition: 'all 0.2s',
                  }}
                >
                  <Mic size={18} />
                </button>
              )}
              {!isRecording && (
                <>
                  <input
                    ref={inputRef}
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        sendMessage();
                      }
                    }}
                    placeholder="Savol yozing..."
                    disabled={loading}
                    className="apple-input"
                    style={{
                      flex: 1,
                      background: 'var(--bg)',
                      border: '1px solid var(--border)',
                      borderRadius: '20px',
                      padding: '10px 16px',
                      color: 'var(--text-primary)',
                      fontSize: '14px',
                      outline: 'none',
                    }}
                  />
                  <button
                    onClick={() => sendMessage()}
                    disabled={!input.trim() || loading}
                    aria-label="Yuborish"
                    className={input.trim() && !loading ? 'chat-send-active' : ''}
                    style={{
                      width: '40px',
                      height: '40px',
                      minWidth: '40px',
                      borderRadius: '50%',
                      background: (input.trim() && !loading)
                        ? 'linear-gradient(135deg, #0A84FF 0%, #5E5CE6 100%)'
                        : 'var(--border)',
                      border: 'none',
                      color: '#FFF',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      cursor: (input.trim() && !loading) ? 'pointer' : 'not-allowed',
                      opacity: (input.trim() && !loading) ? 1 : 0.6,
                      transition: 'opacity 0.2s, transform 0.15s',
                    }}
                  >
                    <Send size={16} />
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>,
    document.body
  );
};

export default ChatWidget;
