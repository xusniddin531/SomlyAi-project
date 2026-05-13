import React, { useState, useEffect } from 'react';
import { TrendingUp, Users, Filter, RefreshCw, Target } from 'lucide-react';

const AdminSpending = ({ token }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);
  const [search, setSearch] = useState('');

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/admin/spending-insights?days=${days}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) setData(await res.json());
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  useEffect(() => { fetchData(); }, [days]);

  const formatAmount = (n) => {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return n.toLocaleString();
  };

  const filteredUsers = data?.user_interests?.filter(u => {
    if (!search) return true;
    const q = search.toLowerCase();
    return u.name?.toLowerCase().includes(q) ||
           u.username?.toLowerCase().includes(q) ||
           u.top_categories?.some(c => c.category?.toLowerCase().includes(q));
  }) || [];

  if (loading || !data) {
    return (
      <div className="admin-page">
        <h1 className="page-title">📊 Xarajat Tahlili</h1>
        <div className="skeleton-row mt20" style={{ height: '200px' }}></div>
        <div className="skeleton-row" style={{ height: '400px' }}></div>
      </div>
    );
  }

  return (
    <div className="admin-page fade-in">
      <div className="detail-header">
        <h1 className="page-title"><Target size={22} style={{verticalAlign:'-4px',marginRight:'6px'}}/>Xarajat Tahlili</h1>
        <button className="btn-icon" onClick={fetchData} title="Yangilash"><RefreshCw size={16} /></button>
      </div>

      {/* PERIOD FILTER */}
      <div className="spending-filters">
        <div className="settings-toggle-group">
          {[7, 30, 90].map(d => (
            <button key={d} className={`settings-toggle-btn ${days === d ? 'active' : ''}`} onClick={() => setDays(d)}>
              {d} kun
            </button>
          ))}
        </div>
      </div>

      {/* TOP CATEGORIES */}
      <div className="card mt20">
        <div className="settings-card-header">
          <TrendingUp size={18} color="#f59e0b" />
          <h3>Top kategoriyalar ({days} kun)</h3>
        </div>
        <div className="spending-cats-grid">
          {data.top_categories.map((cat, i) => (
            <div key={i} className="spending-cat-item">
              <div className="spending-cat-rank">#{i + 1}</div>
              <div className="spending-cat-info">
                <div className="spending-cat-name">{cat.category || 'Boshqa'}</div>
                <div className="spending-cat-meta">
                  <span>{formatAmount(cat.total_amount)} so'm</span>
                  <span>•</span>
                  <span>{cat.count} ta tranzaksiya</span>
                  <span>•</span>
                  <span><Users size={12}/> {cat.user_count} user</span>
                </div>
              </div>
              <div className="spending-cat-bar">
                <div className="spending-cat-fill" style={{
                  width: `${Math.min(100, (cat.total_amount / (data.top_categories[0]?.total_amount || 1)) * 100)}%`
                }}></div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* USER INTERESTS */}
      <div className="card mt20">
        <div className="settings-card-header">
          <Users size={18} color="#6366f1" />
          <h3>Userlar qiziqishlari ({filteredUsers.length} user)</h3>
        </div>
        <div style={{padding:'12px 16px 0'}}>
          <input
            type="text"
            className="user-id-input"
            placeholder="🔍 User yoki kategoriya qidirish..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{marginBottom:'8px'}}
          />
        </div>
        <div className="spending-users-list">
          {filteredUsers.slice(0, 50).map((u, i) => (
            <div key={i} className="spending-user-row">
              <div className="spending-user-info">
                <span className="spending-user-name">{u.name || 'Noma\'lum'}</span>
                {u.username && <span className="spending-user-handle">@{u.username}</span>}
              </div>
              <div className="spending-user-cats">
                {u.top_categories.map((c, j) => (
                  <span key={j} className={`spending-tag tag-${j}`}>
                    {c.category} ({formatAmount(c.total)})
                  </span>
                ))}
              </div>
            </div>
          ))}
          {filteredUsers.length === 0 && (
            <div style={{padding:'24px',textAlign:'center',color:'var(--text-muted)'}}>
              Natija topilmadi
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default AdminSpending;
