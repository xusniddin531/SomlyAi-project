import React, { useState, useEffect } from 'react';
import { BarChart3, Users, Target, Megaphone, Send, Bot, TrendingUp, Settings, Moon, Sun, LogOut, Brain, Zap } from 'lucide-react';

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', icon: BarChart3 },
  { id: 'users', label: 'Foydalanuvchilar', icon: Users },
  { id: 'segments', label: 'Segmentatsiya', icon: Target },
  { id: 'spending', label: 'Xarajat Tahlili', icon: TrendingUp },
  { id: 'channels', label: 'Kanallar', icon: Megaphone },
  { id: 'broadcast', label: 'Broadcast', icon: Send },
  { id: 'knowledge', label: 'AI Bilimlar', icon: Brain },
  { id: 'quick-actions', label: 'Tezkor Amallar', icon: Zap },
  { id: 'ai-chat', label: 'AI Chat', icon: Bot },
  { id: 'settings', label: 'Sozlamalar', icon: Settings },
];

const AdminLayout = ({ activePage, onNavigate, children, onLogout }) => {
  const [dark, setDark] = useState(() => {
    const saved = localStorage.getItem('admin_theme');
    if (saved) return saved === 'dark';
    if (window.Telegram?.WebApp?.colorScheme) return window.Telegram.WebApp.colorScheme === 'dark';
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });

  useEffect(() => {
    // Listen for data-theme changes from AdminSettings
    const observer = new MutationObserver(() => {
      const theme = document.documentElement.getAttribute('data-theme');
      if (theme) setDark(theme === 'dark');
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => observer.disconnect();
  }, []);

  const toggleDark = () => {
    const newDark = !dark;
    setDark(newDark);
    localStorage.setItem('admin_theme', newDark ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', newDark ? 'dark' : 'light');
  };

  return (
    <div className={`admin-root ${dark ? 'dark' : 'light'}`}>
      {/* Sidebar (desktop/tablet) */}
      <aside className="admin-sidebar">
        <div className="sidebar-header">
          <img src="/src/somly.jpg" alt="Logo" className="sidebar-logo" />
          <span className="sidebar-title">Admin</span>
        </div>
        <nav className="sidebar-nav">
          {NAV_ITEMS.map(item => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                className={`sidebar-item ${activePage === item.id ? 'active' : ''}`}
                onClick={() => onNavigate(item.id)}
              >
                <Icon size={20} />
                <span className="sidebar-label">{item.label}</span>
              </button>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <button className="sidebar-item" onClick={toggleDark}>
            {dark ? <Sun size={20} /> : <Moon size={20} />}
            <span className="sidebar-label">{dark ? 'Light' : 'Dark'}</span>
          </button>
          <button className="sidebar-item logout" onClick={onLogout}>
            <LogOut size={20} />
            <span className="sidebar-label">Chiqish</span>
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="admin-main">
        <div className="admin-content">{children}</div>
      </main>

      {/* Bottom tab bar (mobile) */}
      <nav className="admin-tabbar">
        {NAV_ITEMS.slice(0, 5).map(item => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              className={`tabbar-item ${activePage === item.id ? 'active' : ''}`}
              onClick={() => onNavigate(item.id)}
            >
              <Icon size={20} />
              <span>{item.label.split(' ')[0]}</span>
            </button>
          );
        })}
      </nav>
    </div>
  );
};

export default AdminLayout;
