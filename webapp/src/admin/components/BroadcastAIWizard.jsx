import React, { useState } from 'react';
import { X, Sparkles, ChevronRight, ChevronLeft, Check, RefreshCw, Wand2 } from 'lucide-react';

/**
 * BroadcastAIWizard — Meta Ads kabi step-by-step reklama matnini AI bilan yaratish.
 *
 * 4 ta step:
 *  1. Maqsad (goal): Promo / E'lon / Eslatma / Maslahat / Boshqa
 *  2. Auditoriya (audience): Hammasi / Yoshlar / Aktiv / Yangilar / Boshqa
 *  3. Uslub (tone): Do'stona / Rasmiy / Hayajonli / Qisqa
 *  4. Asosiy fikrlar (key_points): erkin matn
 *
 * Keyin AI → 3 ta variant. Admin tanlaydi → onSelect(text).
 *
 * Props:
 *   - token: admin auth token
 *   - onClose(): modal yopish
 *   - onSelect(text): tanlangan reklama matni
 *   - language: 'uz' | 'ru' | 'en'
 */
const GOALS = [
  { id: 'promo', label: 'Promo / Aksiya', emoji: '🎁' },
  { id: 'announce', label: 'Yangi xizmat e\'loni', emoji: '📢' },
  { id: 'reminder', label: 'Eslatma', emoji: '⏰' },
  { id: 'advice', label: 'Foydali maslahat', emoji: '💡' },
  { id: 'other', label: 'Boshqa', emoji: '✍️' },
];

const AUDIENCES = [
  { id: 'all', label: 'Hammasi' },
  { id: 'youth', label: 'Yoshlar (18-30)' },
  { id: 'active', label: 'Aktiv foydalanuvchilar' },
  { id: 'new', label: 'Yangi foydalanuvchilar' },
  { id: 'inactive', label: 'Faolsiz (qaytarish)' },
];

const TONES = [
  { id: 'friendly', label: "Do'stona", emoji: '😊' },
  { id: 'formal', label: 'Rasmiy', emoji: '🎩' },
  { id: 'exciting', label: 'Hayajonli', emoji: '🔥' },
  { id: 'short', label: 'Juda qisqa', emoji: '⚡' },
];

const BroadcastAIWizard = ({ token, onClose, onSelect, language = 'uz' }) => {
  const [step, setStep] = useState(0); // 0..3 (savollar), 4 (loading/preview)
  const [form, setForm] = useState({
    goalId: null,
    audienceId: 'all',
    toneId: 'friendly',
    keyPoints: '',
  });
  const [generating, setGenerating] = useState(false);
  const [suggestions, setSuggestions] = useState([]); // {main, alts}
  const [error, setError] = useState('');

  const getLabel = (list, id) => (list.find(x => x.id === id) || {}).label || '';

  const canGoNext = () => {
    if (step === 0) return !!form.goalId;
    if (step === 1) return !!form.audienceId;
    if (step === 2) return !!form.toneId;
    if (step === 3) return form.keyPoints.trim().length >= 3;
    return false;
  };

  const handleGenerate = async () => {
    setGenerating(true);
    setError('');
    setStep(4);
    try {
      const res = await fetch('/api/admin/broadcast/ai-suggest', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          goal: getLabel(GOALS, form.goalId),
          audience: getLabel(AUDIENCES, form.audienceId),
          tone: getLabel(TONES, form.toneId),
          key_points: form.keyPoints.trim(),
          language,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        const all = [data.text, ...(data.suggestions || [])].filter(Boolean);
        setSuggestions(all);
      } else {
        const err = await res.json().catch(() => ({}));
        setError(err.error || 'AI hozir javob bera olmadi');
      }
    } catch (e) {
      setError('Tarmoq xatosi');
    } finally {
      setGenerating(false);
    }
  };

  const handleSelect = (text) => {
    onSelect(text);
    onClose();
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
        backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
        zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: '16px',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--admin-bg)',
          borderRadius: '20px',
          width: '100%',
          maxWidth: '560px',
          maxHeight: '92vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          boxShadow: '0 24px 60px rgba(0,0,0,0.4)',
          animation: 'fadeIn 0.2s ease',
        }}
      >
        {/* Header */}
        <div style={{
          padding: '16px 20px',
          borderBottom: '1px solid var(--admin-border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'var(--admin-card)',
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{
              width: '36px', height: '36px', borderRadius: '10px',
              background: 'linear-gradient(135deg,#8B5CF6,#6366F1)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff',
            }}>
              <Wand2 size={18} />
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: '15px', color: 'var(--admin-text)' }}>AI Reklama Sehrgar</div>
              <div style={{ fontSize: '11px', color: 'var(--admin-text-secondary)' }}>
                Bosqichma-bosqich → AI matn tayyorlaydi
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              width: '32px', height: '32px', borderRadius: '50%',
              background: 'var(--admin-bg)', border: '1px solid var(--admin-border)',
              color: 'var(--admin-text-secondary)', cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
          ><X size={16} /></button>
        </div>

        {/* Progress dots */}
        {step < 4 && (
          <div style={{
            display: 'flex', gap: '6px', padding: '12px 20px',
            borderBottom: '1px solid var(--admin-border)', background: 'var(--admin-bg)',
          }}>
            {[0, 1, 2, 3].map(i => (
              <div key={i} style={{
                flex: 1, height: '4px', borderRadius: '2px',
                background: i <= step ? 'var(--admin-primary)' : 'var(--admin-border)',
                transition: 'all 0.3s',
              }} />
            ))}
          </div>
        )}

        {/* Step content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
          {step === 0 && (
            <StepSelect
              title="🎯 1. Reklamaning maqsadi nima?"
              subtitle="Foydalanuvchi nima qilishini xohlaysiz?"
              options={GOALS}
              value={form.goalId}
              onSelect={(id) => setForm({ ...form, goalId: id })}
              renderEmoji
            />
          )}
          {step === 1 && (
            <StepSelect
              title="👥 2. Kimga yo'naltirilgan?"
              subtitle="Qaysi auditoriyaga yuborasiz?"
              options={AUDIENCES}
              value={form.audienceId}
              onSelect={(id) => setForm({ ...form, audienceId: id })}
            />
          )}
          {step === 2 && (
            <StepSelect
              title="🎨 3. Qanday uslubda?"
              subtitle="Matn qanday ohangda yozilsin?"
              options={TONES}
              value={form.toneId}
              onSelect={(id) => setForm({ ...form, toneId: id })}
              renderEmoji
            />
          )}
          {step === 3 && (
            <div>
              <h3 style={{ margin: '0 0 6px', fontSize: '17px', color: 'var(--admin-text)' }}>
                ✍️ 4. Nima haqida yozay?
              </h3>
              <p style={{ margin: '0 0 14px', fontSize: '13px', color: 'var(--admin-text-secondary)' }}>
                Asosiy fikrlarni qisqa yozing. AI shu asosida 3 ta variant tayyorlaydi.
              </p>
              <textarea
                value={form.keyPoints}
                onChange={(e) => setForm({ ...form, keyPoints: e.target.value })}
                placeholder="Masalan: Yangi 'Avtomatik tasniflash' xizmati ishga tushdi — har bir xarajat avtomatik kategoriyaga ajraladi. Bepul."
                rows={6}
                style={{
                  width: '100%',
                  padding: '12px 14px',
                  background: 'var(--admin-card)',
                  border: '1px solid var(--admin-border)',
                  borderRadius: '12px',
                  color: 'var(--admin-text)',
                  fontSize: '14px',
                  outline: 'none',
                  resize: 'vertical',
                  fontFamily: 'inherit',
                  lineHeight: 1.5,
                  boxSizing: 'border-box',
                }}
              />
              {/* Mini preview of choices */}
              <div style={{
                marginTop: '14px', padding: '10px 12px',
                background: 'var(--admin-card)', borderRadius: '10px',
                fontSize: '12px', color: 'var(--admin-text-secondary)',
                display: 'flex', flexWrap: 'wrap', gap: '12px',
              }}>
                <span>🎯 {getLabel(GOALS, form.goalId)}</span>
                <span>👥 {getLabel(AUDIENCES, form.audienceId)}</span>
                <span>🎨 {getLabel(TONES, form.toneId)}</span>
              </div>
            </div>
          )}
          {step === 4 && (
            <PreviewStep
              loading={generating}
              error={error}
              suggestions={suggestions}
              onRetry={handleGenerate}
              onSelect={handleSelect}
              onBack={() => setStep(3)}
            />
          )}
        </div>

        {/* Footer */}
        {step < 4 && (
          <div style={{
            padding: '14px 20px',
            borderTop: '1px solid var(--admin-border)',
            display: 'flex',
            gap: '8px',
            justifyContent: 'space-between',
            background: 'var(--admin-bg)',
            flexShrink: 0,
          }}>
            <button
              onClick={() => step > 0 ? setStep(step - 1) : onClose()}
              style={{
                padding: '10px 14px', borderRadius: '10px',
                background: 'var(--admin-card)', border: '1px solid var(--admin-border)',
                color: 'var(--admin-text)', cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, fontSize: '13px',
              }}
            >
              <ChevronLeft size={16} /> {step > 0 ? 'Orqaga' : 'Bekor'}
            </button>
            {step < 3 ? (
              <button
                onClick={() => canGoNext() && setStep(step + 1)}
                disabled={!canGoNext()}
                style={{
                  padding: '10px 18px', borderRadius: '10px',
                  background: canGoNext() ? 'linear-gradient(135deg,#8B5CF6,#6366F1)' : 'var(--admin-border)',
                  border: 'none', color: '#fff', cursor: canGoNext() ? 'pointer' : 'not-allowed',
                  opacity: canGoNext() ? 1 : 0.6,
                  display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, fontSize: '13px',
                }}
              >
                Keyingisi <ChevronRight size={16} />
              </button>
            ) : (
              <button
                onClick={() => canGoNext() && handleGenerate()}
                disabled={!canGoNext()}
                style={{
                  padding: '10px 18px', borderRadius: '10px',
                  background: canGoNext() ? 'linear-gradient(135deg,#8B5CF6,#6366F1)' : 'var(--admin-border)',
                  border: 'none', color: '#fff', cursor: canGoNext() ? 'pointer' : 'not-allowed',
                  opacity: canGoNext() ? 1 : 0.6,
                  display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, fontSize: '13px',
                }}
              >
                <Sparkles size={16} /> AI tayyorlasin
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

const StepSelect = ({ title, subtitle, options, value, onSelect, renderEmoji }) => (
  <div>
    <h3 style={{ margin: '0 0 6px', fontSize: '17px', color: 'var(--admin-text)' }}>{title}</h3>
    <p style={{ margin: '0 0 16px', fontSize: '13px', color: 'var(--admin-text-secondary)' }}>{subtitle}</p>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {options.map(opt => (
        <button
          key={opt.id}
          onClick={() => onSelect(opt.id)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            padding: '14px 16px',
            borderRadius: '12px',
            background: value === opt.id ? 'rgba(139,92,246,0.15)' : 'var(--admin-card)',
            border: `1px solid ${value === opt.id ? '#8B5CF6' : 'var(--admin-border)'}`,
            color: 'var(--admin-text)',
            cursor: 'pointer',
            fontSize: '14px',
            fontWeight: 600,
            textAlign: 'left',
            transition: 'all 0.18s ease',
          }}
        >
          {renderEmoji && opt.emoji && <span style={{ fontSize: '20px' }}>{opt.emoji}</span>}
          <span style={{ flex: 1 }}>{opt.label}</span>
          {value === opt.id && <Check size={18} color="#8B5CF6" />}
        </button>
      ))}
    </div>
  </div>
);

const PreviewStep = ({ loading, error, suggestions, onRetry, onSelect, onBack }) => {
  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '40px 20px' }}>
        <div style={{
          width: '60px', height: '60px', margin: '0 auto 16px',
          borderRadius: '50%', background: 'linear-gradient(135deg,#8B5CF6,#6366F1)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          animation: 'pulse 1.5s ease-in-out infinite',
        }}>
          <Sparkles size={28} color="#fff" />
        </div>
        <p style={{ color: 'var(--admin-text)', margin: '0 0 6px', fontWeight: 600 }}>
          AI o'ylayapti...
        </p>
        <p style={{ color: 'var(--admin-text-secondary)', fontSize: '13px', margin: 0 }}>
          3 ta variant tayyorlanmoqda (5-10 soniya)
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ textAlign: 'center', padding: '40px 20px' }}>
        <p style={{ color: '#EF4444', margin: '0 0 16px', fontWeight: 600 }}>❌ {error}</p>
        <div style={{ display: 'flex', gap: '8px', justifyContent: 'center' }}>
          <button onClick={onBack} style={{
            padding: '10px 16px', borderRadius: '10px',
            background: 'var(--admin-card)', border: '1px solid var(--admin-border)',
            color: 'var(--admin-text)', cursor: 'pointer', fontSize: '13px', fontWeight: 600,
          }}>Orqaga</button>
          <button onClick={onRetry} style={{
            padding: '10px 16px', borderRadius: '10px',
            background: 'linear-gradient(135deg,#8B5CF6,#6366F1)', border: 'none',
            color: '#fff', cursor: 'pointer', fontSize: '13px', fontWeight: 600,
            display: 'flex', alignItems: 'center', gap: '6px',
          }}>
            <RefreshCw size={14} /> Qayta urinib ko'rish
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <h3 style={{ margin: '0 0 6px', fontSize: '17px', color: 'var(--admin-text)' }}>
        ✨ AI tayyorlagan variantlar
      </h3>
      <p style={{ margin: '0 0 16px', fontSize: '13px', color: 'var(--admin-text-secondary)' }}>
        Yoqqanini tanlang — keyin Broadcast formasida tahrirlash mumkin
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {suggestions.map((s, i) => (
          <div key={i} style={{
            background: 'var(--admin-card)',
            border: '1px solid var(--admin-border)',
            borderRadius: '12px',
            padding: '14px',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px', marginBottom: '8px' }}>
              <span style={{
                fontSize: '11px', fontWeight: 700, padding: '3px 8px', borderRadius: '6px',
                background: i === 0 ? 'rgba(139,92,246,0.18)' : 'var(--admin-bg)',
                color: i === 0 ? '#8B5CF6' : 'var(--admin-text-secondary)',
              }}>
                {i === 0 ? '🌟 ASOSIY' : `VARIANT ${i + 1}`}
              </span>
              <button
                onClick={() => onSelect(s)}
                style={{
                  padding: '6px 12px', borderRadius: '8px',
                  background: 'linear-gradient(135deg,#8B5CF6,#6366F1)', border: 'none',
                  color: '#fff', cursor: 'pointer', fontSize: '12px', fontWeight: 600,
                  display: 'flex', alignItems: 'center', gap: '4px',
                }}
              ><Check size={13} /> Tanlash</button>
            </div>
            <div style={{
              color: 'var(--admin-text)',
              fontSize: '14px',
              lineHeight: 1.55,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}>{s}</div>
          </div>
        ))}
      </div>
      <button
        onClick={onRetry}
        style={{
          marginTop: '16px', width: '100%',
          padding: '10px', borderRadius: '10px',
          background: 'var(--admin-card)', border: '1px solid var(--admin-border)',
          color: 'var(--admin-text)', cursor: 'pointer', fontSize: '13px', fontWeight: 600,
          display: 'flex', alignItems: 'center', gap: '6px', justifyContent: 'center',
        }}
      >
        <RefreshCw size={14} /> Yana 3 ta variant tayyorlash
      </button>
    </div>
  );
};

export default BroadcastAIWizard;
