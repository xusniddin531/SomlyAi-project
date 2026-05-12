import React, { useState, useEffect } from 'react';
import { Settings, Lock, Clock, Bot, Cpu, Sun, Moon, Save, RefreshCw, Heart, Info } from 'lucide-react';

const AdminSettings = ({ token, onThemeToggle, isDark }) => {
  const [settings, setSettings] = useState(null);
  const [groqKeys, setGroqKeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  // PIN change
  const [showPinModal, setShowPinModal] = useState(false);
  const [oldPin, setOldPin] = useState('');
  const [newPin, setNewPin] = useState('');
  const [pinError, setPinError] = useState('');
  const [pinSuccess, setPinSuccess] = useState(false);

  useEffect(() => {
    fetchAll();
  }, []);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [settingsRes, groqRes] = await Promise.all([
        fetch('/api/admin/settings', { headers: { Authorization: `Bearer ${token}` } }),
        fetch('/api/admin/groq-status', { headers: { Authorization: `Bearer ${token}` } })
      ]);
      if (settingsRes.ok) setSettings(await settingsRes.json());
      if (groqRes.ok) {
        const g = await groqRes.json();
        setGroqKeys(g.keys || []);
      }
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch('/api/admin/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(settings)
      });
      if (res.ok) {
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      }
    } catch (e) {
      console.error(e);
    }
    setSaving(false);
  };

  const handlePinChange = async () => {
    setPinError('');
    setPinSuccess(false);
    try {
      const res = await fetch('/api/admin/pin-change', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ old_pin: oldPin, new_pin: newPin })
      });
      const data = await res.json();
      if (data.success) {
        setPinSuccess(true);
        setOldPin('');
        setNewPin('');
        setTimeout(() => { setShowPinModal(false); setPinSuccess(false); }, 1500);
      } else {
        setPinError(data.error || "Xatolik");
      }
    } catch (e) {
      setPinError("Tarmoq xatosi");
    }
  };

  const updateSetting = (key, value) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  if (loading || !settings) {
    return (
      <div className="admin-page">
        <h1 className="page-title">⚙️ Sozlamalar</h1>
        <div className="skeleton-row mt20" style={{ height: '200px' }}></div>
        <div className="skeleton-row" style={{ height: '200px' }}></div>
      </div>
    );
  }

  return (
    <div className="admin-page fade-in">
      <div className="detail-header">
        <h1 className="page-title">⚙️ Sozlamalar</h1>
        <button className={`btn-primary ${saved ? 'btn-success-state' : ''}`} onClick={handleSave} disabled={saving}>
          {saved ? <><RefreshCw size={16} className="spin" /> Saqlandi!</> : <><Save size={16} /> Saqlash</>}
        </button>
      </div>

      <div className="settings-grid">

        {/* PIN KOD */}
        <div className="card settings-card">
          <div className="settings-card-header">
            <Lock size={20} color="#ef4444" />
            <h3>PIN Kod</h3>
          </div>
          <div className="settings-card-body">
            <p className="settings-desc">Joriy PIN: ****</p>
            <button className="btn-outline" onClick={() => setShowPinModal(true)}>
              🔐 PIN o'zgartirish
            </button>
          </div>
        </div>

        {/* BOT SOZLAMALARI */}
        <div className="card settings-card">
          <div className="settings-card-header">
            <Bot size={20} color="#6366f1" />
            <h3>Bot sozlamalari</h3>
          </div>
          <div className="settings-card-body">
            <div className="settings-row">
              <span className="settings-label">Bot nomi</span>
              <span className="settings-value">Somly AI</span>
            </div>
            <div className="settings-row">
              <span className="settings-label">Bot username</span>
              <span className="settings-value">@Somly_ai_bot</span>
            </div>
          </div>
        </div>

        {/* ESLATMA VAQTLARI */}
        <div className="card settings-card">
          <div className="settings-card-header">
            <Clock size={20} color="#f59e0b" />
            <h3>Eslatma vaqtlari</h3>
          </div>
          <div className="settings-card-body">
            <div className="settings-row">
              <span className="settings-label">Ertalabgi eslatma</span>
              <input type="time" value={settings.morning_reminder || "09:00"} 
                onChange={e => updateSetting("morning_reminder", e.target.value)} className="settings-input" />
            </div>
            <div className="settings-row">
              <span className="settings-label">Kunduzgi eslatma</span>
              <input type="time" value={settings.afternoon_reminder || "15:00"} 
                onChange={e => updateSetting("afternoon_reminder", e.target.value)} className="settings-input" />
            </div>
            <div className="settings-row">
              <span className="settings-label">Kechki eslatma</span>
              <input type="time" value={settings.evening_reminder || "21:00"} 
                onChange={e => updateSetting("evening_reminder", e.target.value)} className="settings-input" />
            </div>
            <div className="settings-row">
              <span className="settings-label">Oylik xulosa</span>
              <div className="settings-combo">
                <input type="number" min="1" max="28" value={settings.monthly_summary_day || 1} 
                  onChange={e => updateSetting("monthly_summary_day", parseInt(e.target.value))} className="settings-input small" />
                <span>-kun,</span>
                <input type="time" value={settings.monthly_summary_time || "09:00"} 
                  onChange={e => updateSetting("monthly_summary_time", e.target.value)} className="settings-input" />
              </div>
            </div>
          </div>
        </div>

        {/* SEGMENT SAVOL ORALIG'I */}
        <div className="card settings-card">
          <div className="settings-card-header">
            <Settings size={20} color="#10b981" />
            <h3>Segment savol oralig'i</h3>
          </div>
          <div className="settings-card-body">
            <div className="settings-row">
              <span className="settings-label">Min (soat)</span>
              <input type="number" min="1" max="24" value={settings.segment_min_hours || 1} 
                onChange={e => updateSetting("segment_min_hours", parseInt(e.target.value))} className="settings-input small" />
            </div>
            <div className="settings-row">
              <span className="settings-label">Max (soat)</span>
              <input type="number" min="1" max="24" value={settings.segment_max_hours || 4} 
                onChange={e => updateSetting("segment_max_hours", parseInt(e.target.value))} className="settings-input small" />
            </div>
            <p className="settings-hint">Random oraliqda savol yuboriladi</p>
          </div>
        </div>

        {/* QIZIQISH CHASTOTASI */}
        <div className="card settings-card">
          <div className="settings-card-header">
            <Heart size={20} color="#ec4899" />
            <h3>Qiziqish savol chastotasi</h3>
          </div>
          <div className="settings-card-body">
            <div className="settings-toggle-group">
              <button 
                className={`settings-toggle-btn ${settings.interest_freq === '1w' ? 'active' : ''}`}
                onClick={() => updateSetting("interest_freq", "1w")}
              >1 hafta</button>
              <button 
                className={`settings-toggle-btn ${settings.interest_freq === '1m' ? 'active' : ''}`}
                onClick={() => updateSetting("interest_freq", "1m")}
              >1 oy</button>
            </div>
          </div>
        </div>

        {/* DARK / LIGHT MODE */}
        <div className="card settings-card">
          <div className="settings-card-header">
            {isDark ? <Moon size={20} color="#8b5cf6" /> : <Sun size={20} color="#f59e0b" />}
            <h3>Mavzu (Theme)</h3>
          </div>
          <div className="settings-card-body">
            <div className="settings-toggle-group">
              <button 
                className={`settings-toggle-btn ${!isDark ? 'active' : ''}`}
                onClick={() => onThemeToggle && onThemeToggle('light')}
              >☀️ Light</button>
              <button 
                className={`settings-toggle-btn ${isDark ? 'active' : ''}`}
                onClick={() => onThemeToggle && onThemeToggle('dark')}
              >🌙 Dark</button>
            </div>
          </div>
        </div>

      </div>

      {/* PIN MODAL */}
      {showPinModal && (
        <div className="modal-overlay" onClick={() => setShowPinModal(false)}>
          <div className="modal-content settings-modal" onClick={e => e.stopPropagation()}>
            <h3>🔐 PIN o'zgartirish</h3>
            <div className="modal-form">
              <label>Joriy PIN:</label>
              <input type="password" maxLength={4} value={oldPin} 
                onChange={e => setOldPin(e.target.value.replace(/\D/g, ''))} 
                className="settings-input" placeholder="****" />
              <label>Yangi PIN (4 raqam):</label>
              <input type="password" maxLength={4} value={newPin} 
                onChange={e => setNewPin(e.target.value.replace(/\D/g, ''))} 
                className="settings-input" placeholder="****" />
              {pinError && <p className="text-danger">{pinError}</p>}
              {pinSuccess && <p className="text-success">✅ PIN yangilandi!</p>}
              <div className="modal-actions mt10">
                <button className="btn-outline" onClick={() => setShowPinModal(false)}>Bekor</button>
                <button className="btn-primary" onClick={handlePinChange} 
                  disabled={oldPin.length !== 4 || newPin.length !== 4}>Tasdiqlash</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminSettings;
