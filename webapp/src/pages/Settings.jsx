import React, { useState } from 'react';
import { Settings as SettingsIcon, Globe, Moon, Sun, Trash2, Shield, Download, ChevronRight, Check } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { fetchApi, getUserId } from '../utils/api';
import PageHeader from '../components/PageHeader';

const SettingsPage = ({ initData }) => {
  const { t, i18n } = useTranslation();
  const [activeTab, setActiveTab] = useState('general'); // general, data
  const [theme, setTheme] = useState('dark');
  const [showAlert, setShowAlert] = useState('');

  const triggerAlert = (msg) => {
    setShowAlert(msg);
    setTimeout(() => setShowAlert(''), 3000);
  };

  const changeLanguage = async (code) => {
    i18n.changeLanguage(code);
    triggerAlert(`Til o'zgartirildi: ${code.toUpperCase()}`);
    try {
      await fetchApi('/settings/language', {
        method: 'POST',
        body: JSON.stringify({ user_id: getUserId(), language: code })
      });
    } catch (e) {
      console.error(e);
    }
  };

  const toggleTheme = () => {
    const newTheme = theme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);
    triggerAlert(`Mavzu o'zgartirildi: ${newTheme}`);
    // In a real app, apply this to document body or context
  };

  const handleClearData = async () => {
    if (window.confirm("Barcha ma'lumotlaringiz o'chiriladi. Ishonchingiz komilmi?")) {
      try {
        await fetchApi('/settings/clear', {
          method: 'POST',
          body: JSON.stringify({ user_id: getUserId() })
        });
        triggerAlert("Ma'lumotlar tozalandi!");
      } catch (e) {
        console.error(e);
      }
    }
  };

  return (
    <div className="page-container" style={{ padding: '20px', paddingBottom: '100px' }}>
      {showAlert && (
        <div style={{
          position: 'fixed', top: '20px', left: '50%', transform: 'translateX(-50%)',
          background: 'rgba(16, 185, 129, 0.9)', color: '#fff', padding: '10px 20px',
          borderRadius: '20px', fontSize: '14px', fontWeight: 600, zIndex: 9999,
          backdropFilter: 'blur(10px)', boxShadow: '0 4px 12px rgba(0,0,0,0.1)'
        }}>
          <Check size={16} style={{ display: 'inline', marginRight: '6px', verticalAlign: '-3px' }}/>
          {showAlert}
        </div>
      )}

      <header style={{ marginBottom: '24px' }}>
        <PageHeader title="Sozlamalar" showLogo={true} />
        <p style={{ color: 'var(--text-secondary)', fontSize: '15px' }}>
          Ilovani o'zingizga moslashtiring
        </p>
      </header>

      {/* Tabs */}
      <div style={{ display: 'flex', background: 'rgba(255,255,255,0.05)', borderRadius: '12px', padding: '4px', marginBottom: '24px' }}>
        <button onClick={() => setActiveTab('general')} style={{ flex: 1, padding: '10px', borderRadius: '10px', border: 'none', background: activeTab === 'general' ? 'var(--primary)' : 'transparent', color: activeTab === 'general' ? '#fff' : 'var(--text-secondary)', fontWeight: 600, transition: '0.3s' }}>
          Umumiy
        </button>
        <button onClick={() => setActiveTab('data')} style={{ flex: 1, padding: '10px', borderRadius: '10px', border: 'none', background: activeTab === 'data' ? 'var(--primary)' : 'transparent', color: activeTab === 'data' ? '#fff' : 'var(--text-secondary)', fontWeight: 600, transition: '0.3s' }}>
          Ma'lumotlar
        </button>
      </div>

      {activeTab === 'general' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Language Selection */}
          <div className="glass-card" style={{ padding: '20px', borderRadius: '20px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Globe size={18} className="text-primary" />
              Tilni tanlang
            </h3>
            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
              {[{ code: 'uz', label: 'O\'zbek' }, { code: 'ru', label: 'Русский' }, { code: 'en', label: 'English' }].map(lang => (
                <button
                  key={lang.code}
                  onClick={() => changeLanguage(lang.code)}
                  style={{
                    flex: '1 1 calc(33% - 10px)', padding: '12px', borderRadius: '12px',
                    border: i18n.language === lang.code ? '1px solid var(--primary)' : '1px solid var(--border)',
                    background: i18n.language === lang.code ? 'rgba(59, 130, 246, 0.15)' : 'var(--bg)',
                    color: i18n.language === lang.code ? 'var(--primary)' : 'var(--text-primary)',
                    fontWeight: 600, cursor: 'pointer', transition: 'all 0.2s'
                  }}
                >
                  {lang.label}
                </button>
              ))}
            </div>
          </div>

          {/* Theme Selection */}
          <div className="glass-card" style={{ padding: '20px', borderRadius: '20px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              {theme === 'dark' ? <Moon size={18} className="text-primary" /> : <Sun size={18} className="text-primary" />}
              Mavzu
            </h3>
            <div 
              onClick={toggleTheme}
              style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '16px', background: 'rgba(255,255,255,0.03)', borderRadius: '12px', cursor: 'pointer', border: '1px solid rgba(255,255,255,0.05)'
              }}>
              <span style={{ fontWeight: 500, color: '#fff' }}>Hozirgi: {theme === 'dark' ? 'Qorong\'i (Dark)' : 'Yorug\' (Light)'}</span>
              <ChevronRight size={18} color="var(--text-secondary)" />
            </div>
          </div>
        </div>
      )}

      {activeTab === 'data' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Data Export */}
          <div className="glass-card" style={{ padding: '20px', borderRadius: '20px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Download size={18} className="text-primary" />
              Ma'lumotlarni yuklab olish
            </h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginBottom: '16px' }}>
              Barcha tranzaksiyalaringizni va hisobotlaringizni Excel (.xlsx) formatida yuklab oling.
            </p>
            <button 
              onClick={() => triggerAlert("Eksport tayyorlanmoqda. Iltimos kuting...")}
              style={{
                width: '100%', padding: '14px', borderRadius: '12px', border: 'none',
                background: 'var(--primary)', color: '#fff', fontWeight: 600, fontSize: '15px', cursor: 'pointer'
              }}>
              Hozir yuklab olish
            </button>
          </div>

          {/* Danger Zone */}
          <div className="glass-card" style={{ padding: '20px', borderRadius: '20px', border: '1px solid rgba(239, 68, 68, 0.2)' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--danger)' }}>
              <Shield size={18} />
              Xavfli Hudud
            </h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginBottom: '16px' }}>
              Hisobingizdagi barcha ma'lumotlarni, shu jumladan balans, tranzaksiyalar va qarzlarni butunlay o'chirish. Bu amalni ortga qaytarib bo'lmaydi!
            </p>
            <button 
              onClick={handleClearData}
              style={{
                width: '100%', padding: '14px', borderRadius: '12px', border: 'none',
                background: 'rgba(239, 68, 68, 0.1)', color: 'var(--danger)', fontWeight: 600, fontSize: '15px', cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px'
              }}>
              <Trash2 size={18} />
              Barcha ma'lumotlarni o'chirish
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default SettingsPage;
