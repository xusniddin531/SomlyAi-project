import React, { useState, useEffect } from 'react';
import { Plus, Megaphone, Trash2, Send, Clock, CheckCircle, XCircle, AlertCircle, Eye, Search } from 'lucide-react';

const STATUS_MAP = {
  draft: { label: 'Qoralama', color: '#6b7280', icon: Clock },
  scheduled: { label: 'Rejalashtirilgan', color: '#f59e0b', icon: Clock },
  sending: { label: 'Yuborilmoqda', color: '#3b82f6', icon: Send },
  completed: { label: 'Yakunlangan', color: '#10b981', icon: CheckCircle },
  stopped: { label: "To'xtatilgan", color: '#ef4444', icon: XCircle },
};

const CONTENT_TYPE_MAP = {
  text: '📝 Matn',
  photo: '🖼 Rasm',
  video: '🎥 Video',
  document: '📄 Fayl',
  photo_text: '🖼+📝 Rasm+Matn',
};

const AdminAds = ({ token, navigateTo }) => {
  const [ads, setAds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetchAds();
    // Poll for status updates every 5s
    const interval = setInterval(fetchAds, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchAds = async () => {
    try {
      const res = await fetch('/api/admin/ads', {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setAds(data);
      }
    } catch (e) {
      console.error('Failed to fetch ads:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (adId) => {
    if (!confirm(`"${adId}" reklamani o'chirmoqchimisiz?`)) return;
    try {
      const res = await fetch(`/api/admin/ads/${adId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        setAds(prev => prev.filter(a => a._id !== adId));
      }
    } catch (e) {
      alert('Xatolik: ' + e.message);
    }
  };

  const handleStop = async (adId) => {
    if (!confirm("Reklamani to'xtatmoqchimisiz?")) return;
    try {
      await fetch(`/api/admin/ads/${adId}/stop`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` }
      });
      fetchAds();
    } catch (e) {
      alert('Xatolik: ' + e.message);
    }
  };

  const filtered = ads.filter(a =>
    !searchQuery || 
    a.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    a._id?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  if (loading) {
    return (
      <div className="admin-page fade-in">
        <h1 className="page-title">📣 Reklama boshqaruvi</h1>
        <div className="card" style={{ padding: '40px', textAlign: 'center' }}>
          <div className="spinner" />
          <p style={{ color: 'var(--text-muted)', marginTop: '12px' }}>Yuklanmoqda...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-page fade-in">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', flexWrap: 'wrap', gap: '12px' }}>
        <h1 className="page-title" style={{ margin: 0 }}>📣 Reklama boshqaruvi</h1>
        <button
          className="btn-primary"
          onClick={() => navigateTo('ad-create')}
          style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 20px', borderRadius: '12px', fontWeight: '600' }}
        >
          <Plus size={18} /> Yangi reklama
        </button>
      </div>

      {/* Search */}
      <div className="card" style={{ padding: '12px 16px', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '10px' }}>
        <Search size={18} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
        <input
          type="text"
          placeholder="Qidirish (nom yoki ID)..."
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          style={{
            flex: 1, background: 'transparent', border: 'none', outline: 'none',
            color: 'var(--text)', fontSize: '14px'
          }}
        />
      </div>

      {/* Stats Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '12px', marginBottom: '20px' }}>
        {['draft', 'scheduled', 'sending', 'completed'].map(status => {
          const info = STATUS_MAP[status];
          const count = ads.filter(a => a.status === status).length;
          const Icon = info.icon;
          return (
            <div key={status} className="card" style={{ padding: '16px', textAlign: 'center' }}>
              <Icon size={20} style={{ color: info.color, marginBottom: '6px' }} />
              <div style={{ fontSize: '22px', fontWeight: '700', color: info.color }}>{count}</div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{info.label}</div>
            </div>
          );
        })}
      </div>

      {/* Ads Table */}
      {filtered.length === 0 ? (
        <div className="card" style={{ padding: '60px 20px', textAlign: 'center' }}>
          <Megaphone size={48} style={{ color: 'var(--text-muted)', marginBottom: '16px', opacity: 0.3 }} />
          <h3 style={{ color: 'var(--text-muted)', fontWeight: '500' }}>
            {searchQuery ? "Topilmadi" : "Hali reklama yaratilmagan"}
          </h3>
          {!searchQuery && (
            <p style={{ color: 'var(--text-muted)', fontSize: '14px', marginTop: '8px' }}>
              "Yangi reklama" tugmasini bosing
            </p>
          )}
        </div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table className="history-table" style={{ width: '100%' }}>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Nomi</th>
                  <th>Turi</th>
                  <th>Holati</th>
                  <th>Qamrov</th>
                  <th>Sana</th>
                  <th>Amallar</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(ad => {
                  const statusInfo = STATUS_MAP[ad.status] || STATUS_MAP.draft;
                  const StatusIcon = statusInfo.icon;
                  return (
                    <tr key={ad._id}>
                      <td><code style={{ fontSize: '12px', background: 'var(--border)', padding: '2px 6px', borderRadius: '4px' }}>{ad._id}</code></td>
                      <td style={{ fontWeight: '500', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{ad.name}</td>
                      <td><span style={{ fontSize: '12px' }}>{CONTENT_TYPE_MAP[ad.content_type] || ad.content_type}</span></td>
                      <td>
                        <span style={{
                          display: 'inline-flex', alignItems: 'center', gap: '4px',
                          padding: '4px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: '600',
                          background: statusInfo.color + '20', color: statusInfo.color
                        }}>
                          <StatusIcon size={12} /> {statusInfo.label}
                        </span>
                      </td>
                      <td>
                        {ad.status === 'completed' || ad.status === 'sending' ? (
                          <span style={{ fontSize: '13px' }}>
                            <span style={{ color: '#10b981' }}>{ad.stats?.sent || 0}</span>
                            {' / '}
                            <span style={{ color: '#ef4444' }}>{ad.stats?.failed || 0}</span>
                            {' / '}
                            {ad.stats?.total || 0}
                          </span>
                        ) : '—'}
                      </td>
                      <td style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{ad.created_at}</td>
                      <td>
                        <div style={{ display: 'flex', gap: '6px' }}>
                          <button
                            onClick={() => navigateTo('ad-create', { editAdId: ad._id })}
                            className="btn-icon"
                            title="Ko'rish"
                            style={{ padding: '6px', borderRadius: '8px', background: 'var(--border)', border: 'none', cursor: 'pointer', color: 'var(--text)' }}
                          >
                            <Eye size={14} />
                          </button>
                          {(ad.status === 'sending' || ad.status === 'scheduled') && (
                            <button
                              onClick={() => handleStop(ad._id)}
                              className="btn-icon"
                              title="To'xtatish"
                              style={{ padding: '6px', borderRadius: '8px', background: '#ef444420', border: 'none', cursor: 'pointer', color: '#ef4444' }}
                            >
                              <XCircle size={14} />
                            </button>
                          )}
                          {(ad.status === 'draft' || ad.status === 'completed' || ad.status === 'stopped') && (
                            <button
                              onClick={() => handleDelete(ad._id)}
                              className="btn-icon"
                              title="O'chirish"
                              style={{ padding: '6px', borderRadius: '8px', background: '#ef444420', border: 'none', cursor: 'pointer', color: '#ef4444' }}
                            >
                              <Trash2 size={14} />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminAds;
