import React, { useState } from 'react';
import { Users, Target } from 'lucide-react';
import AdminUsers from './AdminUsers';
import AdminSegments from './AdminSegments';

/**
 * AdminPeople — Foydalanuvchilar va Segmentatsiya bitta sahifada.
 * Tablar orqali o'tiladi (Users / Segments).
 * Mavjud AdminUsers va AdminSegments komponentlari reuse qilinadi.
 */
const AdminPeople = ({ token, navigateTo, ...rest }) => {
  const [tab, setTab] = useState('users'); // 'users' | 'segments'

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
        </div>
      </div>

      {/* Tab content */}
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
        {tab === 'users' && <AdminUsers token={token} navigateTo={navigateTo} {...rest} />}
        {tab === 'segments' && <AdminSegments token={token} navigateTo={navigateTo} {...rest} />}
      </div>
    </div>
  );
};

const TabButton = ({ active, onClick, icon, label }) => (
  <button
    onClick={onClick}
    style={{
      display: 'flex',
      alignItems: 'center',
      gap: '6px',
      padding: '8px 14px',
      borderRadius: '9px',
      border: 'none',
      background: active ? 'var(--admin-primary)' : 'transparent',
      color: active ? '#fff' : 'var(--admin-text-secondary)',
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
