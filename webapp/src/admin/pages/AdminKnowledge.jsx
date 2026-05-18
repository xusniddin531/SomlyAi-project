import React, { useState, useEffect } from 'react';
import { Brain, Plus, Search, Edit2, Trash2, Check, X, RefreshCw, BookOpen } from 'lucide-react';

/**
 * AdminKnowledge — AI Bilimlar bazasini boshqarish
 * Bot commandlari /teach, /knowledge, /editteach, /unteach o'rniga.
 *
 * Functions:
 *   • GET    /api/admin/knowledge       — ro'yxat
 *   • POST   /api/admin/knowledge       — yangi qo'shish
 *   • PUT    /api/admin/knowledge       — tahrirlash (content + active flag)
 *   • DELETE /api/admin/knowledge?topic= — arxivlash
 */
const AdminKnowledge = ({ token }) => {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all'); // 'all' | 'active' | 'archived'
  const [editing, setEditing] = useState(null); // {id, topic, content} | null
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ topic: '', content: '' });
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState('');

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(''), 2500);
  };

  const fetchItems = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/admin/knowledge', {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setItems(data.items || []);
      }
    } catch (e) {
      console.error(e);
      showToast('❌ Yuklashda xato');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchItems(); }, []);

  const handleCreate = async () => {
    if (!form.topic.trim() || !form.content.trim()) {
      showToast('❌ Mavzu va matn bo\'sh bo\'lishi mumkin emas');
      return;
    }
    setSaving(true);
    try {
      const res = await fetch('/api/admin/knowledge', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ topic: form.topic.trim(), content: form.content.trim() })
      });
      if (res.ok) {
        showToast('✅ Bilim qo\'shildi');
        setForm({ topic: '', content: '' });
        setCreating(false);
        fetchItems();
      } else {
        const err = await res.json();
        showToast(`❌ ${err.error || 'Xato'}`);
      }
    } catch (e) {
      showToast('❌ Tarmoq xatosi');
    } finally {
      setSaving(false);
    }
  };

  const handleUpdate = async () => {
    if (!editing.content.trim()) {
      showToast('❌ Matn bo\'sh');
      return;
    }
    setSaving(true);
    try {
      const res = await fetch('/api/admin/knowledge', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ topic: editing.topic, content: editing.content.trim() })
      });
      if (res.ok) {
        showToast('✅ Yangilandi');
        setEditing(null);
        fetchItems();
      } else {
        showToast('❌ Xato');
      }
    } catch (e) {
      showToast('❌ Tarmoq xatosi');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleActive = async (item) => {
    try {
      const res = await fetch('/api/admin/knowledge', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ topic: item.topic, active: !item.active })
      });
      if (res.ok) {
        showToast(item.active ? '⏸ Arxivlandi' : '✅ Faollashtirildi');
        fetchItems();
      }
    } catch (e) {
      showToast('❌ Xato');
    }
  };

  const handleDelete = async (item) => {
    if (!window.confirm(`"${item.topic}" mavzuni arxivlashni xohlaysizmi?`)) return;
    try {
      const res = await fetch(`/api/admin/knowledge?topic=${encodeURIComponent(item.topic)}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        showToast('🗑 Arxivlandi');
        fetchItems();
      }
    } catch (e) {
      showToast('❌ Xato');
    }
  };

  // Filtered list
  const filtered = items.filter(it => {
    if (filter === 'active' && !it.active) return false;
    if (filter === 'archived' && it.active) return false;
    if (search) {
      const q = search.toLowerCase();
      return it.topic.toLowerCase().includes(q) || it.content.toLowerCase().includes(q);
    }
    return true;
  });

  const totalActive = items.filter(i => i.active).length;
  const totalArchived = items.length - totalActive;
  const totalUsage = items.reduce((sum, i) => sum + (i.usage_count || 0), 0);

  return (
    <div style={{ padding: '20px', maxWidth: '1100px', margin: '0 auto' }}>
      {/* Toast */}
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
          background: 'linear-gradient(135deg, #8B5CF6, #6366F1)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff'
        }}>
          <Brain size={26} />
        </div>
        <div style={{ flex: 1 }}>
          <h1 style={{ fontSize: '24px', margin: 0, fontWeight: 700 }}>AI Bilimlar bazasi</h1>
          <p style={{ margin: '4px 0 0', color: 'var(--admin-text-secondary)', fontSize: '13px' }}>
            Bot AI prompt'iga qo'shimcha qo'llanmalar — har bir bilim AI ga yo'l-yo'riq beradi
          </p>
        </div>
        <button
          onClick={fetchItems}
          style={{
            background: 'var(--admin-card)', border: '1px solid var(--admin-border)',
            color: 'var(--admin-text)', borderRadius: '10px', padding: '10px 14px',
            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px'
          }}
        >
          <RefreshCw size={16} /> Yangilash
        </button>
      </div>

      {/* Stat cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px', marginBottom: '20px' }}>
        <StatCard icon={<BookOpen size={20} />} label="Jami bilimlar" value={items.length} color="#8B5CF6" />
        <StatCard icon={<Check size={20} />} label="Faol" value={totalActive} color="#10B981" />
        <StatCard icon={<X size={20} />} label="Arxivlangan" value={totalArchived} color="#6B7280" />
        <StatCard icon={<Brain size={20} />} label="Jami ishlatish" value={totalUsage} color="#F59E0B" />
      </div>

      {/* Toolbar: Search + Filter + Add */}
      <div style={{ display: 'flex', gap: '10px', marginBottom: '16px', flexWrap: 'wrap' }}>
        <div style={{ flex: '1 1 240px', position: 'relative' }}>
          <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--admin-text-secondary)' }} />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Mavzu yoki matn bo'yicha qidirish..."
            style={{
              width: '100%', background: 'var(--admin-card)', border: '1px solid var(--admin-border)',
              borderRadius: '10px', padding: '10px 14px 10px 38px', color: 'var(--admin-text)',
              fontSize: '14px', outline: 'none', boxSizing: 'border-box'
            }}
          />
        </div>
        <div style={{ display: 'flex', gap: '6px', background: 'var(--admin-card)', padding: '4px', borderRadius: '10px', border: '1px solid var(--admin-border)' }}>
          {[
            { k: 'all', label: 'Hammasi' },
            { k: 'active', label: 'Faol' },
            { k: 'archived', label: 'Arxiv' },
          ].map(f => (
            <button
              key={f.k}
              onClick={() => setFilter(f.k)}
              style={{
                background: filter === f.k ? 'var(--admin-primary)' : 'transparent',
                color: filter === f.k ? '#fff' : 'var(--admin-text-secondary)',
                border: 'none', borderRadius: '8px', padding: '6px 12px',
                fontSize: '13px', fontWeight: 600, cursor: 'pointer',
                transition: 'all 0.2s',
              }}
            >{f.label}</button>
          ))}
        </div>
        <button
          onClick={() => { setCreating(true); setForm({ topic: '', content: '' }); }}
          style={{
            background: 'linear-gradient(135deg, #8B5CF6, #6366F1)', border: 'none', color: '#fff',
            borderRadius: '10px', padding: '10px 16px', cursor: 'pointer', fontWeight: 600,
            display: 'flex', alignItems: 'center', gap: '6px'
          }}
        >
          <Plus size={16} /> Yangi bilim
        </button>
      </div>

      {/* List */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px', color: 'var(--admin-text-secondary)' }}>
          Yuklanmoqda...
        </div>
      ) : filtered.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: '60px 20px', background: 'var(--admin-card)',
          borderRadius: '14px', border: '1px dashed var(--admin-border)'
        }}>
          <Brain size={48} style={{ color: 'var(--admin-text-secondary)', opacity: 0.4, margin: '0 auto 12px' }} />
          <p style={{ color: 'var(--admin-text-secondary)', margin: '0 0 12px' }}>
            {search ? 'Mos keluvchi bilim topilmadi' : 'Hali bilim qo\'shilmagan'}
          </p>
          {!search && (
            <button
              onClick={() => setCreating(true)}
              style={{
                background: 'linear-gradient(135deg, #8B5CF6, #6366F1)', border: 'none', color: '#fff',
                borderRadius: '10px', padding: '10px 18px', cursor: 'pointer', fontWeight: 600
              }}
            >+ Birinchi bilimni qo'shing</button>
          )}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {filtered.map(item => (
            <KnowledgeCard
              key={item.id || item.topic}
              item={item}
              onEdit={() => setEditing({ topic: item.topic, content: item.content })}
              onToggleActive={() => handleToggleActive(item)}
              onDelete={() => handleDelete(item)}
            />
          ))}
        </div>
      )}

      {/* Create Modal */}
      {creating && (
        <Modal title="Yangi bilim qo'shish" onClose={() => setCreating(false)}>
          <FormFields form={form} setForm={setForm} disabled={saving} />
          <ModalFooter>
            <button onClick={() => setCreating(false)} className="adm-btn-secondary">Bekor</button>
            <button onClick={handleCreate} disabled={saving} className="adm-btn-primary">
              {saving ? 'Saqlanmoqda...' : 'Qo\'shish'}
            </button>
          </ModalFooter>
        </Modal>
      )}

      {/* Edit Modal */}
      {editing && (
        <Modal title={`Tahrirlash: ${editing.topic}`} onClose={() => setEditing(null)}>
          <div style={{ marginBottom: '12px' }}>
            <label style={labelStyle}>Mavzu (o'zgarmas)</label>
            <input type="text" value={editing.topic} disabled style={{ ...inputStyle, opacity: 0.5 }} />
          </div>
          <div>
            <label style={labelStyle}>Matn</label>
            <textarea
              value={editing.content}
              onChange={(e) => setEditing({ ...editing, content: e.target.value })}
              rows={6}
              style={{ ...inputStyle, fontFamily: 'inherit', resize: 'vertical' }}
            />
          </div>
          <ModalFooter>
            <button onClick={() => setEditing(null)} className="adm-btn-secondary">Bekor</button>
            <button onClick={handleUpdate} disabled={saving} className="adm-btn-primary">
              {saving ? 'Saqlanmoqda...' : 'Saqlash'}
            </button>
          </ModalFooter>
        </Modal>
      )}
    </div>
  );
};

// ─── Subcomponents ───

const StatCard = ({ icon, label, value, color }) => (
  <div style={{
    background: 'var(--admin-card)', border: '1px solid var(--admin-border)',
    borderRadius: '12px', padding: '14px', display: 'flex', alignItems: 'center', gap: '12px'
  }}>
    <div style={{
      width: '40px', height: '40px', borderRadius: '10px',
      background: `${color}22`, color: color,
      display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0
    }}>{icon}</div>
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--admin-text)' }}>{value}</div>
      <div style={{ fontSize: '12px', color: 'var(--admin-text-secondary)' }}>{label}</div>
    </div>
  </div>
);

const KnowledgeCard = ({ item, onEdit, onToggleActive, onDelete }) => (
  <div style={{
    background: 'var(--admin-card)', border: '1px solid var(--admin-border)',
    borderRadius: '14px', padding: '14px 16px', opacity: item.active ? 1 : 0.6,
    transition: 'all 0.2s'
  }}>
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px', marginBottom: '8px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flex: 1, minWidth: 0 }}>
        <span style={{
          fontSize: '11px', fontWeight: 700, padding: '3px 8px', borderRadius: '6px',
          background: item.active ? 'rgba(16,185,129,0.18)' : 'rgba(107,114,128,0.18)',
          color: item.active ? '#10B981' : '#9CA3AF',
        }}>{item.active ? '● FAOL' : '○ ARXIV'}</span>
        <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: 'var(--admin-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {item.topic}
        </h3>
      </div>
      <span style={{ fontSize: '11px', color: 'var(--admin-text-secondary)', flexShrink: 0 }}>
        {item.usage_count || 0} marta
      </span>
    </div>
    <p style={{
      margin: '0 0 12px', fontSize: '13px', color: 'var(--admin-text-secondary)',
      lineHeight: '1.5', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
      overflow: 'hidden'
    }}>{item.content}</p>
    <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
      <button onClick={onEdit} className="adm-icon-btn" style={{ borderColor: 'rgba(99,102,241,0.4)', color: '#6366F1' }}>
        <Edit2 size={14} /> Tahrirlash
      </button>
      <button onClick={onToggleActive} className="adm-icon-btn">
        {item.active ? <><X size={14} /> Arxivlash</> : <><Check size={14} /> Faollashtirish</>}
      </button>
      <button onClick={onDelete} className="adm-icon-btn" style={{ borderColor: 'rgba(239,68,68,0.4)', color: '#EF4444' }}>
        <Trash2 size={14} /> O'chirish
      </button>
    </div>
  </div>
);

const Modal = ({ title, onClose, children }) => (
  <div onClick={onClose} style={{
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(6px)',
    zIndex: 9998, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px'
  }}>
    <div onClick={(e) => e.stopPropagation()} style={{
      background: 'var(--admin-bg, var(--admin-card))', borderRadius: '16px', padding: '24px',
      width: '100%', maxWidth: '520px', boxShadow: '0 24px 60px rgba(0,0,0,0.4)',
      animation: 'fadeIn 0.2s ease'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 700 }}>{title}</h2>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--admin-text-secondary)', cursor: 'pointer' }}>
          <X size={20} />
        </button>
      </div>
      {children}
    </div>
  </div>
);

const ModalFooter = ({ children }) => (
  <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '20px' }}>
    {children}
  </div>
);

const FormFields = ({ form, setForm, disabled }) => (
  <>
    <div style={{ marginBottom: '12px' }}>
      <label style={labelStyle}>Mavzu</label>
      <input
        type="text" value={form.topic} disabled={disabled}
        onChange={(e) => setForm({ ...form, topic: e.target.value })}
        placeholder="Masalan: 'Oziq-ovqat kategoriyasi'"
        style={inputStyle}
      />
    </div>
    <div>
      <label style={labelStyle}>Matn (AI shu matnni o'qib bilim oladi)</label>
      <textarea
        value={form.content} disabled={disabled}
        onChange={(e) => setForm({ ...form, content: e.target.value })}
        placeholder="Bilim haqida batafsil yozing. AI shu ma'lumotni har xabarda hisobga oladi."
        rows={6}
        style={{ ...inputStyle, fontFamily: 'inherit', resize: 'vertical' }}
      />
    </div>
  </>
);

const labelStyle = {
  display: 'block', fontSize: '12px', fontWeight: 600,
  color: 'var(--admin-text-secondary)', marginBottom: '6px'
};

const inputStyle = {
  width: '100%', padding: '10px 12px',
  background: 'var(--admin-card)', border: '1px solid var(--admin-border)',
  borderRadius: '10px', color: 'var(--admin-text)', fontSize: '14px',
  outline: 'none', boxSizing: 'border-box'
};

export default AdminKnowledge;
