import React, { useState, useEffect } from 'react';
import PinLock from './PinLock';
import AdminLayout from './AdminLayout';
import AdminDashboard from './pages/AdminDashboard';
import AdminChannels from './pages/AdminChannels';
import AdminChannelDetail from './pages/AdminChannelDetail';
import AdminBroadcast from './pages/AdminBroadcast';
import AdminSpending from './pages/AdminSpending';
import AdminSettings from './pages/AdminSettings';
import AdminKnowledge from './pages/AdminKnowledge';
import AdminQuickActions from './pages/AdminQuickActions';
// AdminPeople ichida AdminUsers + AdminSegments reuse qilinadi (tablar bilan)
import AdminPeople from './pages/AdminPeople';
// AI Chat endi alohida sahifa emas — floating button (har sahifada ko'rinadi)
import AdminAIChatFloating from './components/AdminAIChatFloating';
import './admin.css';

const AdminApp = () => {
  const [token, setToken] = useState(() => sessionStorage.getItem('admin_token') || null);
  const [activePage, setActivePage] = useState('dashboard');
  const [pageProps, setPageProps] = useState({});
  const [isDark, setIsDark] = useState(() => {
    const saved = localStorage.getItem('admin_theme');
    return saved ? saved === 'dark' : true;
  });

  useEffect(() => {
    // Telegram WebApp expand
    if (window.Telegram?.WebApp) {
      const tg = window.Telegram.WebApp;
      tg.expand();
      try { tg.requestFullscreen?.(); } catch {}
    }
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
    localStorage.setItem('admin_theme', isDark ? 'dark' : 'light');
  }, [isDark]);

  useEffect(() => {
    if (!token) return;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/admin/ws?token=${token}`;
    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        // Custom event dispatcher to broadcast events across Admin components
        window.dispatchEvent(new CustomEvent('admin_ws_event', { detail: data }));
      } catch (e) {
        console.error("WS parse error", e);
      }
    };

    return () => {
      ws.close();
    };
  }, [token]);

  const handleThemeToggle = (mode) => {
    setIsDark(mode === 'dark');
  };

  const handleUnlock = (newToken) => {
    setToken(newToken);
  };

  const handleLogout = () => {
    sessionStorage.removeItem('admin_token');
    setToken(null);
  };

  const handleNavigate = (page, props = {}) => {
    setActivePage(page);
    setPageProps(props);
  };

  if (!token) {
    return <PinLock onUnlock={handleUnlock} />;
  }

  const renderPage = () => {
    switch (activePage) {
      case 'dashboard': return <AdminDashboard token={token} navigateTo={handleNavigate} {...pageProps} />;
      // Unified People sahifa (eski 'users' va 'segments' route'lari shu yerga keladi)
      case 'people':
      case 'users':
      case 'segments':
        return <AdminPeople token={token} navigateTo={handleNavigate} {...pageProps} />;
      case 'channels': return <AdminChannels token={token} navigateTo={handleNavigate} {...pageProps} />;
      case 'channel-stats': return <AdminChannelDetail token={token} navigateTo={handleNavigate} {...pageProps} />;
      case 'broadcast': return <AdminBroadcast token={token} navigateTo={handleNavigate} {...pageProps} />;
      // 'ai-chat' endi alohida sahifa emas — floating button. Eski URL'lar dashboard'ga qaytadi.
      case 'ai-chat': return <AdminDashboard token={token} navigateTo={handleNavigate} {...pageProps} />;
      case 'spending': return <AdminSpending token={token} navigateTo={handleNavigate} {...pageProps} />;
      case 'knowledge': return <AdminKnowledge token={token} navigateTo={handleNavigate} {...pageProps} />;
      case 'quick-actions': return <AdminQuickActions token={token} navigateTo={handleNavigate} {...pageProps} />;
      case 'settings': return <AdminSettings token={token} onThemeToggle={handleThemeToggle} isDark={isDark} navigateTo={handleNavigate} {...pageProps} />;
      default: return <AdminDashboard token={token} navigateTo={handleNavigate} {...pageProps} />;
    }
  };

  return (
    <>
      <AdminLayout
        activePage={activePage}
        onNavigate={handleNavigate}
        onLogout={handleLogout}
      >
        {renderPage()}
      </AdminLayout>
      {/* Floating AI Chat — har sahifada o'ng past burchakda ko'rinadi */}
      <AdminAIChatFloating token={token} />
    </>
  );
};

export default AdminApp;
