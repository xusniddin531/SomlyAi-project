import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { 
  Users, CreditCard, Tags, Bell, Download, Trash2, 
  BookOpen, MessageCircle, Globe, ChevronRight, X, 
  FileText, Shield, Check, Lock, Sun, Moon
} from 'lucide-react';
import { getUserId, fetchApi } from '../utils/api';
import { useTranslation } from 'react-i18next';
import PageHeader from '../components/PageHeader';

const ProfilePage = ({ initData }) => {
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  
  const [activeModal, setActiveModal] = useState(null);
  const [showAlert, setShowAlert] = useState('');
  
  const [notifications, setNotifications] = useState({ morning: true, evening: false });
  const [language, setLanguage] = useState("uz"); 

  const tgUser = window.Telegram?.WebApp?.initDataUnsafe?.user || {};
  const userName = tgUser.first_name || 'Foydalanuvchi';
  const username = tgUser.username ? `@${tgUser.username}` : '';
  const initials = userName.substring(0, 2).toUpperCase();

  const [balances, setBalances] = useState([]);
  const [exportForm, setExportForm] = useState({ balance: 'all', startDate: '', endDate: '' });
  const [clearConsent, setClearConsent] = useState(false);
  const [clearLanguage, setClearLanguage] = useState("uz");
  const [isExporting, setIsExporting] = useState(false);
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [referralStats, setReferralStats] = useState({ invited: 0, registered: 0 });

  useEffect(() => {
    const currentLang = i18n.language || 'uz';
    setLanguage(currentLang);
    setClearLanguage(currentLang);
    
    // Set default dates
    const today = new Date();
    const thirtyDaysAgo = new Date(today);
    thirtyDaysAgo.setDate(today.getDate() - 30);
    setExportForm(prev => ({
      ...prev,
      startDate: thirtyDaysAgo.toISOString().split('T')[0],
      endDate: today.toISOString().split('T')[0]
    }));

    // Fetch balances
    fetchApi('/dashboard').then(res => {
      if (res && res.balances) {
        setBalances(res.balances);
      }
    }).catch(console.error);

    // Fetch referrals
    fetchApi('/referrals').then(res => {
      if (res && !res.error) setReferralStats(res);
    }).catch(console.error);

    const syncThemeState = () => {
      const isLight = document.documentElement.getAttribute('data-theme') === 'light';
      setIsDark(!isLight);
    };
    syncThemeState();
    window.addEventListener('theme_changed', syncThemeState);
    return () => window.removeEventListener('theme_changed', syncThemeState);
  }, [i18n.language]);

  const [isDark, setIsDark] = useState(true);

  const triggerAlert = (msg) => {
    setShowAlert(msg);
    setTimeout(() => setShowAlert(''), 2500);
  };

  const handleChangeLanguage = async (code) => {
    setLanguage(code);
    i18n.changeLanguage(code);
    setActiveModal(null);
    triggerAlert(t('settings.language_changed'));
    
    try {
      await fetchApi('/settings/language', {
        method: 'POST',
        body: JSON.stringify({ user_id: getUserId(), language: code })
      });
    } catch (e) {
      console.error('Failed to sync language to backend', e);
    }
  };

  const handleToggleNotify = async (type) => {
    const newState = !notifications[type];
    setNotifications(prev => ({ ...prev, [type]: newState }));
    
    try {
      await fetch('/api/settings/notifications', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: getUserId(),
          morning_reminder: type === 'morning' ? newState : notifications.morning,
          evening_reminder: type === 'evening' ? newState : notifications.evening
        })
      });
      triggerAlert(t('settings.notification_updated'));
    } catch (e) {
      console.error('Failed to update notifications:', e);
    }
  };

  const handleClearData = async () => {
    setActiveModal(null); 
    localStorage.removeItem('cache_/api/dashboard');
    localStorage.removeItem('cache_/api/transactions');
    try {
      await fetchApi('/clear_data', {
        method: 'POST',
        body: JSON.stringify({ user_id: getUserId(), language: clearLanguage })
      });
    } catch (e) {
      console.error(e);
    }
    triggerAlert('✅ Hisobotlar tozalandi');
    setTimeout(() => {
      navigate('/');
    }, 500);
  };

  const submitExport = async () => {
    setIsExporting(true);
    try {
      await fetchApi('/export', {
         method: 'POST',
         body: JSON.stringify({ 
           user_id: getUserId(), 
           balance: exportForm.balance,
           start_date: exportForm.startDate,
           end_date: exportForm.endDate
         })
      });
      // Mock loading for 1-2 seconds if api is too fast
      await new Promise(resolve => setTimeout(resolve, 1500));
      setActiveModal(null);
      triggerAlert('📊 Hisobotingiz bot orqali yuborildi!');
    } catch (e) {
      console.error(e);
    } finally {
      setIsExporting(false);
    }
  };

  // ── Premium UI Components ──
  const Section = ({ children }) => (
    <div style={{ 
      marginBottom: '24px',
      background: 'var(--card)', 
      borderRadius: 'var(--radius-lg)', 
      border: '1px solid var(--border)',
      boxShadow: '0 4px 20px rgba(0, 0, 0, 0.05)',
      overflow: 'hidden'
    }}>
      {children}
    </div>
  );

  const ActionRow = ({ icon, label, onClick, isLast, color = "var(--text-secondary)", badge = null }) => (
    <div onClick={onClick} style={{ 
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      height: '52px', padding: '0 16px', 
      borderBottom: isLast ? 'none' : '1px solid var(--border)', 
      cursor: badge ? 'default' : 'pointer',
      opacity: badge ? 0.6 : 1,
      transition: 'background-color 0.2s ease'
    }} className="action-row-hover">
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div style={{ color: color, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {icon}
        </div>
        <span style={{ fontSize: '16px', fontWeight: '500', color: 'var(--text-primary)' }}>{label}</span>
      </div>
      {badge ? (
        <div style={{ 
          background: 'var(--border)', color: 'var(--text-secondary)', 
          padding: '4px 8px', borderRadius: '8px', fontSize: '12px', 
          fontWeight: '600', display: 'flex', alignItems: 'center', gap: '4px' 
        }}>
          {badge}
        </div>
      ) : (
        <ChevronRight size={20} color="var(--text-secondary)" opacity={0.5} />
      )}
    </div>
  );

  const Toggle = ({ enabled, onToggle }) => (
    <div onClick={onToggle} style={{ 
      width: '52px', height: '32px', borderRadius: '16px', 
      background: enabled ? '#34C759' : '#3A3A3C', 
      position: 'relative', cursor: 'pointer', 
      transition: 'background 0.3s ease',
      flexShrink: 0
    }}>
      <div style={{ 
        width: '28px', height: '28px', borderRadius: '14px', 
        background: '#FFF', position: 'absolute', top: '2px', 
        left: enabled ? '22px' : '2px', 
        transition: 'left 0.3s cubic-bezier(0.4, 0, 0.2, 1)', 
        boxShadow: '0 2px 8px rgba(0,0,0,0.15)' 
      }} />
    </div>
  );

  // ── Modal wrapper ──
  const ModalOverlay = ({ children, onClose }) => createPortal(
    <div className="modal-overlay" onClick={onClose} 
      style={{ backdropFilter: 'blur(12px)', background: 'rgba(0,0,0,0.5)', zIndex: 9999 }}>
      <div className="modal-content animate-fade-in" onClick={e => e.stopPropagation()} 
        style={{ 
          background: 'var(--card-solid)', borderRadius: '28px', 
          border: '1px solid var(--border)', padding: '24px',
          maxHeight: '88vh', overflowY: 'auto',
          boxShadow: '0 -10px 40px rgba(0,0,0,0.2)'
        }}>
        {children}
      </div>
    </div>,
    document.body
  );

  const ModalHeader = ({ title, onClose }) => (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
      <h3 style={{ fontSize: '20px', fontWeight: '700', letterSpacing: '-0.3px', color: 'var(--text-primary)' }}>{title}</h3>
      <button onClick={onClose} style={{ 
        background: 'var(--border)', border: 'none', color: 'var(--text-primary)', 
        width: '32px', height: '32px', borderRadius: '16px', 
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        cursor: 'pointer'
      }}><X size={16}/></button>
    </div>
  );

  return (
    <div className="animate-fade-in" style={{ paddingBottom: '100px', padding: '0 16px 100px', paddingTop: '16px' }}>
      <PageHeader title={userName ? "Profil" : "Profil"} showLogo={true} showBack={true} />

      {/* Alert Toast */}
      {showAlert && (
        <div style={{ 
          position: 'fixed', top: '16px', left: '50%', transform: 'translateX(-50%)', 
          background: 'rgba(48, 209, 88, 0.95)', backdropFilter: 'blur(12px)',
          color: '#FFF', padding: '12px 24px', borderRadius: '28px', zIndex: 100, 
          fontWeight: '600', fontSize: '14px',
          boxShadow: '0 8px 32px rgba(48,209,88,0.25)', 
          animation: 'slideDown 0.3s ease-out' 
        }}>
          {showAlert}
        </div>
      )}

      {/* ── TOP PROFILE SECTION ── */}
      <div style={{ 
        textAlign: 'center', padding: '32px 0 32px', 
        display: 'flex', flexDirection: 'column', alignItems: 'center' 
      }}>
        {tgUser.photo_url ? (
          <img src={tgUser.photo_url} alt="Profile" style={{
            width: '80px', height: '80px', borderRadius: '40px', marginBottom: '16px',
            objectFit: 'cover', border: '2px solid var(--border)'
          }} />
        ) : (
          <div style={{ 
            width: '80px', height: '80px', borderRadius: '40px', marginBottom: '16px',
            background: 'linear-gradient(135deg, var(--primary) 0%, #5AC8FA 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '32px', fontWeight: '700', color: '#FFF',
            border: '2px solid var(--border)'
          }}>
            {initials}
          </div>
        )}
        <h1 style={{ fontSize: '18px', fontWeight: '700', margin: '0 0 4px', letterSpacing: '-0.3px', color: 'var(--text-primary)' }}>
          {userName}
        </h1>
        {username && (
          <p style={{ fontSize: '14px', color: 'var(--text-secondary)', margin: 0 }}>
            {username}
          </p>
        )}
      </div>

      {/* ── MENU SECTIONS ── */}
      
      {/* 1-GURUH */}
      <Section>
        <ActionRow icon={<Users size={20}/>} label="Telegram guruh" color="#32ADE6" onClick={() => navigate('/group')} />
        <ActionRow icon={<CreditCard size={20}/>} label={t('settings.balances')} color="#34C759" onClick={() => navigate('/balances')} />
        <ActionRow icon={<Tags size={20}/>} label={t('settings.categories')} color="#FF9F0A" onClick={() => navigate('/categories')} />
        <ActionRow icon={<Users size={20}/>} label="Do'stlar" color="#BF5AF2" onClick={() => setActiveModal('referrals')} />
        <ActionRow icon={<Bell size={20}/>} label={t('settings.notifications')} color="#FF453A" onClick={() => setActiveModal('notify')} isLast />
      </Section>

      {/* 2-GURUH */}
      <Section>
        <ActionRow icon={<Download size={20}/>} label={t('settings.download_report')} color="#0A84FF" onClick={() => setActiveModal('export')} />
        <ActionRow icon={<Trash2 size={20}/>} label={t('settings.clear_data')} color="#FF453A" onClick={() => setActiveModal('clear')} isLast />
      </Section>

      {/* 3-GURUH */}
      <Section>
        <ActionRow icon={isDark ? <Sun size={20}/> : <Moon size={20}/>} label={isDark ? "Light Mode" : "Dark Mode"} color={isDark ? "#FFD60A" : "#000000"} onClick={() => window.dispatchEvent(new Event('theme_toggle'))} />
        <ActionRow icon={<BookOpen size={20}/>} label={t('settings.user_guide')} color="#5AC8FA" onClick={() => setActiveModal('guide')} />
        <ActionRow icon={<MessageCircle size={20}/>} label={t('settings.support')} color="#34C759" onClick={() => window.Telegram?.WebApp?.openTelegramLink('https://t.me/+4nDGoZ0Bfi4xYjZi') || window.open('https://t.me/+4nDGoZ0Bfi4xYjZi', '_blank')} />
        <ActionRow icon={<Globe size={20}/>} label={t('settings.change_language')} color="#0A84FF" onClick={() => setActiveModal('lang')} isLast />
      </Section>

      {/* 4-GURUH */}
      <Section>
        <ActionRow icon={<FileText size={20}/>} label={t('settings.terms')} color="#8E8E93" onClick={() => navigate('/terms')} />
        <ActionRow icon={<Shield size={20}/>} label={t('settings.privacy')} color="#8E8E93" onClick={() => navigate('/privacy')} isLast />
      </Section>

      {/* ════════════════════════════════════
         MODALS
         ════════════════════════════════════ */}

      {/* Notifications */}
      {activeModal === 'notify' && (
        <ModalOverlay onClose={() => setActiveModal(null)}>
          <ModalHeader title={t('settings.notifications')} onClose={() => setActiveModal(null)} />
          
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px', background: 'var(--card)', borderRadius: '16px', marginBottom: '12px', border: '1px solid var(--border)', boxShadow: '0 4px 12px rgba(0,0,0,0.03)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
              <div style={{ fontSize: '22px' }}>🌅</div>
              <div>
                <p style={{ fontWeight: '600', fontSize: '15px', color: 'var(--text-primary)', marginBottom: '2px' }}>{t('settings.morning_reminder')}</p>
                <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{t('settings.morning_time')}</p>
              </div>
            </div>
            <Toggle enabled={notifications.morning} onToggle={() => handleToggleNotify('morning')} />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px', background: 'var(--card)', borderRadius: '16px', border: '1px solid var(--border)', boxShadow: '0 4px 12px rgba(0,0,0,0.03)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
              <div style={{ fontSize: '22px' }}>🌙</div>
              <div>
                <p style={{ fontWeight: '600', fontSize: '15px', color: 'var(--text-primary)', marginBottom: '2px' }}>{t('settings.evening_reminder')}</p>
                <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{t('settings.evening_time')}</p>
              </div>
            </div>
            <Toggle enabled={notifications.evening} onToggle={() => handleToggleNotify('evening')} />
          </div>
        </ModalOverlay>
      )}

      {/* Export */}
      {activeModal === 'export' && (
        <ModalOverlay onClose={() => setActiveModal(null)}>
          <ModalHeader title="Excel yuklab olish" onClose={() => setActiveModal(null)} />
          
          <div style={{ marginBottom: '20px' }}>
            <label style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '8px', display: 'block', fontWeight: '500' }}>Balans</label>
            <select 
              value={exportForm.balance} 
              onChange={e => setExportForm({...exportForm, balance: e.target.value})}
              style={{ width: '100%', background: 'var(--card)', border: '1px solid var(--border)', color: 'var(--text-primary)', padding: '14px', borderRadius: '14px', fontSize: '15px', outline: 'none', appearance: 'none', WebkitAppearance: 'none' }}
            >
              <option value="all" style={{ background: 'var(--card-solid)', color: 'var(--text-primary)' }}>Barcha balanslar</option>
              {balances.map(b => (
                <option key={b.currency} value={b.currency} style={{ background: 'var(--card-solid)', color: 'var(--text-primary)' }}>
                  {b.title || b.currency} ({b.currency})
                </option>
              ))}
            </select>
            <div style={{ position: 'relative', top: '-34px', left: 'calc(100% - 30px)', pointerEvents: 'none' }}>
              <ChevronRight size={18} color="var(--text-secondary)" style={{ transform: 'rotate(90deg)' }} />
            </div>
          </div>

          <div style={{ marginBottom: '32px' }}>
            <label style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '8px', display: 'block', fontWeight: '500' }}>Davr</label>
            <button 
              onClick={() => setShowDatePicker(true)}
              style={{ width: '100%', background: 'var(--card)', border: '1px solid var(--border)', color: 'var(--text-primary)', padding: '14px', borderRadius: '14px', fontSize: '15px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
            >
              <span>{exportForm.startDate ? new Date(exportForm.startDate).toLocaleDateString('uz-UZ') : 'Boshlang\'ich'} – {exportForm.endDate ? new Date(exportForm.endDate).toLocaleDateString('uz-UZ') : 'Yakuniy'}</span>
              <ChevronRight size={18} color="var(--text-secondary)" style={{ transform: 'rotate(90deg)' }} />
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <button 
              onClick={() => setExportForm({ balance: 'all', startDate: '', endDate: '' })} 
              style={{ background: 'transparent', border: 'none', color: '#0A84FF', fontSize: '15px', fontWeight: '600', cursor: 'pointer', padding: '8px' }}
            >
              Belgilanganlarni o'chirish
            </button>
            <button 
              onClick={submitExport} 
              disabled={isExporting}
              style={{ width: '100%', padding: '16px', background: 'var(--primary)', color: '#FFF', border: 'none', borderRadius: '14px', fontSize: '15px', fontWeight: '600', cursor: isExporting ? 'default' : 'pointer', display: 'flex', justifyContent: 'center', alignItems: 'center', boxShadow: '0 8px 24px var(--primary-glow)' }}
            >
              {isExporting ? <span className="spin-animation">⏳</span> : 'Hisobotni yuklab olish'}
            </button>
          </div>
        </ModalOverlay>
      )}

      {/* Date Picker Modal */}
      {showDatePicker && (
        <ModalOverlay onClose={() => setShowDatePicker(false)}>
          <ModalHeader title="Davrni tanlang" onClose={() => setShowDatePicker(false)} />
          
          <div style={{ display: 'flex', gap: '12px', marginBottom: '24px' }}>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: '12px', color: 'var(--text-secondary)', display: 'block', marginBottom: '6px' }}>Boshlang'ich</label>
              <input 
                type="date" 
                value={exportForm.startDate} 
                onChange={e => setExportForm({...exportForm, startDate: e.target.value})}
                style={{ width: '100%', background: 'var(--card)', border: '1px solid var(--border)', color: 'var(--text-primary)', padding: '12px', borderRadius: '12px', fontSize: '14px', outline: 'none' }} 
              />
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: '12px', color: 'var(--text-secondary)', display: 'block', marginBottom: '6px' }}>Yakuniy</label>
              <input 
                type="date" 
                value={exportForm.endDate} 
                onChange={e => setExportForm({...exportForm, endDate: e.target.value})}
                style={{ width: '100%', background: 'var(--card)', border: '1px solid var(--border)', color: 'var(--text-primary)', padding: '12px', borderRadius: '12px', fontSize: '14px', outline: 'none' }} 
              />
            </div>
          </div>

          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '12px', fontWeight: '500' }}>Tezkor</p>
          <div style={{ display: 'flex', gap: '8px', marginBottom: '24px', overflowX: 'auto', paddingBottom: '4px' }}>
            <button 
              onClick={() => {
                const d = new Date().toISOString().split('T')[0];
                setExportForm({...exportForm, startDate: d, endDate: d});
              }}
              style={{ padding: '8px 16px', background: 'rgba(255,255,255,0.08)', border: 'none', borderRadius: '16px', color: '#fff', fontSize: '13px', whiteSpace: 'nowrap' }}
            >Bugungi kun</button>
            <button 
              onClick={() => {
                const today = new Date();
                const lastWeek = new Date(today);
                lastWeek.setDate(today.getDate() - 7);
                setExportForm({...exportForm, startDate: lastWeek.toISOString().split('T')[0], endDate: today.toISOString().split('T')[0]});
              }}
              style={{ padding: '8px 16px', background: 'rgba(255,255,255,0.08)', border: 'none', borderRadius: '16px', color: '#fff', fontSize: '13px', whiteSpace: 'nowrap' }}
            >Hafta</button>
            <button 
              onClick={() => {
                const today = new Date();
                const lastMonth = new Date(today);
                lastMonth.setDate(today.getDate() - 30);
                setExportForm({...exportForm, startDate: lastMonth.toISOString().split('T')[0], endDate: today.toISOString().split('T')[0]});
              }}
              style={{ padding: '8px 16px', background: 'rgba(255,255,255,0.08)', border: 'none', borderRadius: '16px', color: '#fff', fontSize: '13px', whiteSpace: 'nowrap' }}
            >O'tgan oy</button>
          </div>

          <button 
            onClick={() => setShowDatePicker(false)} 
            style={{ width: '100%', padding: '16px', background: 'var(--primary)', color: '#FFF', border: 'none', borderRadius: '14px', fontSize: '15px', fontWeight: '600', boxShadow: '0 8px 24px var(--primary-glow)' }}
          >
            Qo'llash
          </button>
        </ModalOverlay>
      )}

      {/* Clear Data */}
      {activeModal === 'clear' && (
        <ModalOverlay onClose={() => setActiveModal(null)}>
          <h3 style={{ fontSize: '20px', fontWeight: '700', marginBottom: '16px', color: 'var(--text-primary)' }}>Hisobotlarni tozalash</h3>
          
          <p style={{ color: 'var(--text-secondary)', marginBottom: '24px', lineHeight: '1.5', fontSize: '14px' }}>
            Barcha kiritilgan hisobotlar o'chiriladi va hisobotlarni qayta tiklash imkoni bo'lmaydi
          </p>

          <div style={{ marginBottom: '24px' }}>
            <label style={{ fontSize: '13px', color: 'var(--text-secondary)', display: 'block', marginBottom: '8px' }}>Tilni tanlang</label>
            <div style={{ position: 'relative' }}>
              <select 
                value={clearLanguage}
                onChange={e => setClearLanguage(e.target.value)}
                style={{ width: '100%', background: 'var(--card)', border: '1px solid var(--border)', color: 'var(--text-primary)', padding: '14px', borderRadius: '14px', fontSize: '15px', outline: 'none', appearance: 'none' }}
              >
                <option value="uz" style={{ background: 'var(--card-solid)' }}>O'zbek tili</option>
                <option value="ru" style={{ background: 'var(--card-solid)' }}>Rus tili</option>
                <option value="en" style={{ background: 'var(--card-solid)' }}>Ingliz tili</option>
              </select>
              <ChevronRight size={18} color="var(--text-secondary)" style={{ position: 'absolute', right: '14px', top: '14px', transform: 'rotate(90deg)', pointerEvents: 'none' }} />
            </div>
          </div>

          <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '32px', cursor: 'pointer', padding: '12px 16px', background: 'var(--card)', borderRadius: '14px', border: '1px solid var(--border)' }}>
            <span style={{ fontSize: '15px', color: 'var(--text-primary)', fontWeight: '500' }}>Hisobotlarni o'chirilishiga roziman</span>
            <div style={{ 
              width: '52px', height: '32px', borderRadius: '16px', 
              background: clearConsent ? '#34C759' : '#3A3A3C', 
              position: 'relative', transition: 'background 0.3s ease',
              flexShrink: 0
            }}>
              <div style={{ 
                width: '28px', height: '28px', borderRadius: '14px', 
                background: '#FFF', position: 'absolute', top: '2px', 
                left: clearConsent ? '22px' : '2px', 
                transition: 'left 0.3s cubic-bezier(0.4, 0, 0.2, 1)', 
                boxShadow: '0 2px 8px rgba(0,0,0,0.15)' 
              }} />
            </div>
            <input 
              type="checkbox" 
              checked={clearConsent} 
              onChange={e => setClearConsent(e.target.checked)}
              style={{ display: 'none' }} 
            />
          </label>

          <div style={{ display: 'flex', gap: '12px' }}>
            <button onClick={() => { setActiveModal(null); setClearConsent(false); }} style={{ flex: 1, padding: '16px', background: 'var(--bg)', border: 'none', borderRadius: '14px', color: 'var(--text-primary)', fontWeight: '600', fontSize: '15px', cursor: 'pointer' }}>
              Bekor qilish
            </button>
            <button onClick={handleClearData} disabled={!clearConsent} style={{ flex: 1, padding: '16px', background: clearConsent ? 'var(--danger)' : 'rgba(255,69,58,0.3)', border: 'none', borderRadius: '14px', color: 'white', fontWeight: '600', fontSize: '15px', cursor: clearConsent ? 'pointer' : 'default', transition: 'background 0.3s' }}>
              O'chirish 🔴
            </button>
          </div>
        </ModalOverlay>
      )}

      {/* Guide */}
      {activeModal === 'guide' && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'var(--bg)', zIndex: 1000, overflowY: 'auto', padding: '0' }}>
          <div style={{ position: 'sticky', top: 0, background: 'var(--nav-bg)', backdropFilter: 'blur(30px)', padding: '16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border)', zIndex: 10 }}>
            <h3 style={{ fontSize: '20px', fontWeight: '700', margin: 0, color: 'var(--text-primary)' }}>Foydalanish yo'riqnomasi</h3>
            <button onClick={() => setActiveModal(null)} style={{ background: 'var(--border)', border: 'none', color: 'var(--text-primary)', width: '32px', height: '32px', borderRadius: '16px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}><X size={16}/></button>
          </div>
          
          <div style={{ padding: '24px 16px 40px', lineHeight: '1.6', fontSize: '15px', color: 'var(--text-secondary)' }}>
            <p style={{ marginBottom: '24px', fontSize: '16px', color: 'var(--text-primary)', fontWeight: '500' }}>
              Somly AI — zamonaviy sun'iy intellekt asosidagi shaxsiy moliyaviy yordamchi.
            </p>

            <h4 style={{ color: 'var(--primary)', fontSize: '16px', fontWeight: '700', marginBottom: '12px', marginTop: '24px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>📌</span> BOSHLASH:
            </h4>
            <div style={{ background: 'var(--card)', padding: '16px', borderRadius: '16px', border: '1px solid var(--border)' }}>
              <ul style={{ margin: 0, paddingLeft: '20px' }}>
                <li style={{ marginBottom: '8px' }}>Bot @SomlyAI_bot ga /start yuboring.</li>
                <li style={{ marginBottom: '8px' }}>Telefon raqamingizni ulang.</li>
                <li>Tilni tanlang va foydalanishni boshlang.</li>
              </ul>
            </div>

            <h4 style={{ color: 'var(--success)', fontSize: '16px', fontWeight: '700', marginBottom: '12px', marginTop: '32px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>💸</span> XARAJAT KIRITISH:
            </h4>
            <div style={{ background: 'var(--card)', padding: '16px', borderRadius: '16px', border: '1px solid var(--border)' }}>
              <p style={{ marginBottom: '12px' }}>Shunchaki botga yozing yoki ovoz yuboring:</p>
              <ul style={{ margin: 0, paddingLeft: '20px', marginBottom: '12px', color: 'var(--text-primary)' }}>
                <li style={{ marginBottom: '6px' }}>"Taksiga 15,000 so'm sarfladim"</li>
                <li style={{ marginBottom: '6px' }}>"Oziq-ovqatga 200 ming ketdi"</li>
                <li style={{ marginBottom: '6px' }}>"Oylik maoshim 4 million tushdi"</li>
                <li>"Jasurga 100 ming qarz berdim"</li>
              </ul>
              <p style={{ margin: 0, color: 'var(--text-secondary)' }}>AI o'zi tushunadi va saqlaydi.</p>
            </div>

            <h4 style={{ color: 'var(--warning)', fontSize: '16px', fontWeight: '700', marginBottom: '12px', marginTop: '32px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>📊</span> HISOBOTLAR:
            </h4>
            <div style={{ background: 'var(--card)', padding: '16px', borderRadius: '16px', border: '1px solid var(--border)' }}>
              <ul style={{ margin: 0, paddingLeft: '20px' }}>
                <li style={{ marginBottom: '8px' }}>Mini App orqali barcha tranzaksiyalaringizni ko'ring.</li>
                <li style={{ marginBottom: '8px' }}>Kunlik, haftalik, oylik statistika.</li>
                <li>Excel formatda yuklab oling.</li>
              </ul>
            </div>

            <h4 style={{ color: '#BF5AF2', fontSize: '16px', fontWeight: '700', marginBottom: '12px', marginTop: '32px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>💡</span> AFZALLIKLARI:
            </h4>
            <div style={{ background: 'var(--card)', padding: '16px', borderRadius: '16px', border: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div style={{ display: 'flex', gap: '8px' }}><span style={{ color: 'var(--success)' }}>✅</span> Mutlaqo bepul</div>
              <div style={{ display: 'flex', gap: '8px' }}><span style={{ color: 'var(--success)' }}>✅</span> Ovoz va matn orqali kiritish</div>
              <div style={{ display: 'flex', gap: '8px' }}><span style={{ color: 'var(--success)' }}>✅</span> Avtomatik kategoriyalash</div>
              <div style={{ display: 'flex', gap: '8px' }}><span style={{ color: 'var(--success)' }}>✅</span> Qarz nazorati</div>
              <div style={{ display: 'flex', gap: '8px' }}><span style={{ color: 'var(--success)' }}>✅</span> Ko'p valyuta qo'llab-quvvatlash</div>
              <div style={{ display: 'flex', gap: '8px' }}><span style={{ color: 'var(--success)' }}>✅</span> Oila va jamoa uchun guruh rejimi</div>
            </div>

            <div style={{ textAlign: 'center', marginTop: '40px', padding: '24px', background: 'linear-gradient(135deg, var(--primary-glow) 0%, rgba(90,200,250,0.1) 100%)', borderRadius: '16px', border: '1px solid rgba(10,132,255,0.2)' }}>
              <p style={{ margin: 0, fontSize: '16px', fontWeight: '600', color: 'var(--text-primary)' }}>
                Somly AI — pulini nazorat qilmoqchi bo'lgan har bir inson uchun.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Language */}
      {activeModal === 'lang' && (
        <ModalOverlay onClose={() => setActiveModal(null)}>
          <ModalHeader title="Tilni o'zgartirish" onClose={() => setActiveModal(null)} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {[
              { code: 'uz', label: "O'zbek tili", flag: '🇺🇿' },
              { code: 'ru', label: 'Rus tili', flag: '🇷🇺' },
              { code: 'en', label: 'Ingliz tili', flag: '🇬🇧' }
            ].map(lang => (
              <label 
                key={lang.code} 
                style={{ 
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  width: '100%', padding: '16px 18px', 
                  background: 'var(--card)', 
                  border: '1px solid var(--border)', 
                  borderRadius: '14px', color: 'var(--text-primary)', fontWeight: '600', fontSize: '15px',
                  cursor: 'pointer'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                  <span style={{ fontSize: '22px' }}>{lang.flag}</span>
                  <span>{lang.label}</span>
                </div>
                <div style={{ 
                  width: '24px', height: '24px', borderRadius: '12px', 
                  border: language === lang.code ? '7px solid var(--primary)' : '2px solid var(--border)',
                  background: 'transparent', transition: 'all 0.2s'
                }} />
                <input 
                  type="radio" 
                  name="language" 
                  value={lang.code} 
                  checked={language === lang.code}
                  onChange={() => handleChangeLanguage(lang.code)} 
                  style={{ display: 'none' }}
                />
              </label>
            ))}
          </div>
        </ModalOverlay>
      )}

      {/* Referrals (Friends) */}
      {activeModal === 'referrals' && (
        <ModalOverlay onClose={() => setActiveModal(null)}>
          <ModalHeader title="Do'stlarni taklif qilish" onClose={() => setActiveModal(null)} />
          
          <div style={{ textAlign: 'center', marginBottom: '24px' }}>
            <div style={{ 
              width: '80px', height: '80px', borderRadius: '40px', background: 'rgba(191, 90, 242, 0.1)', 
              display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px', color: '#BF5AF2' 
            }}>
              <Users size={40} />
            </div>
            <h3 style={{ fontSize: '18px', fontWeight: '700', color: 'var(--text-primary)', marginBottom: '8px' }}>Do'stlaringizni taklif qiling!</h3>
            <p style={{ fontSize: '14px', color: 'var(--text-secondary)', lineHeight: '1.5' }}>
              Somly AI haqida do'stlaringizga ayting va birgalikda moliyaviy barqarorlikka erishing.
            </p>
          </div>

          <div style={{ background: 'var(--card)', borderRadius: '16px', padding: '16px', marginBottom: '24px', border: '1px solid var(--border)' }}>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '8px', fontWeight: '500' }}>Sizning taklif havolangiz</p>
            <div style={{ display: 'flex', gap: '8px' }}>
              <input 
                type="text" 
                readOnly 
                value={`https://t.me/Somly_ai_bot?start=ref_${getUserId()}`}
                style={{ 
                  flex: 1, background: 'var(--bg)', border: '1px solid var(--border)', 
                  color: 'var(--text-primary)', padding: '12px', borderRadius: '12px', fontSize: '14px', outline: 'none' 
                }} 
              />
            </div>
            <div style={{ display: 'flex', gap: '12px', marginTop: '12px' }}>
              <button 
                onClick={() => {
                  navigator.clipboard.writeText(`https://t.me/Somly_ai_bot?start=ref_${getUserId()}`);
                  triggerAlert('✅ Havola nusxalandi');
                }}
                style={{ flex: 1, padding: '12px', background: 'var(--border)', color: 'var(--text-primary)', border: 'none', borderRadius: '12px', fontSize: '14px', fontWeight: '600', cursor: 'pointer' }}
              >
                📋 Nusxalash
              </button>
              <button 
                onClick={() => {
                  const text = encodeURIComponent(`Somly AI — bepul moliyaviy yordamchi!\nPul kirim-chiqimingizni ovoz yoki matn orqali kuzating. Mutlaqo tekin 💰\n👉 https://t.me/Somly_ai_bot?start=ref_${getUserId()}`);
                  window.Telegram?.WebApp?.openTelegramLink(`https://t.me/share/url?url=&text=${text}`);
                }}
                style={{ flex: 1, padding: '12px', background: '#BF5AF2', color: '#FFF', border: 'none', borderRadius: '12px', fontSize: '14px', fontWeight: '600', cursor: 'pointer' }}
              >
                📤 Ulashish
              </button>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '12px' }}>
            <div style={{ flex: 1, background: 'var(--card)', padding: '16px', borderRadius: '16px', border: '1px solid var(--border)', textAlign: 'center' }}>
              <p style={{ fontSize: '24px', fontWeight: '700', color: 'var(--text-primary)', margin: '0 0 4px 0' }}>{referralStats.invited}</p>
              <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: 0 }}>Taklif qilganlar</p>
            </div>
            <div style={{ flex: 1, background: 'var(--card)', padding: '16px', borderRadius: '16px', border: '1px solid var(--border)', textAlign: 'center' }}>
              <p style={{ fontSize: '24px', fontWeight: '700', color: 'var(--success)', margin: '0 0 4px 0' }}>{referralStats.registered}</p>
              <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: 0 }}>Ro'yxatdan o'tganlar</p>
            </div>
          </div>
        </ModalOverlay>
      )}

    </div>
  );
};

export default ProfilePage;
