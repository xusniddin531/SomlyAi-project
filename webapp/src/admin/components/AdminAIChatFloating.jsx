import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Sparkles, X } from 'lucide-react';
import AdminAIChat from '../pages/AdminAIChat';

/**
 * AdminAIChatFloating — admin paneldagi AI Chat'ni o'ng past burchakda
 * suzib turuvchi tugma (FAB) sifatida ko'rsatadi.
 *
 * - Tugma har sahifada doim ko'rinadi (sidebar/tab-bar dan tashqari)
 * - Bosilganda full-height bottom sheet modal ochiladi
 * - Mavjud AdminAIChat komponentini reuse qiladi (qayta yozish yo'q)
 * - Responsive: mobile'da full screen, desktop'da 480px panel
 */
const AdminAIChatFloating = ({ token }) => {
  const [open, setOpen] = useState(false);

  // ESC bilan yopish
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open]);

  return createPortal(
    <>
      {/* FAB tugmasi — har doim ko'rinadi */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          aria-label="AI Yordamchini ochish"
          className="admin-ai-fab"
          style={{
            position: 'fixed',
            bottom: 'calc(80px + env(safe-area-inset-bottom))',
            right: '20px',
            width: '56px',
            height: '56px',
            borderRadius: '50%',
            background: 'linear-gradient(135deg, #8B5CF6 0%, #6366F1 50%, #3B82F6 100%)',
            color: '#fff',
            border: 'none',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            boxShadow: '0 8px 24px rgba(139, 92, 246, 0.45)',
            zIndex: 9997,
            transition: 'transform 0.18s ease, box-shadow 0.2s ease',
          }}
          onMouseDown={(e) => e.currentTarget.style.transform = 'scale(0.92)'}
          onMouseUp={(e) => e.currentTarget.style.transform = 'scale(1)'}
          onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1)'}
          onTouchStart={(e) => e.currentTarget.style.transform = 'scale(0.92)'}
          onTouchEnd={(e) => e.currentTarget.style.transform = 'scale(1)'}
        >
          <Sparkles size={24} />
        </button>
      )}

      {/* Bottom sheet modal */}
      {open && (
        <div
          onClick={() => setOpen(false)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.55)',
            backdropFilter: 'blur(8px)',
            WebkitBackdropFilter: 'blur(8px)',
            zIndex: 9998,
            display: 'flex',
            alignItems: 'flex-end',
            justifyContent: 'flex-end',
            padding: '0',
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: 'var(--admin-bg)',
              width: '100%',
              maxWidth: '520px',
              height: '92vh',
              maxHeight: '92dvh',
              borderRadius: '20px 20px 0 0',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
              boxShadow: '0 -16px 60px rgba(0,0,0,0.5)',
              animation: 'slideUpFab 0.28s cubic-bezier(0.16, 1, 0.3, 1)',
            }}
          >
            {/* Header */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '14px 16px',
              borderBottom: '1px solid var(--admin-border)',
              flexShrink: 0,
              background: 'var(--admin-card)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <div style={{
                  width: '34px',
                  height: '34px',
                  borderRadius: '10px',
                  background: 'linear-gradient(135deg, #8B5CF6, #6366F1)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}>
                  <Sparkles size={18} color="#fff" />
                </div>
                <div>
                  <div style={{ fontWeight: 700, fontSize: '15px', color: 'var(--admin-text)' }}>
                    AI Yordamchi
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--admin-text-secondary)' }}>
                    Bot statistikasi haqida so'rang
                  </div>
                </div>
              </div>
              <button
                onClick={() => setOpen(false)}
                aria-label="Yopish"
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '50%',
                  background: 'var(--admin-bg)',
                  border: '1px solid var(--admin-border)',
                  color: 'var(--admin-text-secondary)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                }}
              >
                <X size={16} />
              </button>
            </div>

            {/* AI Chat content */}
            <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
              <AdminAIChat token={token} />
            </div>
          </div>
        </div>
      )}

      {/* Animation keyframes (inline so it works even if admin.css doesn't have it) */}
      <style>{`
        @keyframes slideUpFab {
          from { transform: translateY(100%); opacity: 0.5; }
          to   { transform: translateY(0); opacity: 1; }
        }
        .admin-ai-fab:hover {
          box-shadow: 0 12px 32px rgba(139, 92, 246, 0.6) !important;
        }
        @media (min-width: 768px) {
          .admin-ai-fab {
            bottom: 24px !important;
            right: 24px !important;
          }
        }
      `}</style>
    </>,
    document.body
  );
};

export default AdminAIChatFloating;
