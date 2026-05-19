import React, { useState, useEffect, useMemo } from 'react';
import { Search, UserX, User, Copy, CheckCheck } from 'lucide-react';

const AdminBlockedUsers = ({ token }) => {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [copiedId, setCopiedId] = useState(null);
  const [page, setPage] = useState(1);
  const ITEMS_PER_PAGE = 30;

  useEffect(() => {
    fetchBlockedUsers();
  }, []);

  const fetchBlockedUsers = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/admin/blocked-users', {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setUsers(data);
      }
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  const filteredUsers = useMemo(() => {
    if (!search) return users;
    const q = search.toLowerCase();
    return users.filter(u =>
      String(u.telegram_id).includes(q) ||
      (u.username || '').toLowerCase().includes(q) ||
      (u.full_name || '').toLowerCase().includes(q)
    );
  }, [users, search]);

  const displayed = filteredUsers.slice(0, page * ITEMS_PER_PAGE);
  const hasMore = displayed.length < filteredUsers.length;

  const copyToClipboard = async (text, id) => {
    try {
      await navigator.clipboard.writeText(String(text));
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 1500);
    } catch (e) {
      console.error('Copy failed', e);
    }
  };

  return (
    <div className="admin-page fade-in">
      <div className="flex-row" style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <div>
          <h1 className="page-title" style={{ margin: 0 }}>🚫 Bloklanganlar</h1>
          <p style={{ margin: '4px 0 0', fontSize: '13px', color: 'var(--admin-text-secondary)' }}>
            Botni bloklagan foydalanuvchilar — {users.length} ta
          </p>
        </div>
      </div>

      <div className="filters-card card mb20">
        <div className="search-bar">
          <Search size={18} />
          <input
            type="text"
            placeholder="Telegram ID, username yoki ism bo'yicha qidirish..."
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1); }}
          />
        </div>
      </div>

      <p className="results-count">Topildi: {filteredUsers.length} ta</p>

      {loading ? (
        <div>{[1,2,3,4,5].map(i => <div key={i} className="skeleton-row mt10" />)}</div>
      ) : displayed.length === 0 ? (
        <div className="empty-state">
          <UserX size={40} style={{ opacity: 0.3, marginBottom: 8 }} />
          <p>{search ? 'Topilmadi.' : "Hozircha hech kim botni bloklamagan."}</p>
        </div>
      ) : (
        <div className="users-list">
          {displayed.map(u => (
            <BlockedUserRow
              key={u.telegram_id}
              user={u}
              copiedId={copiedId}
              onCopy={copyToClipboard}
            />
          ))}
        </div>
      )}

      {hasMore && (
        <button className="btn-load-more" onClick={() => setPage(p => p + 1)}>
          Ko'proq yuklash
        </button>
      )}
    </div>
  );
};

const BlockedUserRow = ({ user: u, copiedId, onCopy }) => {
  const isCopied = copiedId === u.telegram_id;
  const displayName = u.full_name || (u.username ? `@${u.username}` : "Noma'lum");
  const lastActive = u.last_active ? u.last_active.substring(0, 10) : 'Noma\'lum';
  const createdAt = u.created_at ? u.created_at.substring(0, 10) : 'Noma\'lum';

  return (
    <div
      className="user-list-item card"
      style={{ borderLeft: '3px solid #ef4444' }}
    >
      <div className="user-item-main">
        <div className="user-avatar" style={{ background: '#fee2e2', color: '#ef4444' }}>
          {displayName.charAt(0).toUpperCase() || <UserX size={16} />}
        </div>
        <div className="user-item-info">
          <div className="ui-row">
            <span className="ui-name">{displayName}</span>
            {u.registration_complete === false && (
              <span className="ui-badge" style={{ background: '#fef3c7', color: '#92400e' }}>
                Ro'yxatdan o'tmagan
              </span>
            )}
          </div>
          <div className="ui-row secondary">
            {u.username ? (
              <span style={{ color: 'var(--admin-primary)' }}>@{u.username}</span>
            ) : (
              <span style={{ opacity: 0.5 }}>Username yo'q</span>
            )}
            <span>•</span>
            <span style={{
              fontFamily: 'monospace',
              fontSize: '12px',
              background: 'var(--admin-card)',
              padding: '1px 6px',
              borderRadius: '4px',
              letterSpacing: '0.5px',
            }}>
              ID: {u.telegram_id}
            </span>
          </div>
        </div>
      </div>

      <div className="user-item-right" style={{ gap: '10px' }}>
        <div className="ui-activity" style={{ textAlign: 'right' }}>
          <span>Qo'shilgan</span>
          <strong>{createdAt}</strong>
          <span style={{ marginTop: 2 }}>Oxirgi faol</span>
          <strong>{lastActive}</strong>
        </div>
        <button
          onClick={() => onCopy(u.telegram_id, u.telegram_id)}
          title="Telegram ID nusxa olish"
          style={{
            background: isCopied ? '#dcfce7' : 'var(--admin-card)',
            border: '1px solid var(--admin-border)',
            borderRadius: '8px',
            padding: '6px 10px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            fontSize: '12px',
            color: isCopied ? '#16a34a' : 'var(--admin-text-secondary)',
            transition: 'all 0.2s',
            whiteSpace: 'nowrap',
          }}
        >
          {isCopied ? <CheckCheck size={14} /> : <Copy size={14} />}
          {isCopied ? 'Nusxa olindi' : 'ID copy'}
        </button>
      </div>
    </div>
  );
};

export default AdminBlockedUsers;
