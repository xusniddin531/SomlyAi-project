import React, { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';
import { 
  Home, Search, Grid, CreditCard, Tag, ShieldAlert, Users, Bell, User,
  WifiOff, Wifi, AlertTriangle, RefreshCw 
} from 'lucide-react';
import { OfflineBanner } from './components/StateViews';
import DashboardPage from './pages/Dashboard';
import BalancesPage from './pages/Balances';
import StatisticsPage from './pages/Statistics';
import ProfilePage from './pages/Profile';
import CategoriesPage from './pages/Categories';
import DebtsPage from './pages/Debts';
import AnalyticsPage from './pages/Analytics';
import ReportsPage from './pages/Reports';
import GroupPage from './pages/GroupPage';
import RemindersPage from './pages/Reminders';
import SettingsPage from './pages/Settings';
import NotificationsPage from './pages/Notifications';
import PrivacyPage from './pages/Privacy';

import { wsService } from './utils/websocket';
import { fetchApi } from './utils/api';
import { useTranslation } from 'react-i18next';

import AdminApp from './admin/AdminApp';

const AppContent = ({ initData, isOffline, wasOffline, isSyncing }) => {
  const location = useLocation();
  const isAdmin = location.pathname.startsWith('/admin');

  if (isAdmin) {
    return <AdminApp />;
  }

  return (
    <div className="app-wrapper">
      <Sidebar />
      
      <div className="app-container">
        {/* Status Banners */}
        {isOffline && <OfflineBanner />}
        {wasOffline && !isOffline && (
          <div className="status-banner" style={{ background: isSyncing ? 'var(--warning)' : 'var(--success)' }}>
            {isSyncing ? <RefreshCw size={18} className="spin-animation" /> : <Wifi size={18} />}
            <span>{isSyncing ? "Yangilanmoqda..." : "Yangilandi"}</span>
          </div>
        )}

        <div className="main-content-scroll">
          <Routes>
            <Route path="/" element={<DashboardPage initData={initData} />} />
            <Route path="/balances" element={<BalancesPage initData={initData} />} />
            <Route path="/stats" element={<StatisticsPage initData={initData} />} />
            <Route path="/reports" element={<ReportsPage initData={initData} />} />
            <Route path="/categories" element={<CategoriesPage initData={initData} />} />
            <Route path="/profile" element={<ProfilePage initData={initData} />} />
            <Route path="/debts" element={<DebtsPage initData={initData} />} />
            <Route path="/reminders" element={<RemindersPage initData={initData} />} />
            <Route path="/analytics" element={<AnalyticsPage initData={initData} />} />
            <Route path="/group" element={<GroupPage initData={initData} />} />
            <Route path="/settings" element={<SettingsPage initData={initData} />} />
            <Route path="/notifications" element={<NotificationsPage initData={initData} />} />
            <Route path="/privacy" element={<PrivacyPage />} />
          </Routes>
        </div>

        <BottomNav />
      </div>
    </div>
  );
};

const App = () => {
  const [initData, setInitData] = useState('');
  const [isOffline, setIsOffline] = useState(!navigator.onLine);
  const [globalError, setGlobalError] = useState(false);
  const [wasOffline, setWasOffline] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const { t } = useTranslation();

  useEffect(() => {
    // Telegram Web App SDK init: Auto expand for full screen
    if (window.Telegram && window.Telegram.WebApp) {
      const tg = window.Telegram.WebApp;
      
      try {
        if (tg.requestFullscreen) {
          tg.requestFullscreen();
        }
      } catch (e) {
        console.log("requestFullscreen not supported");
      }
      
      tg.expand();
      tg.enableClosingConfirmation();
      setInitData(tg.initData);
      
      // Ensure it stays expanded on viewport changes
      const expandApp = () => {
        if (!tg.isExpanded) {
          tg.expand();
        }
      };
      
      tg.onEvent('viewportChanged', expandApp);
      
      // Ensure app stays expanded periodically
      const expandInterval = setInterval(expandApp, 2000);
      
      return () => {
        clearInterval(expandInterval);
      };
    }

    // Fetch user language settings
    const loadUserInfo = async () => {
      try {
        const data = await fetchApi('/user_info');
        if (data && data.language) {
          import('./i18n/i18n').then((module) => {
             module.default.changeLanguage(data.language);
          });
        }
      } catch (err) {
        console.error('Failed to load user info', err);
      }
    };
    loadUserInfo();

    const handleOnline = () => {
      setIsOffline(false);
      setWasOffline(true);
      setIsSyncing(true);
      wsService.connect();
      window.dispatchEvent(new Event('app_online'));
      setTimeout(() => {
        setIsSyncing(false);
        setTimeout(() => setWasOffline(false), 1000);
      }, 1000);
    };
    const handleOffline = () => {
      setIsOffline(true);
      setWasOffline(false);
      wsService.disconnect();
    };
    
    if (navigator.onLine) wsService.connect();

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    const handleApiError = () => setGlobalError(true);
    window.addEventListener('api_server_error', handleApiError);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      window.removeEventListener('api_server_error', handleApiError);
      wsService.disconnect();
    };
  }, []);

  // Theme Management
  useEffect(() => {
    const savedTheme = localStorage.getItem('user_theme');
    let defaultTheme = 'dark';
    if (savedTheme) {
      defaultTheme = savedTheme;
    } else if (window.Telegram?.WebApp?.colorScheme) {
      defaultTheme = window.Telegram.WebApp.colorScheme;
    } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
      defaultTheme = 'light';
    }
    
    document.documentElement.setAttribute('data-theme', defaultTheme);

    const handleThemeToggle = () => {
      const current = document.documentElement.getAttribute('data-theme') || 'dark';
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('user_theme', next);
      window.dispatchEvent(new CustomEvent('theme_changed', { detail: next }));
    };

    window.addEventListener('theme_toggle', handleThemeToggle);
    return () => window.removeEventListener('theme_toggle', handleThemeToggle);
  }, []);

  return (
    <BrowserRouter>
      <AppContent initData={initData} isOffline={isOffline} wasOffline={wasOffline} isSyncing={isSyncing} />
    </BrowserRouter>
  );
};

const Sidebar = () => {
  const location = useLocation();
  const { t } = useTranslation();

  return (
    <div className="sidebar">
      <div style={{ padding: '20px', display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div style={{ width: 32, height: 32, borderRadius: '8px', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <img src="/somly.jpg" alt="Somly AI Logo" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        </div>
        <h2 style={{ fontSize: '18px', margin: 0, fontWeight: 700 }}>Somly AI</h2>
      </div>

      <div style={{ flex: 1, padding: '0 12px' }}>
        <div className="sidebar-section-title" style={{ fontSize: '11px', color: 'var(--text-secondary)', padding: '12px', fontWeight: 600 }}>ASOSIY</div>
        <NavItem to="/" icon={<Home size={18} />} label="Bosh sahifa" active={location.pathname === '/'} />
        <NavItem to="/reports" icon={<Search size={18} />} label="Hisobotlar" active={location.pathname === '/reports'} />
        <NavItem to="/categories" icon={<Grid size={18} />} label="Kategoriyalar" active={location.pathname === '/categories'} />
        <NavItem to="/balances" icon={<CreditCard size={18} />} label="Balanslar" active={location.pathname === '/balances'} />

        <div className="sidebar-section-title" style={{ fontSize: '11px', color: 'var(--text-secondary)', padding: '12px', marginTop: '16px', fontWeight: 600 }}>MOLIYA</div>
        <NavItem to="/debts" icon={<Tag size={18} />} label="Qarzlar" active={location.pathname === '/debts'} />
        <NavItem to="/reminders" icon={<Bell size={18} />} label="Eslatmalar" active={location.pathname === '/reminders'} />
        <NavItem to="/analytics" icon={<ShieldAlert size={18} />} label="Tavsiyalar" active={location.pathname === '/analytics'} />
        <NavItem to="/group" icon={<Users size={18} />} label="Telegram guruh" active={location.pathname === '/group'} />
      </div>

      <Link to="/profile" style={{ textDecoration: 'none', color: 'inherit' }}>
        <div style={{ padding: '16px', borderTop: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }} className="clickable">
          <div style={{ width: 36, height: 36, background: 'var(--primary)', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontWeight: 'bold' }}>H</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: '14px', fontWeight: 600 }}>Husniddin</div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Profil</div>
          </div>
        </div>
      </Link>
    </div>
  );
};

const NavItem = ({ to, icon, label, active }) => (
  <Link to={to} className="clickable" style={{ 
    display: 'flex', alignItems: 'center', gap: '12px', padding: '10px 12px', 
    borderRadius: '8px', color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
    background: active ? 'var(--card)' : 'transparent',
    textDecoration: 'none', marginBottom: '4px', fontSize: '14px', fontWeight: 500
  }}>
    <span style={{ color: active ? 'var(--primary)' : 'inherit' }}>{icon}</span>
    {label}
  </Link>
);

const BottomNav = () => {
  const location = useLocation();
  const { t } = useTranslation();
  
  return (
    <div className="bottom-nav">
      <Link to="/" className={`nav-item clickable ${location.pathname === '/' ? 'active' : ''}`}>
        <Home size={22} />
        <span>Bosh sahifa</span>
      </Link>
      <Link to="/reports" className={`nav-item clickable ${location.pathname === '/reports' ? 'active' : ''}`}>
        <Search size={22} />
        <span>Hisobotlar</span>
      </Link>
      <Link to="/categories" className={`nav-item clickable ${location.pathname === '/categories' ? 'active' : ''}`}>
        <Grid size={22} />
        <span>Kategoriya</span>
      </Link>
      <Link to="/debts" className={`nav-item clickable ${location.pathname === '/debts' ? 'active' : ''}`}>
        <Tag size={22} />
        <span>Qarzlar</span>
      </Link>
      <Link to="/reminders" className={`nav-item clickable ${location.pathname === '/reminders' ? 'active' : ''}`}>
        <Bell size={22} />
        <span>Eslatmalar</span>
      </Link>
      <Link to="/profile" className={`nav-item clickable ${location.pathname === '/profile' ? 'active' : ''}`}>
        <User size={22} />
        <span>Profil</span>
      </Link>
    </div>
  );
};

export default App;
