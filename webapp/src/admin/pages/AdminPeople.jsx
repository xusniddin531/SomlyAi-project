import React, { useState } from 'react';
import { Users, Target, UserX } from 'lucide-react';
import AdminUsers from './AdminUsers';
import AdminSegments from './AdminSegments';
import AdminBlockedUsers from './AdminBlockedUsers';

/**
 * AdminPeople — Foydalanuvchilar, Segmentatsiya va Bloklanganlar bitta sahifada.
 * Tablar orqali o'tiladi.
 */
const AdminPeople = ({ token, navigateTo, ...rest }) => {
  const [tab, setTab] = useState('users'); // 'users' | 'segments' | 'blocked'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* Tab bar — sticky top */}
      <div style={{
        position: 'sticky', top: 0, zIndex: 5,
        background: 'var(--admin-bg)',
        borderBottom: '1px solid var(--admin-border)',
        padding: '12px 16px 0',
      }}>
        <div style={{
          display: 'inline-flex',
          gap: '4px',
          background: 'var(--admin-card)',
          border: '1px solid var(--admin-border)',
          padding: '4px',
          borderRadius: '12px',
          marginBottom: '12px',
        }}>
          <TabButton
            active={tab === 'users'}
            onClick={() => setTab('users')}
            icon={<Users size={16} />}
            label="Foydalanuvchilar"
          />
          <TabButton
            active={tab === 'segments'}
            onClick={() => setTab('segments')}
            icon={<Target size={16} />}
            label="Segmentatsiya"
          />
          <TabButton
            active={tab === 'blocked'}
            onClick={() => setTab('blocked')}
            icon={<UserX size={16} />}
            label="Bloklanganlar"
            danger
          />
        </div>
      </div>

      {/* Tab content */}
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
        {tab === 'users' && <AdminUsers token={token} navigateTo={navigateTo} {...rest} />}
        {tab === 'segments' && <AdminSegments token={token} navigateTo={navigateTo} {...rest} />}
        {tab === 'blocked' && <AdminBlockedUsers token={token} navigateTo={navigateTo} {...rest} />}
      </div>
    </div>
  );
};

const TabButton = ({ active, onClick, icon, label, danger }) => (
  <button
    onClick={onClick}
    style={{
      display: 'flex',
      alignItems: 'center',
      gap: '6px',
      padding: '8px 14px',
      borderRadius: '9px',
      border: 'none',
      background: active
        ? (danger ? '#ef4444' : 'var(--admin-primary)')
        : 'transparent',
      color: active ? '#fff' : (danger ? '#ef4444' : 'var(--admin-text-secondary)'),
      fontSize: '13px',
      fontWeight: 600,
      cursor: 'pointer',
      transition: 'all 0.2s ease',
      whiteSpace: 'nowrap',
    }}
  >
    {icon}
    {label}
  </button>
);

export default AdminPeople;
