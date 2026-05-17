import React, { useState, useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { MessageCircle, X, Send, Mic, Loader2 } from 'lucide-react';
import { fetchApi, getUserId } from '../utils/api';

const BOT_USERNAME = 'somly_ai_bot'; // Voice — Telegram bot orqali

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

  // Pulse animation flag (yangi xabar bo'lganda diqqat tortish uchun)
  const [hasUnread, setHasUnread] = useState(false);

  useEffect(() => {
    // Auto-scroll to bottom on new messages
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

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

  // Voice tugmasi: Telegram WebApp orqali bot'ga yo'naltirish
  const openBotForVoice = () => {
    const tg = window.Telegram?.WebApp;
    if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');

    if (tg?.showPopup) {
      tg.showPopup({
        title: 'Ovoz yuborish',
        message: "Bot chatiga o'tib, mikrofon tugmasini bosing va ovoz yuboring. Men o'qib, bu yerga javobni qaytaraman.",
        buttons: [
          { id: 'open', type: 'default', text: "Bot chatini ochish" },
          { id: 'cancel', type: 'cancel' }
        ]
      }, (btnId) => {
        if (btnId === 'open') {
          if (tg.openTelegramLink) {
            tg.openTelegramLink(`https://t.me/${BOT_USERNAME}`);
          } else if (tg.close) {
            tg.close();
          }
        }
      });
    } else {
      // Fallback: showPopup yo'q bo'lsa
      window.open(`https://t.me/${BOT_USERNAME}`, '_blank');
    }
  };

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
          style={{
            position: 'fixed',
            bottom: '90px',
            right: '20px',
            width: '56px',
            height: '56px',
            borderRadius: '50%',
            background: 'linear-gradient(135deg, #0A84FF 0%, #5E5CE6 100%)',
            border: 'none',
            color: '#FFF',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            boxShadow: '0 8px 24px rgba(10, 132, 255, 0.4)',
            zIndex: 9998,
            transition: 'transform 0.2s',
          }}
          onMouseDown={(e) => e.currentTarget.style.transform = 'scale(0.92)'}
          onMouseUp={(e) => e.currentTarget.style.transform = 'scale(1)'}
          onTouchStart={(e) => e.currentTarget.style.transform = 'scale(0.92)'}
          onTouchEnd={(e) => e.currentTarget.style.transform = 'scale(1)'}
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
              <button
                onClick={openBotForVoice}
                aria-label="Ovoz yuborish"
                title="Bot orqali ovoz yuborish"
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
                  cursor: 'pointer',
                }}
              >
                <Mic size={18} />
              </button>
              <input
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
                  transition: 'opacity 0.2s',
                }}
              >
                <Send size={16} />
              </button>
            </div>
          </div>
        </div>
      )}
    </>,
    document.body
  );
};

export default ChatWidget;
