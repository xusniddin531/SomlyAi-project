import React, { useState, useEffect } from 'react';
import { Zap, UserX, UserCheck, ShieldPlus, ShieldOff, Globe, Edit2, Plus, Trash2, X, Hash, Link as LinkIcon, RefreshCw } from 'lucide-react';

/**
 * AdminQuickActions — Barcha "quick admin" tugmalari bir joyda.
 * Bot commandlari /ban, /unban, /admin, /remove_admin, /setwebapp,
 * /setchannel, /add_channel, /remove_channel o'rniga.
 */
const AdminQuickActions = ({ token, navigateTo }) => {
  const [toast, setToast] = useState('');
  const [admins, setAdmins] = useState([]);
  const [webappUrl, setWebappUrl] = useState('');
  const [newAdminId, setNewAdminId] = useState('');
  const [banUserId, setBanUserId] = useState('');
  const [newWebappUrl, setNewWebappUrl] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(''), 2500);
  };

  const fetchAdmins = async () => {
    try {
      const res = await fetch('/api/admin/admins', { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setAdmins(data.items || []);
      }
    } catch (e) { console.error(e); }
  };

  const fetchWebappUrl = async () => {
    try {
      const res = await fetch('/api/admin/webapp-url', { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setWebappUrl(data.url || '');
        setNewWebappUrl(data.url || '');
      }
    } catch (e) { console.error(e); }
  };

  useEffect(() => {
    Promise.all([fetchAdmins(), fetchWebappUrl()]).finally(() => setLoading(false));
  }, []);

  // ── Ban / Unban ──
  const handleBan = async (mode) => {
    const id = banUserId.trim();
    if (!id || !/^\d+$/.test(id)) {
      showToast('❌ Faqat raqam Telegram ID kiriting');
      return;
    }
    setSaving(true);
    try {
      const res = await fetch(`/api/admin/users/${id}/${mode}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        showToast(mode === 'ban' ? `🚫 ${id} ban qilindi` : `✅ ${id} ban olib tashlandi`);
        setBanUserId('');
      } else {
        showToast('❌ Xato');
      }
    } catch (e) { showToast('❌ Tarmoq xatosi'); }
    finally { setSaving(false); }
  };

  // ── Add Admin ──
  const handleAddAdmin = async () => {
    const id = newAdminId.trim();
    if (!id || !/^\d+$/.test(id)) {
      showToast('❌ Faqat raqam Telegram ID kiriting');
      return;
    }
    setSaving(true);
    try {
      const res = await fetch('/api/admin/admins', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ telegram_id: parseInt(id, 10) })
      });
      if (res.ok) {
        showToast(`✅ ${id} admin qilindi`);
        setNewAdminId('');
        fetchAdmins();
      } else {
        showToast('❌ Xato');
      }
    } catch (e) { showToast('❌ Tarmoq xatosi'); }
    finally { setSaving(false); }
  };

  const handleRemoveAdmin = async (id) => {
    if (!window.confirm(`${id} ni adminlikdan chiqarishni xohlaysizmi?`)) return;
    try {
      const res = await fetch(`/api/admin/admins/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        showToast('✅ Adminlikdan chiqarildi');
        fetchAdmins();
      } else { showToast('❌ Xato'); }
    } catch (e) { showToast('❌ Tarmoq xatosi'); }
  };

  // ── WebApp URL ──
  const handleSaveWebappUrl = async () => {
    const url = newWebappUrl.trim();
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      showToast('❌ URL https:// yoki http:// bilan boshlanishi kerak');
      return;
    }
    setSaving(true);
    try {
      const res = await fetch('/api/admin/webapp-url', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ url })
      });
      if (res.ok) {
        showToast('✅ Mini App URL yangilandi');
        setWebappUrl(url);
      } else {
        const err = await res.json();
        showToast(`❌ ${err.error || 'Xato'}`);
      }
    } catch (e) { showToast('❌ Tarmoq xatosi'); }
    finally { setSaving(false); }
  };

  return (
    <div style={{ padding: '20px', maxWidth: '1000px', margin: '0 auto' }}>
      {toast && (
        <div style={{
          position: 'fixed', top: '20px', right: '20px', zIndex: 9999,
          background: 'var(--admin-card)', border: '1px solid var(--admin-border)',
          padding: '12px 20px', borderRadius: '12px', boxShadow: '0 8px 24px rgba(0,0,0,0.2)',
          fontSize: '14px', fontWeight: 600,
        }}>{toast}</div>
      )}

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '24px' }}>
        <div style={{
          width: '48px', height: '48px', borderRadius: '12px',
          background: 'linear-gradient(135deg, #F59E0B, #EF4444)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff'
        }}>
          <Zap size={26} />
        </div>
        <div>
          <h1 style={{ fontSize: '24px', margin: 0, fontWeight: 700 }}>Tezkor Amallar</h1>
          <p style={{ margin: '4px 0 0', color: 'var(--admin-text-secondary)', fontSize: '13px' }}>
            Bot commandlari o'rniga — barcha boshqaruv shu yerda
          </p>
        </div>
      </div>

      {/* Section: User Ban */}
      <Section icon={<UserX size={18} />} title="Foydalanuvchini bloklash / ochish" color="#EF4444">
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <input
            type="text" value={banUserId}
            onChange={(e) => setBanUserId(e.target.value.replace(/\D/g, ''))}
            placeholder="Telegram ID (raqam)"
            style={{ ...inputStyle, flex: '1 1 220px' }}
            disabled={saving}
          />
          <button onClick={() => handleBan('ban')} disabled={saving} className="adm-action-btn" style={{ background: 'rgba(239,68,68,0.15)', color: '#EF4444' }}>
            <UserX size={16} /> Ban
          </button>
          <button onClick={() => handleBan('unban')} disabled={saving} className="adm-action-btn" style={{ background: 'rgba(16,185,129,0.15)', color: '#10B981' }}>
            <UserCheck size={16} /> Unban
          </button>
        </div>
        <p style={{ margin: '8px 0 0', fontSize: '12px', color: 'var(--admin-text-secondary)' }}>
          💡 Foydalanuvchi ID ni bilmasangiz, "Foydalanuvchilar" sahifasida toping
        </p>
      </Section>

      {/* Section: Admins */}
      <Section icon={<ShieldPlus size={18} />} title="Adminlar boshqaruvi" color="#8B5CF6">
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '12px' }}>
          <input
            type="text" value={newAdminId}
            onChange={(e) => setNewAdminId(e.target.value.replace(/\D/g, ''))}
            placeholder="Yangi admin Telegram ID"
            style={{ ...inputStyle, flex: '1 1 240px' }}
            disabled={saving}
          />
          <button onClick={handleAddAdmin} disabled={saving} className="adm-action-btn" style={{ background: 'linear-gradient(135deg,#8B5CF6,#6366F1)', color: '#fff' }}>
            <Plus size={16} /> Admin qo'shish
          </button>
        </div>
        {loading ? (
          <div style={{ color: 'var(--admin-text-secondary)', fontSize: '13px' }}>Yuklanmoqda...</div>
        ) : admins.length === 0 ? (
          <div style={{ color: 'var(--admin-text-secondary)', fontSize: '13px' }}>Hech qanday admin yo'q</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {admins.map((a) => (
              <div key={a.telegram_id} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                background: 'var(--admin-card)', border: '1px solid var(--admin-border)',
                borderRadius: '10px', padding: '10px 14px'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <Hash size={14} color="var(--admin-text-secondary)" />
                  <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{a.telegram_id}</span>
                  {a.added_at && (
                    <span style={{ fontSize: '11px', color: 'var(--admin-text-secondary)' }}>
                      {new Date(a.added_at).toLocaleDateString()}
                    </span>
                  )}
                </div>
                <button onClick={() => handleRemoveAdmin(a.telegram_id)} className="adm-icon-btn" style={{ borderColor: 'rgba(239,68,68,0.4)', color: '#EF4444' }}>
                  <ShieldOff size={14} /> Olib tashlash
                </button>
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* Section: Mini App URL */}
      <Section icon={<Globe size={18} />} title="Mini App URL sozlash" color="#0EA5E9">
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '8px' }}>
          <input
            type="text" value={newWebappUrl}
            onChange={(e) => setNewWebappUrl(e.target.value)}
            placeholder="https://your-domain.com"
            style={{ ...inputStyle, flex: '1 1 280px' }}
            disabled={saving}
          />
          <button onClick={handleSaveWebappUrl} disabled={saving || newWebappUrl === webappUrl} className="adm-action-btn" style={{ background: 'linear-gradient(135deg,#0EA5E9,#3B82F6)', color: '#fff' }}>
            <LinkIcon size={16} /> Saqlash
          </button>
        </div>
        {webappUrl && (
          <p style={{ margin: 0, fontSize: '12px', color: 'var(--admin-text-secondary)' }}>
            Joriy URL: <span style={{ fontFamily: 'monospace' }}>{webappUrl}</span>
          </p>
        )}
      </Section>

      {/* Section: Channels — shortcut */}
      <Section icon={<Edit2 size={18} />} title="Kanallar" color="#10B981">
        <p style={{ margin: '0 0 10px', fontSize: '13px', color: 'var(--admin-text-secondary)' }}>
          Kanal qo'shish, tahrirlash va o'chirish uchun
        </p>
        <button
          onClick={() => navigateTo && navigateTo('channels')}
          className="adm-action-btn"
          style={{ background: 'linear-gradient(135deg,#10B981,#059669)', color: '#fff' }}
        >
          <RefreshCw size={16} /> Kanallar sahifasiga o'tish
        </button>
      </Section>
    </div>
  );
};

const Section = ({ icon, title, color, children }) => (
  <div style={{
    background: 'var(--admin-card)', border: '1px solid var(--admin-border)',
    borderRadius: '14px', padding: '18px', marginBottom: '16px'
  }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
      <div style={{
        width: '34px', height: '34px', borderRadius: '9px',
        background: `${color}22`, color: color,
        display: 'flex', alignItems: 'center', justifyContent: 'center'
      }}>{icon}</div>
      <h2 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: 'var(--admin-text)' }}>{title}</h2>
    </div>
    {children}
  </div>
);

const inputStyle = {
  padding: '10px 12px',
  background: 'var(--admin-bg, var(--admin-card))',
  border: '1px solid var(--admin-border)',
  borderRadius: '10px',
  color: 'var(--admin-text)',
  fontSize: '14px',
  outline: 'none',
  boxSizing: 'border-box',
  minWidth: '0'
};

export default AdminQuickActions;
