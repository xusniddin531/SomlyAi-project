import React, { useState, useEffect } from 'react';
import { Users, CreditCard, MessageSquare, ArrowUpRight, Clock, Activity, Target } from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer,
  BarChart, Bar, PieChart, Pie, Cell
} from 'recharts';

const SkeletonCard = () => (
  <div className="stat-card skeleton-card">
    <div className="skeleton-line w60" /><div className="skeleton-line w40" /><div className="skeleton-line w80" />
  </div>
);

// Heatmap component
const ActivityHeatmap = ({ data }) => {
  const days = ['Du', 'Se', 'Ch', 'Pa', 'Ju', 'Sh', 'Ya'];
  const hours = Array.from({ length: 24 }, (_, i) => i);
  
  // Find max count for color scaling
  const maxCount = Math.max(...(data || []).map(d => d.count), 1);
  
  // Create 7x24 grid filled with 0s
  const grid = Array(7).fill(0).map(() => Array(24).fill(0));
  (data || []).forEach(d => {
    if (d.day >= 0 && d.day <= 6 && d.hour >= 0 && d.hour <= 23) {
      grid[d.day][d.hour] = d.count;
    }
  });

  const getColor = (count) => {
    if (count === 0) return 'var(--bg)';
    const intensity = Math.max(0.1, count / maxCount);
    return `rgba(16, 185, 129, ${intensity})`; // Emerald color
  };

  return (
    <div className="heatmap-container">
      <div className="heatmap-grid">
        <div className="heatmap-empty-corner"></div>
        {hours.map(h => (
          <div key={h} className="heatmap-header-x">{h}</div>
        ))}
        
        {days.map((day, dIdx) => (
          <React.Fragment key={day}>
            <div className="heatmap-header-y">{day}</div>
            {hours.map(hIdx => {
              const count = grid[dIdx][hIdx];
              return (
                <div 
                  key={`${dIdx}-${hIdx}`} 
                  className="heatmap-cell"
                  style={{ backgroundColor: getColor(count) }}
                  title={`${day} ${hIdx}:00 - ${count} xabar`}
                />
              );
            })}
          </React.Fragment>
        ))}
      </div>
      <div className="heatmap-legend">
        <span>Kam faol</span>
        <div className="heatmap-scale"></div>
        <span>Ko'p faol</span>
      </div>
    </div>
  );
};

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="chart-tooltip">
        <p className="label">{`${label}`}</p>
        <p className="intro" style={{ color: payload[0].color || 'var(--admin-primary)' }}>
          {`${payload[0].value} ta`}
        </p>
      </div>
    );
  }
  return null;
};

const AdminDashboard = ({ token }) => {
  const [stats, setStats] = useState(null);
  const [segments, setSegments] = useState(null);
  const [aiTop, setAiTop] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();

    const handleWsEvent = (e) => {
      const { event, data } = e.detail;
      if (event === 'new_user' || event === 'new_event') {
        // Debounce fetching slightly or just fetch
        fetchData();
      }
    };
    window.addEventListener('admin_ws_event', handleWsEvent);
    return () => window.removeEventListener('admin_ws_event', handleWsEvent);
  }, []);

  const fetchData = async () => {
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const [statsRes, segmentsRes, aiTopRes] = await Promise.all([
        fetch('/api/admin/dashboard', { headers }),
        fetch('/api/admin/segments', { headers }),
        fetch('/api/admin/ai-top-consumers?limit=10', { headers }),
      ]);

      setStats(await statsRes.json());
      setSegments(await segmentsRes.json());
      if (aiTopRes.ok) {
        const aiData = await aiTopRes.json();
        setAiTop(aiData.users || []);
      }
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  if (loading || !stats) {
    return (
      <div className="admin-page">
        <h1 className="page-title">📊 Dashboard</h1>
        <div className="stats-grid">{[1,2,3,4].map(i => <SkeletonCard key={i} />)}</div>
      </div>
    );
  }

  // Monthly trend calc
  const users30d = stats.users_growth_30d || [];
  const monthAdded = users30d.reduce((sum, day) => sum + day.count, 0);
  const trendPct = stats.total_users > 0 ? ((monthAdded / stats.total_users) * 100).toFixed(1) : 0;

  const cards = [
    { 
      label: 'Jami users', 
      value: stats.total_users?.toLocaleString() || '0', 
      sub: `↑ ${trendPct}% (oy)`, 
      icon: Users, 
      color: '#6366f1' 
    },
    { 
      label: 'Bugun yangi user', 
      value: `+${stats.today_users?.toLocaleString() || '0'}`, 
      sub: 'yangi user', 
      icon: ArrowUpRight, 
      color: '#10b981' 
    },
    { 
      label: 'Aktiv', 
      value: stats.active_users?.toLocaleString() || '0', 
      sub: '(7 kunda)', 
      icon: Activity, 
      color: '#3b82f6' 
    },
    { 
      label: 'Bugungi xabarlar', 
      value: stats.today_messages?.toLocaleString() || '0', 
      sub: 'xabarlar', 
      icon: MessageSquare, 
      color: '#f59e0b' 
    },
  ];

  // Pie chart data formatting
  const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];
  
  const langsData = Object.entries(stats.lang_breakdown || {})
    .map(([lang, count]) => ({ name: (lang || 'uz').toUpperCase(), value: count }));
    
  const ageData = (segments?.age_groups || []).map(a => ({ name: a.label, value: a.count }));

  const incomeData = [
    { name: "Yuqori", value: stats.income_levels?.high || 0 },
    { name: "O'rta", value: stats.income_levels?.medium || 0 },
    { name: "Past", value: stats.income_levels?.low || 0 }
  ].filter(d => d.value > 0);

  return (
    <div className="admin-page fade-in">
      <h1 className="page-title">📊 Dashboard</h1>

      {/* TOP KARTALAR */}
      <div className="stats-grid">
        {cards.map((c, i) => {
          const Icon = c.icon;
          return (
            <div className="stat-card dashboard-top-card" key={i} style={{ '--accent': c.color }}>
              <div className="stat-info">
                <span className="stat-label-flex">
                  <Icon size={18} color={c.color} /> {c.label}
                </span>
                <span className="stat-value-large">{c.value}</span>
                <span className="stat-sub">{c.sub}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="dashboard-charts-grid mt20">
        {/* LINE CHART */}
        <div className="card chart-card full-width">
          <h3>Yangi userlar (30 kun)</h3>
          <div className="chart-wrapper">
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={users30d} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
                <XAxis dataKey="date" stroke="var(--text-muted)" fontSize={12} tickLine={false} />
                <YAxis stroke="var(--text-muted)" fontSize={12} tickLine={false} axisLine={false} />
                <RechartsTooltip content={<CustomTooltip />} />
                <Line type="monotone" dataKey="count" stroke="#6366f1" strokeWidth={3} dot={false} activeDot={{ r: 6 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* BAR CHART: Messages */}
        <div className="card chart-card">
          <h3>Kunlik xabarlar (7 kun)</h3>
          <div className="chart-wrapper">
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={stats.messages_7d || []} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
                <XAxis dataKey="date" stroke="var(--text-muted)" fontSize={12} tickLine={false} />
                <YAxis stroke="var(--text-muted)" fontSize={12} tickLine={false} axisLine={false} />
                <RechartsTooltip content={<CustomTooltip />} />
                <Bar dataKey="count" fill="#10b981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* PIE CHARTS */}
        <div className="dashboard-pies">
          <div className="card chart-card pie">
            <h3>Til taqsimoti</h3>
            <div className="chart-wrapper pie-wrapper">
              <ResponsiveContainer width="100%" height={160}>
                <PieChart>
                  <Pie data={langsData} cx="50%" cy="50%" innerRadius={40} outerRadius={70} paddingAngle={5} dataKey="value">
                    {langsData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <RechartsTooltip content={<CustomTooltip />} />
                </PieChart>
              </ResponsiveContainer>
              <div className="pie-legend">
                {langsData.map((d, i) => (
                  <div className="legend-item" key={i}>
                    <span className="dot" style={{ background: COLORS[i % COLORS.length] }}></span>
                    <span>{d.name}: {d.value}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="card chart-card pie">
            <h3>Yosh guruhlari</h3>
            <div className="chart-wrapper pie-wrapper">
              <ResponsiveContainer width="100%" height={160}>
                <PieChart>
                  <Pie data={ageData} cx="50%" cy="50%" innerRadius={40} outerRadius={70} paddingAngle={5} dataKey="value">
                    {ageData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[(index+2) % COLORS.length]} />
                    ))}
                  </Pie>
                  <RechartsTooltip content={<CustomTooltip />} />
                </PieChart>
              </ResponsiveContainer>
              <div className="pie-legend">
                {ageData.map((d, i) => (
                  <div className="legend-item" key={i}>
                    <span className="dot" style={{ background: COLORS[(i+2) % COLORS.length] }}></span>
                    <span>{d.name}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="card chart-card pie">
            <h3>Daromad darajasi</h3>
            <div className="chart-wrapper pie-wrapper">
              {incomeData.length > 0 ? (
                <ResponsiveContainer width="100%" height={160}>
                  <PieChart>
                    <Pie data={incomeData} cx="50%" cy="50%" innerRadius={40} outerRadius={70} paddingAngle={5} dataKey="value">
                      {incomeData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[(index+4) % COLORS.length]} />
                      ))}
                    </Pie>
                    <RechartsTooltip content={<CustomTooltip />} />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <div className="empty-state flex-center" style={{height: 160}}>Yeterli ma'lumot yo'q</div>
              )}
              {incomeData.length > 0 && (
                <div className="pie-legend">
                  {incomeData.map((d, i) => (
                    <div className="legend-item" key={i}>
                      <span className="dot" style={{ background: COLORS[(i+4) % COLORS.length] }}></span>
                      <span>{d.name}: {d.value}%</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
        
        {/* BAR CHART: REGIONS */}
        <div className="card chart-card full-width">
          <h3>Viloyatlar bo'yicha</h3>
          <div className="regions-bars">
            {(segments?.regions || []).map((r, i) => {
              const maxReg = Math.max(...(segments?.regions || []).map(x => x.count), 1);
              const pct = (r.count / maxReg) * 100;
              return (
                <div className="region-row" key={i}>
                  <span className="reg-label">{r.label}</span>
                  <div className="reg-track">
                    <div className="reg-fill" style={{ width: `${pct}%`, backgroundColor: COLORS[i % COLORS.length] }}></div>
                  </div>
                  <span className="reg-val">{r.count}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* QIZIQISHLAR STATISTIKASI */}
      {stats.interest_stats && Object.keys(stats.interest_stats).length > 0 && (
        <div className="card mt20 full-width">
          <h3>❤️ Qiziqishlar statistikasi</h3>
          <div className="regions-bars">
            {Object.entries(stats.interest_stats).map(([interest, pct], i) => {
              const INTEREST_LABELS = {
                sport: '⚽ Sport', food: '🍔 Oziq-ovqat', fashion: '👗 Kiyim',
                travel: '✈️ Sayohat', education: '📚 Ta\'lim', entertainment: '🎬 O\'yin-kulgi',
                auto: '🚗 Mashina', health: '🏥 Sog\'liq'
              };
              return (
                <div className="region-row" key={interest}>
                  <span className="reg-label">{INTEREST_LABELS[interest] || interest}</span>
                  <div className="reg-track">
                    <div className="reg-fill" style={{ width: `${pct}%`, backgroundColor: COLORS[i % COLORS.length] }}></div>
                  </div>
                  <span className="reg-val">{pct}%</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* HEATMAP */}
      <div className="card mt20 full-width heatmap-card">
        <h3>🔥 Aktiv Vaqtlar (Heatmap)</h3>
        <p className="heatmap-desc">Foydalanuvchilar botdan qaysi soatlarda eng ko'p foydalanadi? (Reklama uchun mos vaqtni aniqlash)</p>
        <ActivityHeatmap data={stats.heatmap} />
        {stats.global_best_hour !== null && stats.global_best_hour !== undefined && (
          <div className="user-activity-summary" style={{marginTop: '12px', borderTop: '1px solid var(--border)', borderBottom: 'none', paddingTop: '12px'}}>
            <span>📊 Eng aktiv vaqt: <strong>{stats.global_best_hour}:00</strong></span>
            <span>📅 Eng aktiv kun: <strong>{stats.global_best_day}</strong></span>
            <span>💡 Reklama uchun tavsiya: <strong>{stats.global_best_hour}:00 — {(stats.global_best_hour + 1) % 24}:00</strong></span>
          </div>
        )}
      </div>

      {/* AI TOP CONSUMERS */}
      <div className="card mt20">
        <h3>🤖 AI Token Sarflovchilar (Top 10)</h3>
        <p style={{ margin: '-4px 0 12px', fontSize: '13px', color: 'var(--admin-text-secondary)' }}>
          Eng ko'p Gemini tokenini ishlatgan foydalanuvchilar
        </p>
        <table className="admin-table" style={{ width: '100%' }}>
          <thead>
            <tr>
              <th>#</th>
              <th>Foydalanuvchi</th>
              <th style={{ textAlign: 'right' }}>Jami token</th>
              <th style={{ textAlign: 'right' }}>So'rovlar</th>
              <th style={{ textAlign: 'right' }}>Oxirgi</th>
            </tr>
          </thead>
          <tbody>
            {aiTop.map((u, i) => (
              <tr key={u.telegram_id}>
                <td style={{ opacity: 0.5 }}>{i + 1}</td>
                <td>
                  <div>{u.full_name || '—'}{u.username ? <span style={{ color: 'var(--admin-primary)', marginLeft: 4 }}>@{u.username}</span> : null}</div>
                  <div style={{ fontSize: '11px', opacity: 0.5 }}>ID: {u.telegram_id}</div>
                </td>
                <td style={{ textAlign: 'right', fontWeight: 600 }}>{u.total_tokens.toLocaleString()}</td>
                <td style={{ textAlign: 'right', opacity: 0.7 }}>{u.request_count}</td>
                <td style={{ textAlign: 'right', opacity: 0.6, fontSize: '12px' }}>
                  {u.last_used ? new Date(u.last_used).toLocaleDateString() : '—'}
                </td>
              </tr>
            ))}
            {aiTop.length === 0 && (
              <tr>
                <td colSpan={5} style={{ textAlign: 'center', opacity: 0.4, padding: '16px 0' }}>
                  Hozircha ma'lumot yo'q
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* RECENT EVENTS */}
      <div className="card mt20 feed-card">
        <h3>⚡ Oxirgi hodisalar</h3>
        <div className="events-feed">
          {(stats.recent_events || []).map((ev, i) => (
            <div className="event-item" key={i}>
              <div className="event-icon">
                {ev.type === 'user' ? <Users size={16} /> : ev.type === 'channel' ? <Target size={16} /> : <Clock size={16} />}
              </div>
              <div className="event-content">
                <p>{ev.text}</p>
                <span>{ev.time}</span>
              </div>
            </div>
          ))}
          {(!stats.recent_events || stats.recent_events.length === 0) && (
            <p className="cell-muted">Hodisalar yo'q.</p>
          )}
        </div>
      </div>

    </div>
  );
};

export default AdminDashboard;
