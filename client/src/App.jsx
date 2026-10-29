import { useState, useEffect, useRef, useCallback } from 'react';
import './index.css';

// ─── Constants ───────────────────────────────────────────────────────────────

const APP_CLIENT_HEADER = 'desktop-ui';

const STEPS = [
  { id: 'setup',         label: 'Campaign Setup',  icon: '📋' },
  { id: 'contacts',      label: 'Upload Contacts', icon: '👥' },
  { id: 'preview',       label: 'Preview Drafts',  icon: '✉️' },
  { id: 'send',          label: 'Send & Export',   icon: '🚀' },
  { id: 'conversations', label: 'Conversations',   icon: '📬' },
];

const TONES = [
  { value: 'professional', label: 'Professional', desc: 'Formal and polished'   },
  { value: 'friendly',     label: 'Friendly',     desc: 'Warm and approachable' },
  { value: 'direct',       label: 'Direct',       desc: 'Brief and to the point'},
  { value: 'warm',         label: 'Warm',         desc: 'Personal and caring'   },
];

const EMAIL_TYPES = [
  { value: 'cold_outreach', label: 'Cold Outreach', desc: 'First-ever contact'         },
  { value: 'follow_up',     label: 'Follow-Up',     desc: 'After a previous reach-out' },
  { value: 'introduction',  label: 'Introduction',  desc: 'Who you are & why connect'  },
  { value: 'partnership',   label: 'Partnership',   desc: 'Win-win collaboration'       },
  { value: 'invitation',    label: 'Invitation',    desc: 'Event or meeting invite'     },
  { value: 're_engagement', label: 'Re-engagement', desc: 'Revive a cold contact'       },
];

const EMAIL_LENGTHS = [
  { value: 'punchy', label: 'Punchy', desc: '30–50 words · best for cold outreach' },
  { value: 'short',  label: 'Short',  desc: '60–90 words'    },
  { value: 'medium', label: 'Medium', desc: '150–200 words'  },
  { value: 'long',   label: 'Long',   desc: '280–340 words'  },
];

const DEFAULT_FORM = {
  mission: '', sender_name: '', sender_company: '',
  offer: '', call_to_action: 'would you be open to a quick 15-minute call next week',
  tone: 'professional', signature: '', google_meet_link: '', google_calendar_link: '', sender_email: '',
  email_type: 'cold_outreach', email_length: 'medium',
};

const STATUS_COLORS = {
  active:        'badge-active',
  progressing:   'badge-progressing',
  not_interested:'badge-closed',
  closed:        'badge-closed',
  limit_reached: 'badge-warn',
  out_of_office: 'badge-warn',
};

const STATUS_LABELS = {
  active:        'Active',
  progressing:   '🔥 Progressing',
  not_interested:'Not Interested',
  closed:        'Closed',
  limit_reached: 'Limit Reached',
};

async function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set('X-A1-Client', APP_CLIENT_HEADER);
  return fetch(url, { ...options, headers });
}

async function readJsonSafely(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

async function streamSseResponse(response, onEvent) {
  if (!response.ok) {
    const errorBody = await readJsonSafely(response);
    throw new Error(errorBody.error || `Request failed (${response.status})`);
  }
  if (!response.body) {
    throw new Error('Streaming response was empty.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (!line.startsWith('data:')) continue;
      onEvent(JSON.parse(line.slice(5).trim()));
    }
  }
}

// ─── Reusable components ──────────────────────────────────────────────────────

function Toast({ message, type, onClose }) {
  useEffect(() => { const t = setTimeout(onClose, 5000); return () => clearTimeout(t); }, [onClose]);
  return (
    <div className={`toast toast-${type}`}>
      <span>{type === 'success' ? '✅' : '❌'}</span>
      <span>{message}</span>
      <button onClick={onClose} className="toast-close">×</button>
    </div>
  );
}

function PendingReplyCard({ email, pending, onApprove, onCancel }) {
  const [timeLeft, setTimeLeft] = useState(0);
  const [editedBody, setEditedBody] = useState(pending.body);

  useEffect(() => {
    const generatedAt = new Date(pending.generated_at).getTime();
    const sendAfterMs = (Number(pending.auto_send_after_seconds) || (pending.classification === 'follow_up' ? 300 : 1800)) * 1000;
    const updateTime = () => {
      const now = Date.now();
      const diff = sendAfterMs - (now - generatedAt);
      setTimeLeft(Math.max(0, diff));
    };
    const kick = setTimeout(updateTime, 0);
    const int = setInterval(updateTime, 1000);
    return () => {
      clearTimeout(kick);
      clearInterval(int);
    };
  }, [pending.auto_send_after_seconds, pending.classification, pending.generated_at]);

  const mins = Math.floor(timeLeft / 60000);
  const secs = Math.floor((timeLeft % 60000) / 1000).toString().padStart(2, '0');

  return (
    <div className="conv-msg" style={{border: '2px solid var(--primary)', background: 'rgba(5, 150, 105, 0.05)', padding: '1rem', borderRadius: '8px', marginBottom: '1rem'}}>
      <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'0.5rem'}}>
        <strong>⏳ Draft Pending Approval</strong>
        <span style={{color: 'var(--primary)', fontWeight: 'bold'}}>
          Sends automatically in {mins}:{secs}
        </span>
      </div>
      <div>
        <label style={{fontSize:'0.8rem', fontWeight:'bold', color:'var(--muted)'}}>Subject: {pending.subject}</label>
      </div>
      <textarea
        style={{width:'100%', minHeight:'120px', marginTop:'0.5rem', padding:'0.5rem', borderRadius:'4px', border:'1px solid var(--border)'}}
        value={editedBody}
        onChange={e => setEditedBody(e.target.value)}
      />
      <div style={{display:'flex', gap:'0.5rem', marginTop:'0.5rem'}}>
        <button className="btn btn-primary btn-sm" onClick={() => onApprove(email, editedBody)}>✅ Approve & Send</button>
        <button className="btn btn-ghost btn-sm" onClick={() => onCancel(email)}>❌ Cancel</button>
      </div>
    </div>
  );
}

function StepIndicator({ steps, current, completed, onNavigate }) {
  return (
    <div className="step-indicator">
      {steps.map((step, i) => {
        const isDone   = completed.includes(step.id);
        const isActive = current === step.id;
        const canClick = isDone || step.id === 'conversations';
        return (
          <div key={step.id} className={`step-item ${isActive ? 'active' : ''} ${isDone ? 'done' : ''}`}>
            <button
              className="step-circle-btn"
              onClick={() => canClick && onNavigate(step.id)}
              style={{ cursor: canClick ? 'pointer' : 'default' }}
              title={canClick ? `Go to ${step.label}` : undefined}
            >
              <div className="step-circle">{isDone ? '✓' : step.icon}</div>
            </button>
            <span className="step-label">{step.label}</span>
            {i < steps.length - 1 && <div className={`step-line ${isDone ? 'done' : ''}`} />}
          </div>
        );
      })}
    </div>
  );
}

// ─── AI Settings Modal ───────────────────────────────────────────────────────

const OPENAI_MODELS   = ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'];
const CLAUDE_MODELS   = [
  'claude-opus-4-1-20250805',
  'claude-sonnet-4-20250514',
  'claude-3-7-sonnet-20250219',
  'claude-3-5-haiku-20241022',
];
const DEEPSEEK_MODELS = ['deepseek-chat', 'deepseek-reasoner'];
const QWEN_MODELS     = ['qwen-plus', 'qwen-turbo', 'qwen-max', 'qwen-long', 'qwen2.5-72b-instruct'];
const KIMI_MODELS     = ['moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k'];

const SMTP_PRESETS = [
  { label: 'Gmail',       host: 'smtp.gmail.com',        port: 587, security: 'starttls' },
  { label: 'Outlook',     host: 'smtp.office365.com',    port: 587, security: 'starttls' },
  { label: 'Yahoo',       host: 'smtp.mail.yahoo.com',   port: 587, security: 'starttls' },
  { label: 'Zoho',        host: 'smtp.zoho.com',         port: 587, security: 'starttls' },
  { label: 'SendGrid',    host: 'smtp.sendgrid.net',     port: 587, security: 'starttls' },
  { label: 'Mailgun',     host: 'smtp.mailgun.org',      port: 587, security: 'starttls' },
  { label: 'iCloud',      host: 'smtp.mail.me.com',      port: 587, security: 'starttls' },
  { label: 'ProtonMail',  host: '127.0.0.1',             port: 1025, security: 'starttls' },
  { label: 'Brevo',       host: 'smtp-relay.brevo.com',  port: 587, security: 'starttls' },
  { label: 'Amazon SES',  host: 'email-smtp.us-east-1.amazonaws.com', port: 587, security: 'starttls' },
];

function StatusBanner({ status }) {
  if (!status) return null;
  return (
    <div style={{
      padding:'0.65rem 1rem', borderRadius:'var(--radius-sm)',
      background: status.ok ? 'var(--success-bg)' : 'var(--error-bg)',
      color: status.ok ? 'var(--success)' : 'var(--error)',
      fontSize:'0.875rem', fontWeight:500,
    }}>{status.message}</div>
  );
}

function LoadingScreen({ message }) {
  return (
    <div className="auth-shell">
      <div className="auth-card">
        <div className="auth-brand">
          <div className="auth-logo">A1</div>
          <div>
            <h1>A1 Mail Dynamics</h1>
            <p>{message}</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function LicensePanel({ licenseState, onActivated, showLogout = false, onLogout = null }) {
  const [token, setToken] = useState('');
  const [status, setStatus] = useState(null);
  const [saving, setSaving] = useState(false);

  const activate = async () => {
    setSaving(true);
    setStatus(null);
    const res = await apiFetch('/api/license/activate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    }).then(r => r.json());
    setSaving(false);
    if (res.error) {
      setStatus({ ok: false, message: `❌ ${res.error}` });
      return;
    }
    setToken('');
    setStatus({ ok: true, message: '✅ License activated successfully.' });
    onActivated?.();
  };

  return (
    <div className="auth-panel">
      <div className="field-section">
        <h3>License Activation</h3>
        <p className="field-hint">Each customer uses their own AI and SMTP credentials. Your license controls access to the desktop software itself.</p>
      </div>

      <div className="license-status-card">
        <div><strong>Status</strong><span>{licenseState?.active ? 'Active' : 'Not Active'}</span></div>
        <div><strong>Machine ID</strong><code>{licenseState?.machine_id || 'Loading…'}</code></div>
        {licenseState?.customer_name && <div><strong>Licensed To</strong><span>{licenseState.customer_name}</span></div>}
        {licenseState?.customer_email && <div><strong>Email</strong><span>{licenseState.customer_email}</span></div>}
        {licenseState?.license_type && <div><strong>License Type</strong><span>{licenseState.license_type}</span></div>}
        {licenseState?.expires_at && <div><strong>Expires</strong><span>{new Date(licenseState.expires_at).toLocaleString()}</span></div>}
      </div>

      {!licenseState?.active && (
        <>
          {!licenseState?.configured && (
            <div className="inline-warning">
              Vendor license public key is not configured yet. Generate your signing keypair before shipping the app.
            </div>
          )}
          {licenseState?.reason && <div className="inline-warning">{licenseState.reason}</div>}

          <div className="field-group">
            <label>Activation Token</label>
            <textarea
              className="field-input field-textarea"
              rows={6}
              value={token}
              onChange={e => setToken(e.target.value)}
              placeholder="Paste the signed license token here"
            />
          </div>

          <div className="step-actions" style={{paddingTop:0, borderTop:'none', marginTop:0}}>
            <button className="btn btn-primary" onClick={activate} disabled={saving || !token.trim()}>
              {saving ? <span className="spinner" /> : 'Activate License'}
            </button>
            <button className="btn btn-outline" type="button" onClick={() => navigator.clipboard?.writeText(licenseState?.machine_id || '')}>
              Copy Machine ID
            </button>
            {showLogout && onLogout && <button className="btn btn-ghost" type="button" onClick={onLogout}>Sign Out</button>}
          </div>
        </>
      )}

      {status && <StatusBanner status={status} />}
    </div>
  );
}

function AccountSettingsPanel({ authState, refreshAuthStatus }) {
  const [accounts, setAccounts] = useState([]);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ username: '', email: '', name: '', password: '', role: 'member' });
  const [passwords, setPasswords] = useState({ current_password: '', new_password: '' });
  const isAdmin = authState?.user?.role === 'admin';

  const loadAccounts = useCallback(async () => {
    if (!isAdmin) return;
    const res = await fetch('/api/admin/accounts').then(r => r.json());
    if (!res.error) setAccounts(res.accounts || []);
  }, [isAdmin]);

  useEffect(() => {
    void loadAccounts();
  }, [loadAccounts]);

  const createNewAccount = async () => {
    setLoading(true);
    setStatus(null);
    const res = await apiFetch('/api/admin/accounts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    }).then(r => r.json());
    setLoading(false);
    if (res.error) {
      setStatus({ ok: false, message: `❌ ${res.error}` });
      return;
    }
    setAccounts(res.accounts || []);
    setForm({ username: '', email: '', name: '', password: '', role: 'member' });
    setStatus({ ok: true, message: '✅ Account created.' });
  };

  const removeAccount = async (username) => {
    const res = await apiFetch(`/api/admin/accounts/${encodeURIComponent(username)}`, { method: 'DELETE' }).then(r => r.json());
    if (res.error) {
      setStatus({ ok: false, message: `❌ ${res.error}` });
      return;
    }
    setAccounts(res.accounts || []);
    setStatus({ ok: true, message: '✅ Account removed.' });
  };

  const updatePassword = async () => {
    setLoading(true);
    setStatus(null);
    const res = await apiFetch('/api/auth/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(passwords),
    }).then(r => r.json());
    setLoading(false);
    if (res.error) {
      setStatus({ ok: false, message: `❌ ${res.error}` });
      return;
    }
    setPasswords({ current_password: '', new_password: '' });
    setStatus({ ok: true, message: '✅ Password updated.' });
    refreshAuthStatus?.();
  };

  return (
    <div className="auth-panel">
      <div className="field-section">
        <h3>Signed In Account</h3>
        <p className="field-hint">
          You are signed in as <strong>{authState?.user?.name || authState?.user?.display_name || authState?.user?.username}</strong>
          {authState?.user?.email ? ` (${authState.user.email})` : ''}
          {' '}({authState?.user?.role || 'member'}).
        </p>
      </div>

      <div className="field-row">
        <div className="field-group">
          <label>Current Password</label>
          <input className="field-input" type="password" value={passwords.current_password} onChange={e => setPasswords(p => ({ ...p, current_password: e.target.value }))} />
        </div>
        <div className="field-group">
          <label>New Password</label>
          <input className="field-input" type="password" value={passwords.new_password} onChange={e => setPasswords(p => ({ ...p, new_password: e.target.value }))} />
        </div>
      </div>
      <button className="btn btn-outline btn-sm" onClick={updatePassword} disabled={loading}>Update Password</button>

      {isAdmin && (
        <>
          <div className="field-section" style={{marginTop:'1rem'}}>
            <h3>Team Accounts</h3>
            <p className="field-hint">Create additional local accounts for this machine.</p>
          </div>

          <div className="accounts-list">
            {accounts.map(account => (
              <div key={account.username} className="account-row">
                <div>
                  <strong>{account.name || account.display_name || account.username}</strong>
                  <div className="account-meta">{account.username} · {account.email || 'no-email'} · {account.role}</div>
                </div>
                {account.username !== authState?.user?.username && (
                  <button className="btn btn-ghost btn-sm" onClick={() => removeAccount(account.username)}>Remove</button>
                )}
              </div>
            ))}
          </div>

          <div className="field-row">
            <div className="field-group">
              <label>Username</label>
              <input className="field-input" value={form.username} onChange={e => setForm(p => ({ ...p, username: e.target.value }))} />
            </div>
            <div className="field-group">
              <label>Email</label>
              <input className="field-input" type="email" value={form.email} onChange={e => setForm(p => ({ ...p, email: e.target.value }))} />
            </div>
          </div>
          <div className="field-row">
            <div className="field-group">
              <label>Name / Company Name</label>
              <input className="field-input" value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} />
            </div>
            <div className="field-group">
              <label>Password</label>
              <input className="field-input" type="password" value={form.password} onChange={e => setForm(p => ({ ...p, password: e.target.value }))} />
            </div>
          </div>
          <div className="field-row">
            <div className="field-group">
              <label>Role</label>
              <select className="field-input" value={form.role} onChange={e => setForm(p => ({ ...p, role: e.target.value }))}>
                <option value="member">Member</option>
                <option value="admin">Admin</option>
              </select>
            </div>
          </div>
          <button className="btn btn-primary btn-sm" onClick={createNewAccount} disabled={loading}>Create Account</button>
        </>
      )}

      {status && <StatusBanner status={status} />}
    </div>
  );
}

function AuthShell({ authState, setAuthState, refreshAuthStatus }) {
  const [mode, setMode] = useState(authState?.authenticated ? 'license' : 'welcome');
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [setupForm, setSetupForm] = useState({ username: '', email: '', name: '', password: '', confirm_password: '' });
  const [loginForm, setLoginForm] = useState({ username: '', password: '' });
  const canSignUp = Boolean(authState?.signup_enabled);
  const canLogin = !authState?.setup_required;
  const signupTitle = authState?.setup_required ? 'Create Owner Account' : 'Create Local Account';
  const signupHint = authState?.setup_required
    ? 'Create the first local admin account for this desktop install.'
    : 'Create a local account for this machine. Admins can still manage accounts later in Settings.';

  useEffect(() => {
    if (authState?.authenticated) setMode('license');
    else setMode('welcome');
  }, [authState]);

  const openMode = nextMode => {
    setStatus(null);
    setMode(nextMode);
  };

  const submitSetup = async () => {
    if (setupForm.password !== setupForm.confirm_password) {
      setStatus({ ok: false, message: '❌ Password confirmation does not match.' });
      return;
    }
    setLoading(true);
    setStatus(null);
    const res = await apiFetch('/api/auth/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(setupForm),
    }).then(r => r.json());
    setLoading(false);
    if (res.error) {
      setStatus({ ok: false, message: `❌ ${res.error}` });
      return;
    }
    setAuthState(res.status);
  };

  const submitLogin = async () => {
    setLoading(true);
    setStatus(null);
    const res = await apiFetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(loginForm),
    }).then(r => r.json());
    setLoading(false);
    if (res.error) {
      setStatus({ ok: false, message: `❌ ${res.error}` });
      return;
    }
    setAuthState(res.status);
  };

  const logout = async () => {
    await apiFetch('/api/auth/logout', { method: 'POST' });
    await refreshAuthStatus();
  };

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <div className="auth-brand">
          <div className="auth-logo">A1</div>
          <div>
            <h1>A1 Mail Dynamics</h1>
            <p>Local-first outreach software with customer-owned API keys.</p>
          </div>
        </div>

        {mode === 'welcome' && (
          <div className="auth-panel">
            <div className="field-section">
              <h3>Welcome</h3>
              <p className="field-hint">Choose how you want to open this machine’s local workspace.</p>
            </div>

            <div className="auth-choice-grid">
              <button
                type="button"
                className="auth-choice-card"
                onClick={() => openMode('setup')}
                disabled={!canSignUp}
              >
                <span className="auth-choice-tag">Sign Up</span>
                <strong>{signupTitle}</strong>
                <p>
                  {canSignUp
                    ? signupHint
                    : 'New account registration is disabled on this machine. Ask an admin to create your account.'}
                </p>
              </button>

              <button
                type="button"
                className="auth-choice-card"
                onClick={() => openMode('login')}
                disabled={!canLogin}
              >
                <span className="auth-choice-tag">Login</span>
                <strong>Sign In</strong>
                <p>
                  {canLogin
                    ? 'Use your existing local username or email plus password to continue.'
                    : 'Create the first owner account before anyone can sign in.'}
                </p>
              </button>
            </div>
          </div>
        )}

        {mode === 'setup' && (
          <form className="auth-panel" onSubmit={e => { e.preventDefault(); submitSetup(); }}>
            <div className="field-section">
              <h3>{signupTitle}</h3>
              <p className="field-hint">{signupHint}</p>
            </div>
            <div className="field-row">
              <div className="field-group">
                <label>Username</label>
                <input className="field-input" value={setupForm.username} onChange={e => setSetupForm(p => ({ ...p, username: e.target.value }))} />
              </div>
              <div className="field-group">
                <label>Email</label>
                <input className="field-input" type="email" value={setupForm.email} onChange={e => setSetupForm(p => ({ ...p, email: e.target.value }))} />
              </div>
            </div>
            <div className="field-row">
              <div className="field-group">
                <label>Name / Company Name</label>
                <input className="field-input" value={setupForm.name} onChange={e => setSetupForm(p => ({ ...p, name: e.target.value }))} />
              </div>
              <div className="field-group">
                <label>Password</label>
                <input className="field-input" type="password" value={setupForm.password} onChange={e => setSetupForm(p => ({ ...p, password: e.target.value }))} />
              </div>
            </div>
            <div className="field-row">
              <div className="field-group">
                <label>Confirm Password</label>
                <input className="field-input" type="password" value={setupForm.confirm_password} onChange={e => setSetupForm(p => ({ ...p, confirm_password: e.target.value }))} />
              </div>
            </div>
            <div className="auth-actions">
              <button className="btn btn-ghost" type="button" onClick={() => openMode('welcome')} disabled={loading}>
                Back
              </button>
              <button className="btn btn-primary" type="submit" disabled={loading}>
                {loading ? <span className="spinner" /> : (authState?.setup_required ? 'Create Owner Account' : 'Create Account')}
              </button>
            </div>
          </form>
        )}

        {mode === 'login' && (
          <form className="auth-panel" onSubmit={e => { e.preventDefault(); submitLogin(); }}>
            <div className="field-section">
              <h3>Sign In</h3>
              <p className="field-hint">Use your username or email plus password to open the app.</p>
            </div>
            <div className="field-group">
              <label>Username or Email</label>
              <input className="field-input" value={loginForm.username} onChange={e => setLoginForm(p => ({ ...p, username: e.target.value }))} />
            </div>
            <div className="field-group">
              <label>Password</label>
              <input className="field-input" type="password" value={loginForm.password} onChange={e => setLoginForm(p => ({ ...p, password: e.target.value }))} />
            </div>
            <div className="auth-actions">
              <button className="btn btn-ghost" type="button" onClick={() => openMode('welcome')} disabled={loading}>
                Back
              </button>
              <button className="btn btn-primary" type="submit" disabled={loading}>
                {loading ? <span className="spinner" /> : 'Sign In'}
              </button>
            </div>
          </form>
        )}

        {mode === 'license' && (
          <LicensePanel licenseState={authState?.license} onActivated={refreshAuthStatus} showLogout onLogout={logout} />
        )}

        {status && <StatusBanner status={status} />}
      </div>
    </div>
  );
}

function SettingsModal({ onClose, authState, refreshAuthStatus, onLogout }) {
  const [activeTab, setActiveTab]   = useState('ai');

  // AI state
  const [provider, setProvider]           = useState('ollama');
  const [ollamaUrl, setOllamaUrl]         = useState('http://localhost:11434');
  const [ollamaModel, setOllamaModel]     = useState('llama3.2');
  const [ollamaModels, setOllamaModels]   = useState([]);
  const [openaiKey, setOpenaiKey]         = useState('');
  const [openaiKeyHint, setOpenaiKeyHint] = useState('');
  const [openaiModel, setOpenaiModel]     = useState('gpt-4o-mini');
  const [claudeKey, setClaudeKey]         = useState('');
  const [claudeKeyHint, setClaudeKeyHint] = useState('');
  const [claudeModel, setClaudeModel]     = useState('claude-3-5-haiku-20241022');
  const [deepseekKey, setDeepseekKey]         = useState('');
  const [deepseekKeyHint, setDeepseekKeyHint] = useState('');
  const [deepseekModel, setDeepseekModel]     = useState('deepseek-chat');
  const [qwenKey, setQwenKey]             = useState('');
  const [qwenKeyHint, setQwenKeyHint]     = useState('');
  const [qwenModel, setQwenModel]         = useState('qwen-plus');
  const [kimiKey, setKimiKey]             = useState('');
  const [kimiKeyHint, setKimiKeyHint]     = useState('');
  const [kimiModel, setKimiModel]         = useState('moonshot-v1-8k');

  // SMTP state
  const [smtpHost, setSmtpHost]               = useState('');
  const [smtpPort, setSmtpPort]               = useState(587);
  const [smtpUsername, setSmtpUsername]       = useState('');
  const [smtpPassword, setSmtpPassword]       = useState('');
  const [smtpPasswordHint, setSmtpPasswordHint] = useState('');
  const [smtpSecurity, setSmtpSecurity]       = useState('starttls');

  // Desktop state
  const [desktopSupported, setDesktopSupported] = useState(false);
  const [desktopPlatform, setDesktopPlatform]   = useState('');
  const [backgroundLaunchEnabled, setBackgroundLaunchEnabled] = useState(false);
  const [desktopStatus, setDesktopStatus]       = useState(null);
  const [desktopSaving, setDesktopSaving]       = useState(false);

  const [aiStatus, setAiStatus]       = useState(null);
  const [smtpStatus, setSmtpStatus]   = useState(null);
  const [aiSaving, setAiSaving]       = useState(false);
  const [smtpSaving, setSmtpSaving]   = useState(false);
  const [aiTesting, setAiTesting]     = useState(false);
  const [smtpTesting, setSmtpTesting] = useState(false);
  const [fetching, setFetching]       = useState(false);

  useEffect(() => {
    fetch('/api/settings/ai').then(r => r.json()).then(d => {
      setProvider(d.provider || 'ollama');
      setOllamaUrl(d.ollama_base_url || 'http://localhost:11434');
      setOllamaModel(d.ollama_model || 'llama3.2');
      setOpenaiKeyHint(d.openai_key_hint || '');
      setOpenaiModel(d.openai_model || 'gpt-4o-mini');
      setClaudeKeyHint(d.claude_key_hint || '');
      setClaudeModel(d.claude_model || 'claude-3-5-haiku-20241022');
      setDeepseekKeyHint(d.deepseek_key_hint || '');
      setDeepseekModel(d.deepseek_model || 'deepseek-chat');
      setQwenKeyHint(d.qwen_key_hint || '');
      setQwenModel(d.qwen_model || 'qwen-plus');
      setKimiKeyHint(d.kimi_key_hint || '');
      setKimiModel(d.kimi_model || 'moonshot-v1-8k');
    });
    fetch('/api/settings/smtp').then(r => r.json()).then(d => {
      setSmtpHost(d.host || '');
      setSmtpPort(d.port || 587);
      setSmtpUsername(d.username || '');
      setSmtpPasswordHint(d.password_hint || '');
      setSmtpSecurity(d.security || 'starttls');
    });
    fetch('/api/settings/desktop').then(r => r.json()).then(d => {
      setDesktopSupported(Boolean(d.supported));
      setDesktopPlatform(d.platform || '');
      setBackgroundLaunchEnabled(Boolean(d.background_launch_enabled));
    });
  }, []);

  const fetchOllamaModels = async () => {
    setFetching(true); setAiStatus(null);
    const res = await fetch('/api/settings/ai/models').then(r => r.json());
    if (res.ok && res.models.length) {
      setOllamaModels(res.models);
      if (!res.models.includes(ollamaModel)) setOllamaModel(res.models[0]);
      setAiStatus({ ok: true, message: `✅ Found ${res.models.length} model(s) on your Ollama server.` });
    } else {
      setAiStatus({ ok: false, message: `❌ ${res.error || 'No models found — is Ollama running?'}` });
    }
    setFetching(false);
  };

  const testAiConnection = async () => {
    setAiTesting(true); setAiStatus(null);
    const res = await fetch('/api/settings/ai/test').then(r => r.json());
    if (res.ok) {
      setAiStatus({ ok: true, message: `✅ Connected to ${res.provider}! Model: ${res.models?.[0] || '—'}` });
      if (res.models?.length) setOllamaModels(res.models);
    } else {
      setAiStatus({ ok: false, message: `❌ ${res.error}` });
    }
    setAiTesting(false);
  };

  const handleAiSave = async () => {
    setAiSaving(true); setAiStatus(null);
    const body = { provider };
    if (provider === 'ollama') {
      body.ollama_base_url = ollamaUrl;
      body.ollama_model    = ollamaModel;
    } else if (provider === 'openai') {
      body.openai_api_key = openaiKey;
      body.openai_model   = openaiModel;
    } else if (provider === 'claude') {
      body.claude_api_key = claudeKey;
      body.claude_model   = claudeModel;
    } else if (provider === 'deepseek') {
      body.deepseek_api_key = deepseekKey;
      body.deepseek_model   = deepseekModel;
    } else if (provider === 'qwen') {
      body.qwen_api_key = qwenKey;
      body.qwen_model   = qwenModel;
    } else if (provider === 'kimi') {
      body.kimi_api_key = kimiKey;
      body.kimi_model   = kimiModel;
    }
    const res = await apiFetch('/api/settings/ai', {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body),
    }).then(r => r.json());
    setAiSaving(false);
    if (res.error) setAiStatus({ ok: false, message: `❌ ${res.error}` });
    else setAiStatus({ ok: true, message: '✅ AI settings saved.' });
  };

  const applySmtpPreset = (preset) => {
    setSmtpHost(preset.host);
    setSmtpPort(preset.port);
    setSmtpSecurity(preset.security);
    setSmtpStatus(null);
  };

  const smtpPayload = {
    host: smtpHost,
    port: Number(smtpPort) || 0,
    username: smtpUsername,
    password: smtpPassword,
    security: smtpSecurity,
  };

  const testSmtpConnection = async () => {
    setSmtpTesting(true); setSmtpStatus(null);
    const res = await apiFetch('/api/settings/smtp/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(smtpPayload),
    }).then(r => r.json());
    setSmtpTesting(false);
    if (res.ok) setSmtpStatus({ ok: true, message: `✅ ${res.message}` });
    else setSmtpStatus({ ok: false, message: `❌ ${res.error}` });
  };

  const handleSmtpSave = async () => {
    setSmtpSaving(true); setSmtpStatus(null);
    const res = await apiFetch('/api/settings/smtp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(smtpPayload),
    }).then(r => r.json());
    setSmtpSaving(false);
    if (res.error) {
      setSmtpStatus({ ok: false, message: `❌ ${res.error}` });
      return;
    }
    setSmtpPassword('');
    setSmtpPasswordHint(res.settings?.password_hint || smtpPasswordHint);
    setSmtpStatus({ ok: true, message: '✅ SMTP settings saved.' });
  };

  const handleDesktopToggle = async (nextValue) => {
    setBackgroundLaunchEnabled(nextValue);
    setDesktopSaving(true);
    setDesktopStatus(null);
    const res = await apiFetch('/api/settings/desktop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ background_launch_enabled: nextValue }),
    }).then(r => r.json());
    setDesktopSaving(false);
    if (res.error) {
      setBackgroundLaunchEnabled(!nextValue);
      setDesktopStatus({ ok: false, message: `❌ ${res.error}` });
      return;
    }
    setDesktopSupported(Boolean(res.supported));
    setDesktopPlatform(res.platform || '');
    setBackgroundLaunchEnabled(Boolean(res.background_launch_enabled));
    setDesktopStatus({ ok: true, message: `✅ ${res.message}` });
  };

  const AI_PROVIDERS = [
    { v:'ollama',   icon:'🦙', label:'Ollama' },
    { v:'openai',   icon:'✨', label:'OpenAI' },
    { v:'claude',   icon:'🧠', label:'Claude' },
    { v:'deepseek', icon:'🔷', label:'DeepSeek' },
    { v:'qwen',     icon:'🌐', label:'Qwen' },
    { v:'kimi',     icon:'🌙', label:'Kimi' },
  ];

  return (
    <div className="gmail-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="gmail-modal" style={{ maxWidth: 660 }}>
        <div className="gmail-modal-header">
          <span className="gmail-modal-icon">⚙️</span>
          <div><h3>Settings</h3><p>Configure AI, SMTP, accounts, and licensing in one place</p></div>
          <button onClick={onClose} style={{marginLeft:'auto',background:'none',border:'none',fontSize:'1.4rem',cursor:'pointer',color:'var(--muted)'}}>×</button>
        </div>

        <div style={{display:'flex',gap:'0.75rem',marginTop:'1.25rem'}}>
          {[{v:'ai',icon:'🧠',label:'AI'},{v:'smtp',icon:'📨',label:'SMTP'},{v:'desktop',icon:'🖥️',label:'Desktop'},{v:'accounts',icon:'👤',label:'Accounts'},{v:'license',icon:'🔐',label:'License'}].map(section=>(
            <button key={section.v} onClick={()=>setActiveTab(section.v)} style={{
              flex:1, padding:'0.75rem', borderRadius:'var(--radius-sm)', cursor:'pointer',
              border: activeTab===section.v ? '2px solid var(--accent)' : '2px solid var(--border)',
              background: activeTab===section.v ? 'var(--accent-light)' : 'var(--surface)',
              fontWeight: activeTab===section.v ? 700 : 400,
              color: activeTab===section.v ? 'var(--accent-dark)' : 'var(--ink)',
            }}>{section.icon} {section.label}</button>
          ))}
        </div>

        <div style={{display:'flex',flexDirection:'column',gap:'1.1rem',marginTop:'1.25rem'}}>
          {activeTab === 'ai' ? (
            <>
              {/* Provider selector — 2 rows of 3 */}
              <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:'0.5rem'}}>
                {AI_PROVIDERS.map(p=>(
                  <button key={p.v} onClick={()=>setProvider(p.v)} style={{
                    padding:'0.6rem 0.5rem', borderRadius:'var(--radius-sm)', cursor:'pointer',
                    border: provider===p.v ? '2px solid var(--accent)' : '2px solid var(--border)',
                    background: provider===p.v ? 'var(--accent-light)' : 'var(--surface)',
                    fontWeight: provider===p.v ? 700 : 400,
                    color: provider===p.v ? 'var(--accent-dark)' : 'var(--ink)',
                    fontSize:'0.85rem',
                  }}>{p.icon} {p.label}</button>
                ))}
              </div>

              {provider === 'ollama' ? (<>
                <div className="field-group" style={{margin:0}}>
                  <label>Ollama Server URL</label>
                  <div style={{display:'flex',gap:'0.5rem'}}>
                    <input className="field-input" style={{flex:1}} value={ollamaUrl}
                      onChange={e=>setOllamaUrl(e.target.value)} placeholder="http://localhost:11434" />
                    <button className="btn btn-outline btn-sm" onClick={testAiConnection} disabled={aiTesting}>
                      {aiTesting ? <span className="spinner"/> : '🔌 Test'}
                    </button>
                  </div>
                </div>
                <div className="field-group" style={{margin:0}}>
                  <label>Model</label>
                  <div style={{display:'flex',gap:'0.5rem'}}>
                    {ollamaModels.length > 0
                      ? <select className="field-input" style={{flex:1}} value={ollamaModel} onChange={e=>setOllamaModel(e.target.value)}>
                          {ollamaModels.map(m=><option key={m} value={m}>{m}</option>)}
                        </select>
                      : <input className="field-input" style={{flex:1}} value={ollamaModel}
                          onChange={e=>setOllamaModel(e.target.value)} placeholder="llama3.2" />
                    }
                    <button className="btn btn-outline btn-sm" onClick={fetchOllamaModels} disabled={fetching} title="Load installed models">
                      {fetching ? <span className="spinner"/> : '🔄 Fetch'}
                    </button>
                  </div>
                  <p className="field-hint" style={{marginTop:'0.3rem'}}>Click Fetch to see all models pulled on your server.</p>
                </div>
                <div style={{background:'var(--surface-alt)',border:'1px solid var(--border)',borderRadius:'var(--radius-sm)',padding:'0.7rem 1rem',fontSize:'0.8rem',color:'var(--muted)'}}>
                  <strong>Quick start:</strong> Install from <a href="https://ollama.com" target="_blank" rel="noreferrer" style={{color:'var(--accent)'}}>ollama.com</a>
                  {' · '}<code>ollama serve</code>{' · '}<code>ollama pull llama3.2</code>
                </div>
              </>) : provider === 'openai' ? (<>
                <div className="field-group" style={{margin:0}}>
                  <label>API Key {openaiKeyHint && <span style={{color:'var(--muted)',fontWeight:400,fontSize:'0.8rem'}}>current: {openaiKeyHint}</span>}</label>
                  <input className="field-input" type="password" value={openaiKey}
                    onChange={e=>setOpenaiKey(e.target.value)}
                    placeholder={openaiKeyHint ? 'Enter new key to replace, or leave blank to keep' : 'sk-…'} />
                </div>
                <div className="field-group" style={{margin:0}}>
                  <label>Model</label>
                  <select className="field-input" value={openaiModel} onChange={e=>setOpenaiModel(e.target.value)}>
                    {OPENAI_MODELS.map(m=><option key={m} value={m}>{m}</option>)}
                  </select>
                </div>
                <div style={{background:'var(--surface-alt)',border:'1px solid var(--border)',borderRadius:'var(--radius-sm)',padding:'0.7rem 1rem',fontSize:'0.8rem',color:'var(--muted)'}}>
                  Get your key at <a href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer" style={{color:'var(--accent)'}}>platform.openai.com/api-keys</a>
                </div>
              </>) : provider === 'claude' ? (<>
                <div className="field-group" style={{margin:0}}>
                  <label>API Key {claudeKeyHint && <span style={{color:'var(--muted)',fontWeight:400,fontSize:'0.8rem'}}>current: {claudeKeyHint}</span>}</label>
                  <input className="field-input" type="password" value={claudeKey}
                    onChange={e=>setClaudeKey(e.target.value)}
                    placeholder={claudeKeyHint ? 'Enter new key to replace, or leave blank to keep' : 'sk-ant-…'} />
                </div>
                <div className="field-group" style={{margin:0}}>
                  <label>Model</label>
                  <select className="field-input" value={claudeModel} onChange={e=>setClaudeModel(e.target.value)}>
                    {CLAUDE_MODELS.map(m=><option key={m} value={m}>{m}</option>)}
                  </select>
                </div>
                <div style={{background:'var(--surface-alt)',border:'1px solid var(--border)',borderRadius:'var(--radius-sm)',padding:'0.7rem 1rem',fontSize:'0.8rem',color:'var(--muted)'}}>
                  Get your key at <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noreferrer" style={{color:'var(--accent)'}}>console.anthropic.com/settings/keys</a>
                </div>
              </>) : provider === 'deepseek' ? (<>
                <div className="field-group" style={{margin:0}}>
                  <label>API Key {deepseekKeyHint && <span style={{color:'var(--muted)',fontWeight:400,fontSize:'0.8rem'}}>current: {deepseekKeyHint}</span>}</label>
                  <input className="field-input" type="password" value={deepseekKey}
                    onChange={e=>setDeepseekKey(e.target.value)}
                    placeholder={deepseekKeyHint ? 'Enter new key to replace, or leave blank to keep' : 'sk-…'} />
                </div>
                <div className="field-group" style={{margin:0}}>
                  <label>Model</label>
                  <select className="field-input" value={deepseekModel} onChange={e=>setDeepseekModel(e.target.value)}>
                    {DEEPSEEK_MODELS.map(m=><option key={m} value={m}>{m}</option>)}
                  </select>
                </div>
                <div style={{background:'var(--surface-alt)',border:'1px solid var(--border)',borderRadius:'var(--radius-sm)',padding:'0.7rem 1rem',fontSize:'0.8rem',color:'var(--muted)'}}>
                  Get your key at <a href="https://platform.deepseek.com/api_keys" target="_blank" rel="noreferrer" style={{color:'var(--accent)'}}>platform.deepseek.com</a>
                  {' · '}<strong>deepseek-chat</strong> = V3 (fast & cheap) · <strong>deepseek-reasoner</strong> = R1 (reasoning)
                </div>
              </>) : provider === 'qwen' ? (<>
                <div className="field-group" style={{margin:0}}>
                  <label>API Key {qwenKeyHint && <span style={{color:'var(--muted)',fontWeight:400,fontSize:'0.8rem'}}>current: {qwenKeyHint}</span>}</label>
                  <input className="field-input" type="password" value={qwenKey}
                    onChange={e=>setQwenKey(e.target.value)}
                    placeholder={qwenKeyHint ? 'Enter new key to replace, or leave blank to keep' : 'sk-…'} />
                </div>
                <div className="field-group" style={{margin:0}}>
                  <label>Model</label>
                  <select className="field-input" value={qwenModel} onChange={e=>setQwenModel(e.target.value)}>
                    {QWEN_MODELS.map(m=><option key={m} value={m}>{m}</option>)}
                  </select>
                </div>
                <div style={{background:'var(--surface-alt)',border:'1px solid var(--border)',borderRadius:'var(--radius-sm)',padding:'0.7rem 1rem',fontSize:'0.8rem',color:'var(--muted)'}}>
                  Get your key at <a href="https://dashscope.console.aliyun.com/apiKey" target="_blank" rel="noreferrer" style={{color:'var(--accent)'}}>DashScope Console</a>
                  {' · '}<strong>qwen-plus</strong> recommended · uses Alibaba DashScope API
                </div>
              </>) : (<>
                <div className="field-group" style={{margin:0}}>
                  <label>API Key {kimiKeyHint && <span style={{color:'var(--muted)',fontWeight:400,fontSize:'0.8rem'}}>current: {kimiKeyHint}</span>}</label>
                  <input className="field-input" type="password" value={kimiKey}
                    onChange={e=>setKimiKey(e.target.value)}
                    placeholder={kimiKeyHint ? 'Enter new key to replace, or leave blank to keep' : 'sk-…'} />
                </div>
                <div className="field-group" style={{margin:0}}>
                  <label>Model</label>
                  <select className="field-input" value={kimiModel} onChange={e=>setKimiModel(e.target.value)}>
                    {KIMI_MODELS.map(m=><option key={m} value={m}>{m}</option>)}
                  </select>
                </div>
                <div style={{background:'var(--surface-alt)',border:'1px solid var(--border)',borderRadius:'var(--radius-sm)',padding:'0.7rem 1rem',fontSize:'0.8rem',color:'var(--muted)'}}>
                  Get your key at <a href="https://platform.moonshot.cn/console/api-keys" target="_blank" rel="noreferrer" style={{color:'var(--accent)'}}>platform.moonshot.cn</a>
                  {' · '}<strong>moonshot-v1-8k</strong> (fast) · <strong>moonshot-v1-128k</strong> (long context)
                </div>
              </>)}

              <StatusBanner status={aiStatus} />

              <div style={{display:'flex',justifyContent:'flex-end',gap:'0.75rem'}}>
                <button className="btn btn-primary" onClick={handleAiSave} disabled={aiSaving}>
                  {aiSaving ? <><span className="spinner"/> Saving…</> : '💾 Save AI Settings'}
                </button>
              </div>
            </>
          ) : activeTab === 'smtp' ? (
            <>
              {/* Provider presets */}
              <div>
                <label style={{fontSize:'0.8rem',fontWeight:600,color:'var(--muted)',display:'block',marginBottom:'0.4rem'}}>Quick Presets</label>
                <div style={{display:'flex',flexWrap:'wrap',gap:'0.4rem'}}>
                  {SMTP_PRESETS.map(p=>(
                    <button key={p.label} onClick={()=>applySmtpPreset(p)}
                      style={{padding:'0.3rem 0.7rem',fontSize:'0.78rem',borderRadius:'var(--radius-sm)',
                        border:'1px solid var(--border)',background:'var(--surface)',cursor:'pointer',
                        color:'var(--ink)'}}>
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="field-group" style={{margin:0}}>
                <label>SMTP Host</label>
                <input className="field-input" value={smtpHost}
                  onChange={e=>setSmtpHost(e.target.value)} placeholder="smtp.example.com" />
              </div>

              <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:'0.75rem'}}>
                <div className="field-group" style={{margin:0}}>
                  <label>Port</label>
                  <input className="field-input" type="number" min={1} max={65535} value={smtpPort}
                    onChange={e=>setSmtpPort(e.target.value)} placeholder="587" />
                </div>
                <div className="field-group" style={{margin:0}}>
                  <label>Security</label>
                  <select className="field-input" value={smtpSecurity} onChange={e=>setSmtpSecurity(e.target.value)}>
                    <option value="starttls">STARTTLS (port 587 — most providers)</option>
                    <option value="ssl">SSL / TLS (port 465 — implicit)</option>
                    <option value="none">None (port 25 — internal relay only)</option>
                  </select>
                </div>
              </div>

              <div className="field-group" style={{margin:0}}>
                <label>SMTP Username / Email</label>
                <input className="field-input" value={smtpUsername}
                  onChange={e=>setSmtpUsername(e.target.value)} placeholder="you@example.com" />
              </div>

              <div className="field-group" style={{margin:0}}>
                <label>Password {smtpPasswordHint && <span style={{color:'var(--muted)',fontWeight:400,fontSize:'0.8rem'}}>current: {smtpPasswordHint}</span>}</label>
                <input className="field-input" type="password" value={smtpPassword}
                  onChange={e=>setSmtpPassword(e.target.value)}
                  placeholder={smtpPasswordHint ? 'Enter new password to replace, or leave blank to keep' : 'App password or mailbox password'} />
                <p className="field-hint" style={{marginTop:'0.3rem'}}>
                  Gmail / Yahoo / Outlook require an <strong>App Password</strong> (not your login password) when 2FA is enabled.
                </p>
              </div>

              <StatusBanner status={smtpStatus} />

              <div style={{display:'flex',justifyContent:'flex-end',gap:'0.75rem',flexWrap:'wrap'}}>
                <button className="btn btn-outline" onClick={testSmtpConnection} disabled={smtpTesting}>
                  {smtpTesting ? <><span className="spinner"/> Testing…</> : '🔌 Test SMTP'}
                </button>
                <button className="btn btn-primary" onClick={handleSmtpSave} disabled={smtpSaving}>
                  {smtpSaving ? <><span className="spinner"/> Saving…</> : '💾 Save SMTP Settings'}
                </button>
              </div>
            </>
          ) : activeTab === 'desktop' ? (
            <>
              <div className="auth-panel">
                <div className="field-section">
                  <h3>Desktop Startup</h3>
                  <p className="field-hint">
                    Turn this on if you want A1 Mail Dynamics to start in the background every time you sign in to Windows.
                  </p>
                </div>

                <div style={{
                  display:'flex', justifyContent:'space-between', alignItems:'center', gap:'1rem',
                  padding:'1rem', border:'1px solid var(--border)', borderRadius:'var(--radius-sm)',
                  background:'var(--surface-alt)',
                }}>
                  <div>
                    <strong style={{display:'block', marginBottom:'0.25rem'}}>Run in background at sign-in</strong>
                    <span style={{fontSize:'0.85rem', color:'var(--muted)'}}>
                      {desktopSupported
                        ? 'The app will create or remove your Windows Startup shortcut automatically.'
                        : `This setting is only available on Windows packaged installs. Current platform: ${desktopPlatform || 'unknown'}.`}
                    </span>
                  </div>
                  <label style={{display:'flex', alignItems:'center', gap:'0.6rem', cursor: desktopSupported ? 'pointer' : 'not-allowed'}}>
                    <input
                      type="checkbox"
                      checked={backgroundLaunchEnabled}
                      disabled={!desktopSupported || desktopSaving}
                      onChange={e => handleDesktopToggle(e.target.checked)}
                      style={{width:18, height:18}}
                    />
                    <span style={{fontWeight:700, color: backgroundLaunchEnabled ? 'var(--success)' : 'var(--muted)'}}>
                      {backgroundLaunchEnabled ? 'ON' : 'OFF'}
                    </span>
                  </label>
                </div>

                <div style={{background:'var(--surface-alt)',border:'1px solid var(--border)',borderRadius:'var(--radius-sm)',padding:'0.7rem 1rem',fontSize:'0.8rem',color:'var(--muted)'}}>
                  When background startup is enabled, launching the app again will reconnect to the running instance instead of looking like a failed `.exe` start.
                </div>

                {desktopSaving && <div style={{display:'flex', justifyContent:'flex-end'}}><span className="spinner" /></div>}
                <StatusBanner status={desktopStatus} />
              </div>
            </>
          ) : activeTab === 'accounts' ? (
            <AccountSettingsPanel authState={authState} refreshAuthStatus={refreshAuthStatus} />
          ) : (
            <div className="auth-panel">
              <LicensePanel licenseState={authState?.license} onActivated={refreshAuthStatus} />
              <div className="step-actions" style={{paddingTop:0, borderTop:'none', marginTop:0}}>
                <button className="btn btn-ghost" onClick={onLogout}>Sign Out</button>
              </div>
            </div>
          )}
        </div>

        <div style={{display:'flex',justifyContent:'flex-end',gap:'0.75rem',marginTop:'1.5rem'}}>
          <button className="btn btn-ghost" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

// ─── Attachment Manager ───────────────────────────────────────────────────────

function AttachmentManager({ attachments, onUpload, onDelete }) {
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef();

  const upload = async (file) => {
    if (!file) return;
    setUploading(true); setError('');
    const fd = new FormData(); fd.append('file', file);
    const res = await apiFetch('/api/attachments/upload', { method:'POST', body: fd }).then(r => r.json());
    setUploading(false);
    if (res.error) setError(res.error);
    else onUpload(res.attachments);
  };

  const handleDrop = (e) => {
    e.preventDefault(); setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) upload(file);
  };

  return (
    <div>
      <div
        className={`drop-zone ${dragOver?'drag-over':''}`}
        style={{padding:'1rem', minHeight:'70px'}}
        onDragOver={e=>{e.preventDefault();setDragOver(true);}}
        onDragLeave={()=>setDragOver(false)}
        onDrop={handleDrop}
        onClick={()=>inputRef.current.click()}
      >
        <input ref={inputRef} type="file" style={{display:'none'}}
          onChange={e=>upload(e.target.files[0])} />
        {uploading
          ? <><span className="spinner"/> Uploading…</>
          : <><div className="drop-icon" style={{fontSize:'1.5rem'}}>📎</div>
             <strong>Attach a file</strong>
             <span className="drop-sub">PDF, Word, Excel, image… (max 20 MB)</span></>}
      </div>
      {error && <p style={{color:'var(--error)',fontSize:'0.85rem',marginTop:'0.4rem'}}>❌ {error}</p>}
      {attachments.length > 0 && (
        <div style={{marginTop:'0.75rem',display:'flex',flexDirection:'column',gap:'0.4rem'}}>
          {attachments.map(fn => (
            <div key={fn} style={{display:'flex',alignItems:'center',gap:'0.75rem',
              background:'var(--surface-alt)',border:'1px solid var(--border)',
              borderRadius:'var(--radius-sm)',padding:'0.45rem 0.75rem'}}>
              <span style={{fontSize:'1rem'}}>📄</span>
              <span style={{flex:1,fontSize:'0.875rem',fontWeight:500}}>{fn}</span>
              <button onClick={()=>onDelete(fn)} style={{background:'none',border:'none',
                cursor:'pointer',color:'var(--error)',fontSize:'1rem',padding:'0 4px'}}
                title="Remove attachment">×</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Step 1: Setup ────────────────────────────────────────────────────────────

function SetupStep({ formData, onChange, attachments, onAttachUpload, onAttachDelete, onNext }) {
  const [errors, setErrors] = useState({});
  const validate = () => {
    const e = {};
    if (!formData.mission.trim())        e.mission = 'Required.';
    if (!formData.offer.trim())          e.offer   = 'Required.';
    if (!formData.call_to_action.trim()) e.cta     = 'Required.';
    return e;
  };
  const next = () => {
    const e = validate();
    if (Object.keys(e).length) { setErrors(e); return; }
    setErrors({}); onNext();
  };
  return (
    <div className="step-content">
      <div className="step-header">
        <h2>📋 Campaign Setup</h2>
        <p>Define who you are and what this campaign is about. The AI will use all of this to write unique emails for each lead.</p>
      </div>

      {/* Sender */}
      <div className="field-section">
        <h3>Sender</h3>
        <div className="field-row">
          <div className="field-group"><label>Your Name</label><input className="field-input" type="text" name="sender_name" value={formData.sender_name} onChange={onChange} /></div>
          <div className="field-group"><label>Company</label><input className="field-input" type="text" name="sender_company" value={formData.sender_company} onChange={onChange} /></div>
        </div>
      </div>

      {/* Email Type */}
      <div className="field-section">
        <h3>Email Type</h3>
        <p className="field-hint">Sets the intent and tone of the entire email structure.</p>
        <div className="tone-grid" style={{gridTemplateColumns:'repeat(3,1fr)'}}>
          {EMAIL_TYPES.map(t => (
            <button key={t.value} type="button"
              className={`tone-option ${formData.email_type === t.value ? 'selected' : ''}`}
              onClick={() => onChange({ target: { name: 'email_type', value: t.value } })}>
              <strong>{t.label}</strong><span>{t.desc}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Mission */}
      <div className="field-section">
        <h3>Mission</h3>
        <p className="field-hint">What does your company do and who do you help?</p>
        <textarea className={`field-input field-textarea ${errors.mission ? 'field-error' : ''}`} name="mission" rows={3} value={formData.mission} onChange={onChange} placeholder="we help SaaS companies book more demos with SEO and targeted outreach" />
        {errors.mission && <span className="error-msg">{errors.mission}</span>}
      </div>

      {/* Offer */}
      <div className="field-section">
        <h3>Offer</h3>
        <p className="field-hint">What specific value are you giving this person?</p>
        <textarea className={`field-input field-textarea ${errors.offer ? 'field-error' : ''}`} name="offer" rows={2} value={formData.offer} onChange={onChange} placeholder="a free SEO audit and 3-step lead generation plan" />
        {errors.offer && <span className="error-msg">{errors.offer}</span>}
      </div>

      {/* CTA + Tone */}
      <div className="field-row">
        <div className="field-group" style={{ flex: 2 }}>
          <label>Call to Action</label>
          <p className="field-hint">What do you want them to do?</p>
          <input className={`field-input ${errors.cta ? 'field-error' : ''}`} type="text" name="call_to_action" value={formData.call_to_action} onChange={onChange} />
          {errors.cta && <span className="error-msg">{errors.cta}</span>}
        </div>
        <div className="field-group">
          <label>Tone</label>
          <p className="field-hint">AI writing style.</p>
          <div className="tone-grid">
            {TONES.map(t => (
              <button key={t.value} type="button" className={`tone-option ${formData.tone === t.value ? 'selected' : ''}`} onClick={() => onChange({ target: { name: 'tone', value: t.value } })}>
                <strong>{t.label}</strong><span>{t.desc}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Email Length */}
      <div className="field-section">
        <h3>Email Length</h3>
        <p className="field-hint">Target word count for AI-generated emails.</p>
        <div style={{display:'flex',gap:'0.75rem'}}>
          {EMAIL_LENGTHS.map(l => (
            <button key={l.value} type="button" onClick={() => onChange({ target: { name: 'email_length', value: l.value } })}
              style={{
                flex:1, padding:'0.6rem 0.5rem', borderRadius:'var(--radius-sm)', cursor:'pointer',
                border: formData.email_length === l.value ? '2px solid var(--accent)' : '2px solid var(--border)',
                background: formData.email_length === l.value ? 'var(--accent-light)' : 'var(--surface)',
                color: formData.email_length === l.value ? 'var(--accent-dark)' : 'var(--ink)',
                fontWeight: formData.email_length === l.value ? 700 : 400,
                textAlign:'center',
              }}>
              <div style={{fontWeight:'inherit'}}>{l.label}</div>
              <div style={{fontSize:'0.75rem',color:'var(--muted)',marginTop:'2px'}}>{l.desc}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Signature */}
      <div className="field-section">
        <h3>Signature <span className="optional-tag">Optional</span></h3>
        <textarea className="field-input field-textarea" name="signature" rows={2} value={formData.signature} onChange={onChange} placeholder="WhatsApp: +1 234 567 890&#10;Cal.com/yourname" />
      </div>

      <div className="field-section">
        <h3>Meeting Links <span className="optional-tag">Optional</span></h3>
        <p className="field-hint">If you add these, the automation will include them in generated drafts and interested lead replies.</p>
        <div className="field-row">
          <div className="field-group">
            <label>Google Meet Link</label>
            <input
              className="field-input"
              type="url"
              name="google_meet_link"
              value={formData.google_meet_link}
              onChange={onChange}
              placeholder="https://meet.google.com/abc-defg-hij"
            />
          </div>
          <div className="field-group">
            <label>Google Calendar Link</label>
            <input
              className="field-input"
              type="url"
              name="google_calendar_link"
              value={formData.google_calendar_link}
              onChange={onChange}
              placeholder="https://calendar.google.com/..."
            />
          </div>
        </div>
      </div>

      {/* Attachments */}
      <div className="field-section">
        <h3>Attachments <span className="optional-tag">Optional</span></h3>
        <p className="field-hint">Files attached here will be included in every SMTP-sent email.</p>
        <AttachmentManager attachments={attachments} onUpload={onAttachUpload} onDelete={onAttachDelete} />
      </div>

      <div className="step-actions">
        <button className="btn btn-primary" onClick={next}>Continue to Contacts →</button>
      </div>
    </div>
  );
}

// ─── Step 2: Contacts ─────────────────────────────────────────────────────────

function ContactsStep({ contacts, onGenerate, onGenerateAI, loading, aiLoading, onBack }) {
  const [file, setFile] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef();

  const handleDrop = (e) => {
    e.preventDefault(); setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f?.name.endsWith('.csv')) setFile(f);
  };

  return (
    <div className="step-content">
      <div className="step-header">
        <h2>👥 Upload Your Leads</h2>
        <p>Upload a CSV. Only <code>email</code> is required — more columns = more personalization for the AI.</p>
      </div>
      <div className="csv-format-card">
        <h4>📌 Supported columns</h4>
        <div className="csv-columns">
          {['email ✱','first_name','last_name','company','role','website','notes'].map(c=>(
            <span key={c} className={`csv-col ${c.includes('✱')?'required':''}`}>{c}</span>
          ))}
        </div>
        <a href="/api/sample-csv" className="link-subtle">⬇ Download sample CSV</a>
      </div>
      <div
        className={`drop-zone ${dragOver?'drag-over':''} ${file?'has-file':''}`}
        onDragOver={e=>{e.preventDefault();setDragOver(true);}}
        onDragLeave={()=>setDragOver(false)}
        onDrop={handleDrop}
        onClick={()=>inputRef.current.click()}
      >
        <input ref={inputRef} type="file" accept=".csv" style={{display:'none'}} onChange={e=>setFile(e.target.files[0])} />
        {file ? <><div className="drop-icon">📄</div><strong>{file.name}</strong><span className="drop-sub">Click to change</span></>
               : <><div className="drop-icon">📂</div><strong>Drag & drop CSV</strong><span className="drop-sub">or click to browse</span></>}
      </div>
      {contacts.length > 0 && (
        <div className="contacts-loaded">
          <h4>✅ {contacts.length} contacts loaded</h4>
          <div className="contacts-mini-table">
            <table>
              <thead><tr><th>Email</th><th>Name</th><th>Company</th><th>Role</th></tr></thead>
              <tbody>{contacts.slice(0,5).map((c,i)=>(
                <tr key={i}><td>{c.email}</td><td>{[c.first_name,c.last_name].filter(Boolean).join(' ')||'—'}</td><td>{c.company||'—'}</td><td>{c.role||'—'}</td></tr>
              ))}</tbody>
            </table>
            {contacts.length > 5 && <p className="table-more">…and {contacts.length-5} more</p>}
          </div>
        </div>
      )}

      {/* Generation mode selection */}
      <div className="gen-mode-cards">
        <div className="gen-mode-card gen-mode-ai">
          <div className="gen-mode-icon">🤖</div>
          <div className="gen-mode-body">
            <h4>AI-Generated <span className="badge-new">Recommended</span></h4>
            <p>Ollama writes a unique, deeply personalized email for each contact based on their company, role, and notes. Configure your model in ⚙️ AI Settings (top-right).</p>
          </div>
          <button className="btn btn-primary" onClick={() => onGenerateAI(file)} disabled={aiLoading || loading || (!file && contacts.length === 0)}>
            {aiLoading ? <><span className="spinner" /> Generating with AI…</> : '🤖 Generate with AI'}
          </button>
        </div>
        <div className="gen-mode-card">
          <div className="gen-mode-icon">📝</div>
          <div className="gen-mode-body">
            <h4>Template-Based</h4>
            <p>Fast, instant generation using the mission, offer, and CTA you entered. Works without an AI key.</p>
          </div>
          <button className="btn btn-outline" onClick={() => onGenerate(file)} disabled={loading || aiLoading || (!file && contacts.length === 0)}>
            {loading ? <><span className="spinner" /> Generating…</> : '📝 Generate from Template'}
          </button>
        </div>
      </div>

      <div className="step-actions">
        <button className="btn btn-ghost" onClick={onBack}>← Back</button>
      </div>
    </div>
  );
}

// ─── AI Generation Progress Modal ────────────────────────────────────────────

function AIGenerateProgress({ progress, onClose }) {
  const { items = [], total = 0, done = false, error = null } = progress;
  const completed = items.filter(i => i.status === 'done' || i.status === 'fallback').length;
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
  return (
    <div className="gmail-overlay">
      <div className="gmail-modal">
        <div className="gmail-modal-header">
          <span className="gmail-modal-icon">🤖</span>
          <div>
            <h3>{done ? 'AI Generation Complete' : 'AI Writing Your Emails…'}</h3>
            <p>{done ? `${completed} emails ready` : 'GPT-4o is crafting personalized copy for each lead'}</p>
          </div>
        </div>
        {error && <div className="gmail-error">❌ {error}</div>}
        <div className="gmail-progress-bar-track">
          <div className="gmail-progress-bar-fill" style={{ width: `${pct}%` }} />
        </div>
        <div className="gmail-progress-pct">{pct}% — {completed} of {total}</div>
        <div className="gmail-email-list">
          {items.map((item, i) => (
            <div key={i} className={`gmail-email-item gmail-email-${item.status === 'done' ? 'sent' : item.status === 'fallback' ? 'failed' : 'sending'}`}>
              <span className="gmail-email-icon">{item.status==='done'?'✅':item.status==='fallback'?'⚠️':'⏳'}</span>
              <span className="gmail-email-addr">{item.email}</span>
              {item.subject && <span style={{fontSize:'0.78rem',color:'var(--muted)',marginLeft:'auto'}}>{item.subject?.slice(0,40)}</span>}
            </div>
          ))}
        </div>
        {done && <button className="btn btn-primary" style={{marginTop:20,width:'100%'}} onClick={onClose}>View Drafts →</button>}
      </div>
    </div>
  );
}

// ─── Step 3: Preview ──────────────────────────────────────────────────────────

function PreviewStep({ drafts, onUpdateDraft, onNext, onBack }) {
  const [active, setActive] = useState(0);
  const [isEditing, setIsEditing] = useState(false);
  const [editedSubject, setEditedSubject] = useState('');
  const [editedBody, setEditedBody] = useState('');
  const [saving, setSaving] = useState(false);

  if (!drafts.length) return (
    <div className="step-content">
      <div className="step-header"><h2>✉️ Draft Preview</h2><p>No drafts yet — go back and generate them first.</p></div>
      <div className="step-actions"><button className="btn btn-ghost" onClick={onBack}>← Back</button></div>
    </div>
  );

  const draft = drafts[active];
  const openDraft = (index) => {
    setActive(index);
    setIsEditing(false);
    setEditedSubject('');
    setEditedBody('');
  };

  const handleSave = async () => {
    setSaving(true);
    const success = await onUpdateDraft(draft.email, editedSubject, editedBody);
    if (success) setIsEditing(false);
    setSaving(false);
  };

  return (
    <div className="step-content">
      <div className="step-header">
        <h2>✉️ Preview Drafts</h2>
        <p>Review every personalized email. Click a name on the left to read that message. You can now edit the copy directly!</p>
      </div>
      <div className="preview-layout">
        <div className="draft-sidebar">
          <div className="draft-count">{drafts.length} emails ready</div>
          {drafts.map((d,i)=>(
            <button key={i} type="button" className={`draft-row ${active===i?'active':''}`} onClick={()=>openDraft(i)}>
              <div className="draft-row-email">{d.email}</div>
              <div className="draft-row-subject">{d.subject}</div>
              <span className={`badge badge-${d.status}`}>{d.status}</span>
            </button>
          ))}
        </div>
        <div className="draft-viewer">
          <div className="draft-meta-row">
            <div className="meta-item"><span>To</span><strong>{draft.email}</strong></div>
            <div className="meta-item" style={{flex: 1}}>
              <span>Subject</span>
              {isEditing ? (
                <input
                  className="field-input field-small"
                  style={{width: '100%', fontWeight: 'bold', marginTop: '4px'}}
                  value={editedSubject}
                  onChange={e => setEditedSubject(e.target.value)}
                />
              ) : (
                <strong>{draft.subject}</strong>
              )}
            </div>
            <div className="meta-item"><span>Status</span><span className={`badge badge-${draft.status}`}>{draft.status}</span></div>
          </div>
          
          {isEditing ? (
            <textarea
              className="field-input draft-body-edit"
              style={{width:'100%', minHeight:'300px', marginTop:'1rem', padding:'1rem', fontFamily:'inherit', lineHeight:1.6}}
              value={editedBody}
              onChange={e => setEditedBody(e.target.value)}
            />
          ) : (
            <pre className="draft-body">{draft.body}</pre>
          )}

          <div className="draft-viewer-actions" style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginTop:'1.5rem', borderTop:'1px solid var(--border)', paddingTop:'1.5rem'}}>
            <div style={{display:'flex', gap:'0.75rem'}}>
              {isEditing ? (
                <>
                  <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
                    {saving ? <><span className="spinner"/> Saving…</> : '💾 Save Changes'}
                  </button>
                  <button className="btn btn-ghost" onClick={() => { setIsEditing(false); setEditedSubject(''); setEditedBody(''); }} disabled={saving}>
                    Cancel
                  </button>
                </>
              ) : (
                <button className="btn btn-outline" onClick={() => { setEditedSubject(draft.subject); setEditedBody(draft.body); setIsEditing(true); }}>
                  ✏️ Edit Draft
                </button>
              )}
            </div>
            {!isEditing && (
              <a href={draft.gmail_url} target="_blank" rel="noreferrer" className="btn btn-outline">📨 Open in Gmail</a>
            )}
          </div>
        </div>
      </div>
      <div className="step-actions">
        <button className="btn btn-ghost" onClick={onBack}>← Back</button>
        <button className="btn btn-primary" onClick={onNext} disabled={isEditing}>Continue to Send →</button>
      </div>
    </div>
  );
}

// ─── Gmail Send Progress Modal ────────────────────────────────────────────────

function GmailProgress({ progress, onClose }) {
  const { items=[], total=0, done=false, sent=0, failed=0, error=null } = progress;
  const pct = total > 0 ? Math.round((items.length / total) * 100) : 0;
  return (
    <div className="gmail-overlay">
      <div className="gmail-modal">
        <div className="gmail-modal-header">
          <span className="gmail-modal-icon">📧</span>
          <div>
            <h3>{done ? 'Sending Complete' : 'Sending via Gmail…'}</h3>
            <p>{done ? `${sent} sent · ${failed} failed` : 'Chrome is composing and sending your emails'}</p>
          </div>
        </div>
        {error && <div className="gmail-error">❌ {error}</div>}
        {!error && <>
          <div className="gmail-progress-bar-track"><div className="gmail-progress-bar-fill" style={{width:`${pct}%`}} /></div>
          <div className="gmail-progress-pct">{pct}% — {items.length} of {total}</div>
          <div className="gmail-email-list">
            {items.map((item,i)=>(
              <div key={i} className={`gmail-email-item gmail-email-${item.status}`}>
                <span className="gmail-email-icon">{item.status==='sent'?'✅':item.status==='failed'?'❌':'⏳'}</span>
                <span className="gmail-email-addr">{item.email}</span>
                {item.error && <span className="gmail-email-err">{item.error}</span>}
              </div>
            ))}
          </div>
        </>}
        {(done || error) ? <button className="btn btn-primary" style={{marginTop:20,width:'100%'}} onClick={onClose}>Done</button>
                         : <p className="gmail-notice">⚠️ Do not close Chrome while sending.</p>}
      </div>
    </div>
  );
}

// ─── Step 4: Send ─────────────────────────────────────────────────────────────

function SendStep({ drafts, formData, onChange, onSMTP, loading, onBack, onDraftsUpdate, onOpenSettings }) {
  const sentCount   = drafts.filter(d=>d.status==='sent').length;
  const failedCount = drafts.filter(d=>d.status==='failed').length;
  const [gmailLimit, setGmailLimit] = useState(Math.min(5, drafts.length));
  const [gmailProgress, setGmailProgress] = useState(null);
  const sendAbortRef = useRef(null);

  const handleGmailSend = async () => {
    sendAbortRef.current?.abort();
    const controller = new AbortController();
    sendAbortRef.current = controller;
    setGmailProgress({ items:[], total:gmailLimit, done:false, sent:0, failed:0, error:null });
    try {
      const response = await apiFetch('/api/send-gmail', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ limit: gmailLimit }),
        signal: controller.signal,
      });
      await streamSseResponse(response, (data) => {
        if (data.fatal) {
          setGmailProgress(p => ({ ...p, done: true, error: data.error }));
          return;
        }
        if (data.done) {
          setGmailProgress(p => ({ ...p, done: true, sent: data.sent, failed: data.failed }));
          fetch('/api/state').then(r=>r.json()).then(s=>onDraftsUpdate(s.drafts||[]));
          return;
        }
        if (data.status) {
          setGmailProgress(p => {
            const items = p.items.filter(it => it.index !== data.index || data.status === 'sending');
            if (data.status !== 'sending') items.push(data);
            return { ...p, items, total: data.total };
          });
        }
      });
    } catch (err) {
      if (err.name !== 'AbortError') {
        setGmailProgress(p => p?.done ? p : { ...p, done: true, error: String(err.message || err) });
      }
    } finally {
      if (sendAbortRef.current === controller) {
        sendAbortRef.current = null;
      }
    }
  };

  return (
    <>
      {gmailProgress && <GmailProgress progress={gmailProgress} onClose={()=>setGmailProgress(null)} />}
      <div className="step-content">
        <div className="step-header">
          <h2>🚀 Send & Export</h2>
          <p>Choose how to deliver your emails. The inbox monitor (next tab) will watch for replies and auto-respond 24/7.</p>
        </div>
        {(sentCount > 0 || failedCount > 0) && (
          <div className="send-result">✅ <strong>{sentCount} sent</strong>{failedCount>0&&<>&nbsp;·❌<strong>{failedCount} failed</strong></>}</div>
        )}
        <div className="send-cards">
          <div className="send-card send-card-featured">
            <div className="send-card-badge">Recommended</div>
            <div className="send-card-icon">🤖</div>
            <h3>Gmail Automation</h3>
            <p>Controls Chrome directly to send from your Gmail account.<br/><strong>Close all Chrome windows first.</strong></p>
            <div className="send-card-actions">
              <div className="gmail-limit-row">
                <label htmlFor="gmailLimit">Emails to send</label>
                <input id="gmailLimit" type="number" min={1} max={drafts.length} value={gmailLimit} onChange={e=>setGmailLimit(Math.max(1,Math.min(drafts.length,Number(e.target.value))))} className="field-input field-small" style={{width:80}} />
                <span className="gmail-limit-of">of {drafts.length}</span>
              </div>
              <button className="btn btn-primary" onClick={handleGmailSend} disabled={!drafts.length}>🤖 Send via Gmail</button>
            </div>
          </div>
          <div className="send-card">
            <div className="send-card-icon">📥</div>
            <h3>Export</h3>
            <p>Download your {drafts.length} emails to review or import elsewhere.</p>
            <div className="send-card-actions">
              <a href="/api/download/csv"  className="btn btn-outline">⬇ CSV</a>
              <a href="/api/download/json" className="btn btn-outline">⬇ JSON</a>
            </div>
          </div>
          <div className="send-card">
            <div className="send-card-icon">⚡</div>
            <h3>SMTP Send</h3>
            <p>Send with the SMTP server you configured in Settings, including non-Gmail mailboxes.</p>
            <div className="send-card-actions">
              <div className="field-group" style={{margin:0}}><label>Sender Email</label><input className="field-input" type="email" name="sender_email" value={formData.sender_email} onChange={onChange} placeholder="you@example.com" /></div>
              <button className="btn btn-ghost" onClick={onOpenSettings}>⚙️ SMTP Settings</button>
              <button className="btn btn-outline" onClick={onSMTP} disabled={loading||!formData.sender_email}>
                {loading ? <><span className="spinner"/>Sending…</> : '⚡ Send via SMTP'}
              </button>
            </div>
          </div>
        </div>
        <div className="step-actions">
          <button className="btn btn-ghost" onClick={onBack}>← Back</button>
          <button className="btn btn-primary" style={{background:'linear-gradient(135deg,#059669,#065f46)'}} onClick={() => {}}>
            <span onClick={() => document.querySelector('[data-step="conversations"]')?.click()}>View Conversations →</span>
          </button>
        </div>
      </div>
    </>
  );
}

// ─── Follow-up Settings ──────────────────────────────────────────────────────

function FollowupSettings() {
  const [enabled, setEnabled]     = useState(false);
  const [delay, setDelay]         = useState(24);
  const [maxCount, setMaxCount]   = useState(2);
  const [saving, setSaving]       = useState(false);
  const [savedNote, setSavedNote] = useState('');
  const loaded = useRef(false);

  useEffect(() => {
    fetch('/api/settings/followup').then(r=>r.json()).then(d => {
      setEnabled(!!d.enabled);
      setDelay(d.delay_hours || 24);
      setMaxCount(d.max_count || 2);
      loaded.current = true;
    });
  }, []);

  const save = async (next) => {
    setSaving(true); setSavedNote('');
    const body = {
      enabled:     next.enabled     ?? enabled,
      delay_hours: next.delay_hours ?? delay,
      max_count:   next.max_count   ?? maxCount,
    };
    const res = await apiFetch('/api/settings/followup', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(body),
    }).then(r=>r.json());
    setSaving(false);
    if (res.error) setSavedNote(`❌ ${res.error}`);
    else { setSavedNote('✅ Saved'); setTimeout(()=>setSavedNote(''), 1800); }
  };

  return (
    <div style={{
      background:'var(--surface-alt)', border:'1px solid var(--border)',
      borderRadius:'var(--radius)', padding:'1rem 1.25rem', marginBottom:'1rem',
    }}>
      <div style={{display:'flex', justifyContent:'space-between', alignItems:'flex-start', gap:'1rem'}}>
        <div style={{flex:1}}>
          <strong style={{fontSize:'1rem'}}>⏰ Auto Follow-ups</strong>
          <p style={{margin:'0.25rem 0 0', fontSize:'0.85rem', color:'var(--muted)'}}>
            If a prospect doesn't reply within the delay window, the AI drafts a follow-up
            and queues it for a short review before auto-sending. Incoming reply drafts auto-send after 30 minutes.
          </p>
        </div>
        <label style={{display:'flex', alignItems:'center', gap:'0.5rem', cursor:'pointer', userSelect:'none'}}>
          <input type="checkbox" checked={enabled}
            onChange={e => { setEnabled(e.target.checked); save({enabled: e.target.checked}); }}
            style={{width:18, height:18, cursor:'pointer'}} />
          <span style={{fontSize:'0.875rem', fontWeight:600,
            color: enabled ? 'var(--success)' : 'var(--muted)'}}>
            {enabled ? 'ON' : 'OFF'}
          </span>
        </label>
      </div>

      {enabled && (
        <div style={{display:'flex', gap:'1rem', marginTop:'0.75rem', flexWrap:'wrap'}}>
          <div style={{flex:1, minWidth:140}}>
            <label style={{fontSize:'0.8rem', fontWeight:600, color:'var(--muted)'}}>Delay (hours)</label>
            <input type="number" min={1} max={168} value={delay}
              onChange={e=>setDelay(Math.max(1,Math.min(168,Number(e.target.value)||24)))}
              onBlur={()=>save({delay_hours: delay})}
              className="field-input" style={{marginTop:'0.25rem'}} />
          </div>
          <div style={{flex:1, minWidth:140}}>
            <label style={{fontSize:'0.8rem', fontWeight:600, color:'var(--muted)'}}>Max follow-ups per contact</label>
            <input type="number" min={1} max={5} value={maxCount}
              onChange={e=>setMaxCount(Math.max(1,Math.min(5,Number(e.target.value)||2)))}
              onBlur={()=>save({max_count: maxCount})}
              className="field-input" style={{marginTop:'0.25rem'}} />
          </div>
          <div style={{display:'flex', alignItems:'flex-end', minHeight:64}}>
            {saving && <span className="spinner" />}
            {savedNote && <span style={{fontSize:'0.8rem', color: savedNote.startsWith('✅') ? 'var(--success)' : 'var(--error)'}}>{savedNote}</span>}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Step 5: Conversations ────────────────────────────────────────────────────

function ConversationsStep({ onBack }) {
  const [monitorStatus, setMonitorStatus] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [loadingToggle, setLoadingToggle] = useState(false);
  const pollRef = useRef(null);

  const fetchStatus = useCallback(async () => {
    try {
      const [s, c] = await Promise.all([
        fetch('/api/inbox/status').then(r=>r.json()),
        fetch('/api/conversations').then(r=>r.json()),
      ]);
      setMonitorStatus(s);
      setConversations(c.conversations || []);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    const initialLoad = setTimeout(() => {
      void fetchStatus();
    }, 0);
    // Poll every 30s to refresh conversation state
    pollRef.current = setInterval(fetchStatus, 30000);
    return () => {
      clearTimeout(initialLoad);
      clearInterval(pollRef.current);
    };
  }, [fetchStatus]);

  const toggleMonitor = async () => {
    setLoadingToggle(true);
    const action = monitorStatus?.running ? 'stop' : 'start';
    try {
      await apiFetch(`/api/inbox/${action}`, { method: 'POST' });
      await fetchStatus();
    } catch { /* ignore */ }
    setLoadingToggle(false);
  };

  const handleApprovePending = async (email, body) => {
    try {
      await apiFetch(`/api/conversations/${encodeURIComponent(email)}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ body })
      });
      fetchStatus();
    } catch { /* ignore */ }
  };

  const handleCancelPending = async (email) => {
    try {
      await apiFetch(`/api/conversations/${encodeURIComponent(email)}/cancel`, { method: 'POST' });
      fetchStatus();
    } catch { /* ignore */ }
  };

  const selectedConv = conversations.find(c => c.email === selectedEmail);

  const statusCounts = {
    active:       conversations.filter(c=>c.status==='active').length,
    progressing:  conversations.filter(c=>c.status==='progressing').length,
    closed:       conversations.filter(c=>['not_interested','closed','limit_reached'].includes(c.status)).length,
  };

  return (
    <div className="step-content">
      <div className="step-header">
        <h2>📬 Conversations</h2>
        <p>The inbox monitor watches your Gmail for replies and auto-responds using AI — your 24/7 virtual sales rep.</p>
      </div>

      {/* Monitor control */}
      <div className={`monitor-card ${monitorStatus?.running ? 'monitor-running' : 'monitor-stopped'}`}>
        <div className="monitor-info">
          <div className={`monitor-dot ${monitorStatus?.running ? 'dot-live' : 'dot-off'}`} />
          <div>
            <strong>{monitorStatus?.running ? 'Inbox Monitor Running' : 'Inbox Monitor Stopped'}</strong>
            <p className="monitor-sub">
              {monitorStatus?.running
                ? `Checking every ${monitorStatus.poll_interval_seconds / 60} min · Last checked: ${monitorStatus.last_checked ? new Date(monitorStatus.last_checked).toLocaleTimeString() : 'never'}`
                : 'Start to watch for replies and auto-respond automatically'}
            </p>
          </div>
        </div>
        <button className={`btn ${monitorStatus?.running ? 'btn-danger-outline' : 'btn-primary'}`} onClick={toggleMonitor} disabled={loadingToggle}>
          {loadingToggle ? <span className="spinner" /> : monitorStatus?.running ? '⏹ Stop Monitor' : '▶ Start Monitor'}
        </button>
      </div>

      {/* Auto follow-up settings */}
      <FollowupSettings />

      {/* Stats row */}
      {conversations.length > 0 && (
        <div className="conv-stats">
          <div className="conv-stat"><span>{conversations.length}</span><label>Total Threads</label></div>
          <div className="conv-stat conv-stat-hot"><span>{statusCounts.progressing}</span><label>Progressing 🔥</label></div>
          <div className="conv-stat"><span>{statusCounts.active}</span><label>Active</label></div>
          <div className="conv-stat conv-stat-muted"><span>{statusCounts.closed}</span><label>Closed</label></div>
        </div>
      )}

      {conversations.length === 0 ? (
        <div className="conv-empty">
          <div style={{fontSize:'2.5rem'}}>📭</div>
          <strong>No conversations yet</strong>
          <p>Send your campaign then start the inbox monitor. Replies will appear here and get auto-responded.</p>
        </div>
      ) : (
        <div className="conv-layout">
          {/* Left: thread list */}
          <div className="conv-list">
            {conversations.map(conv => (
              <button key={conv.email} type="button" className={`conv-item ${selectedEmail===conv.email?'active':''}`} onClick={()=>setSelectedEmail(conv.email)}>
                <div className="conv-item-header">
                  <span className="conv-email">{conv.email}</span>
                  <span className={`badge ${STATUS_COLORS[conv.status]||'badge-active'}`}>{STATUS_LABELS[conv.status]||conv.status}</span>
                </div>
                <div className="conv-item-foot">
                  <span>{conv.messages?.length||0} messages</span>
                  {conv.pending_auto_reply
                    ? <span style={{color:'var(--primary)', fontWeight:'bold'}}>
                        ⏳ {conv.pending_auto_reply.classification === 'follow_up' ? 'follow-up pending' : 'pending reply'}
                      </span>
                    : <span>
                        {conv.auto_reply_count || 0} auto-replies
                        {conv.follow_up_count ? ` · ${conv.follow_up_count} follow-up${conv.follow_up_count > 1 ? 's' : ''}` : ''}
                      </span>}
                </div>
              </button>
            ))}
          </div>

          {/* Right: thread view */}
          <div className="conv-thread">
            {selectedConv ? (
              <>
                <div className="conv-thread-header">
                  <strong>{selectedConv.email}</strong>
                  <span className={`badge ${STATUS_COLORS[selectedConv.status]||'badge-active'}`}>{STATUS_LABELS[selectedConv.status]||selectedConv.status}</span>
                </div>
                <div className="conv-messages">
                  {selectedConv.pending_auto_reply && (
                    <PendingReplyCard
                      key={`${selectedConv.email}-${selectedConv.pending_auto_reply.generated_at}`}
                      email={selectedConv.email}
                      pending={selectedConv.pending_auto_reply}
                      onApprove={handleApprovePending}
                      onCancel={handleCancelPending}
                    />
                  )}
                  {selectedConv.messages?.map((msg, i) => (
                    <div key={i} className={`conv-msg conv-msg-${msg.direction}`}>
                      <div className="conv-msg-meta">
                        <span>{msg.direction === 'sent' ? '📤 You' : '📥 Them'}</span>
                        <span className="conv-msg-class">{msg.classification||''}</span>
                        <span>{msg.timestamp ? new Date(msg.timestamp).toLocaleString() : ''}</span>
                      </div>
                      <pre className="conv-msg-body">{msg.body}</pre>
                      {msg.error && <div className="conv-msg-error">⚠️ {msg.error}</div>}
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="conv-thread-empty">← Select a contact to view the full conversation thread</div>
            )}
          </div>
        </div>
      )}

      <div className="step-actions">
        <button className="btn btn-ghost" onClick={onBack}>← Back to Send</button>
        <button className="btn btn-ghost" onClick={fetchStatus}>🔄 Refresh</button>
      </div>
    </div>
  );
}

// ─── App Root ─────────────────────────────────────────────────────────────────

export default function App() {
  const [step, setStep]               = useState('setup');
  const [completed, setCompleted]     = useState([]);
  const [formData, setFormData]       = useState(DEFAULT_FORM);
  const [contacts, setContacts]       = useState([]);
  const [drafts, setDrafts]           = useState([]);
  const [loading, setLoading]             = useState(false);
  const [aiLoading, setAiLoading]         = useState(false);
  const [aiProgress, setAiProgress]       = useState(null);
  const [toast, setToast]                 = useState(null);
  const [showSettings, setShowSettings]   = useState(false);
  const [attachments, setAttachments]     = useState([]);
  const [authState, setAuthState]         = useState(null);
  const aiAbortRef = useRef(null);

  const refreshAuthStatus = useCallback(async () => {
    const status = await fetch('/api/auth/status').then(r => r.json());
    setAuthState(status);
    return status;
  }, []);

  const loadAppState = useCallback(() => {
    fetch('/api/state').then(r=>r.json()).then(data => {
      if (data.form_data && Object.keys(data.form_data).length) setFormData(p=>({...p,...data.form_data}));
      if (data.contacts?.length) setContacts(data.contacts);
      if (data.drafts?.length)   { setDrafts(data.drafts); setCompleted(['setup','contacts','preview']); }
      if (data.attachments)      setAttachments(data.attachments);
    }).catch(()=>{});
  }, []);

  useEffect(() => {
    void refreshAuthStatus();
  }, [refreshAuthStatus]);

  useEffect(() => {
    if (authState?.authenticated && authState?.license?.active) {
      loadAppState();
    }
  }, [authState, loadAppState]);

  const showToast = (msg, type='success') => setToast({ message:msg, type });
  const handleChange = e => setFormData(p=>({...p,[e.target.name]:e.target.value}));
  const markDone = id => setCompleted(p=>p.includes(id)?p:[...p,id]);
  const goTo = id => { setStep(id); window.scrollTo({top:0,behavior:'smooth'}); };
  const handleLogout = async () => {
    await apiFetch('/api/auth/logout', { method: 'POST' });
    setShowSettings(false);
    setContacts([]);
    setDrafts([]);
    setCompleted([]);
    setAttachments([]);
    setFormData(DEFAULT_FORM);
    await refreshAuthStatus();
  };

  // Template generate
  const handleGenerate = async (file) => {
    setLoading(true);
    const data = new FormData();
    Object.keys(formData).forEach(k=>data.append(k,formData[k]));
    if (file) data.append('contacts_file',file);
    try {
      const res = await apiFetch('/api/generate',{method:'POST',body:data});
      const result = await res.json();
      if (!res.ok) showToast(result.error,'error');
      else { setContacts(result.contacts); setDrafts(result.drafts); showToast(result.message,'success'); markDone('setup'); markDone('contacts'); goTo('preview'); }
    } catch(err) { showToast(String(err),'error'); }
    setLoading(false);
  };

  // AI generate via SSE
  const handleGenerateAI = (file) => {
    if (!file && contacts.length === 0) return;
    aiAbortRef.current?.abort();
    const controller = new AbortController();
    aiAbortRef.current = controller;

    const formPayload = new FormData();
    Object.keys(formData).forEach(k => formPayload.append(k, formData[k]));
    if (file) formPayload.append('contacts_file', file);

    setAiLoading(true);
    setAiProgress({ items:[], total:0, done:false, error:null });

    // POST to generate-ai then read SSE
    apiFetch('/api/generate-ai', { method:'POST', body:formPayload, signal: controller.signal })
      .then(res => streamSseResponse(res, (data) => {
        if (data.done) {
          setContacts(data.contacts);
          setDrafts(data.drafts);
          setAiProgress(p=>({...p, done:true, total:data.drafts?.length||0}));
          markDone('setup'); markDone('contacts');
          setAiLoading(false);
        } else if (data.index !== undefined) {
          setAiProgress(p => ({
            ...p,
            total: data.total,
            items: [...p.items.filter(i=>i.index!==data.index), data],
          }));
        }
      }))
      .catch(err => {
        if (err.name !== 'AbortError') {
          showToast(String(err.message || err),'error');
        }
        setAiLoading(false);
      })
      .finally(() => {
        if (aiAbortRef.current === controller) {
          aiAbortRef.current = null;
        }
      });
  };

  const handleSMTP = async () => {
    setLoading(true);
    try {
      const res = await apiFetch('/api/send-smtp',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sender_email:formData.sender_email})});
      const result = await res.json();
      if (!res.ok) showToast(result.error,'error');
      else { setDrafts(result.drafts); showToast(result.message,'success'); markDone('send'); }
    } catch(err) { showToast(String(err),'error'); }
    setLoading(false);
  };

  const handleUpdateDraft = async (email, subject, body) => {
    try {
      const res = await apiFetch('/api/drafts/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, subject, body })
      });
      const result = await res.json();
      if (!res.ok) {
        showToast(result.error, 'error');
        return false;
      }
      setDrafts(result.drafts);
      showToast('Draft saved successfully.', 'success');
      return true;
    } catch (err) {
      showToast(String(err), 'error');
      return false;
    }
  };

  const handleAttachDelete = async (filename) => {
    const res = await apiFetch(`/api/attachments/${encodeURIComponent(filename)}`, { method:'DELETE' }).then(r=>r.json());
    setAttachments(res.attachments || []);
  };

  const handleReset = async () => {
    await apiFetch('/api/reset',{method:'POST'});
    setContacts([]); setDrafts([]); setCompleted([]); setAttachments([]);
    showToast('Session reset.','success'); goTo('setup');
  };

  if (authState === null) {
    return <LoadingScreen message="Checking account and license status…" />;
  }

  if (authState.setup_required || !authState.authenticated || !authState.license?.active) {
    return <AuthShell authState={authState} setAuthState={setAuthState} refreshAuthStatus={refreshAuthStatus} />;
  }

  return (
    <div className="app-shell">
      {toast && <Toast message={toast.message} type={toast.type} onClose={()=>setToast(null)} />}
      {aiProgress && <AIGenerateProgress progress={aiProgress} onClose={()=>{ setAiProgress(null); if (drafts.length) goTo('preview'); }} />}
      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} authState={authState} refreshAuthStatus={refreshAuthStatus} onLogout={handleLogout} />}

      <nav className="top-nav">
        <div className="nav-brand">
          <span className="nav-logo">A1</span>
          <div><div className="nav-title">A1 Mail Dynamics</div><div className="nav-sub">AI Marketing Agent</div></div>
        </div>
        <div className="nav-right">
          <div className="nav-user">
            <strong>{authState?.user?.name || authState?.user?.display_name || authState?.user?.username}</strong>
            <span>{authState?.user?.role}</span>
          </div>
          {drafts.length > 0 && <div className="nav-stats"><span>👥 {contacts.length}</span><span>✉️ {drafts.length}</span></div>}
          {drafts.length > 0 && <button className="btn btn-ghost btn-sm" onClick={handleReset}>Reset</button>}
          <button className="btn btn-ghost btn-sm" onClick={() => setShowSettings(true)} title="Settings">⚙️ Settings</button>
          <button className="btn btn-ghost btn-sm" onClick={handleLogout}>Sign Out</button>
        </div>
      </nav>

      <div className="page-body">
        <StepIndicator steps={STEPS} current={step} completed={completed} onNavigate={goTo} />
        <div className="card">
          {step==='setup'         && <SetupStep         formData={formData} onChange={handleChange} attachments={attachments} onAttachUpload={setAttachments} onAttachDelete={handleAttachDelete} onNext={()=>{markDone('setup');goTo('contacts');}} />}
          {step==='contacts'      && <ContactsStep      contacts={contacts} loading={loading} aiLoading={aiLoading} onGenerate={handleGenerate} onGenerateAI={handleGenerateAI} onBack={()=>goTo('setup')} />}
          {step==='preview'       && <PreviewStep       drafts={drafts} onUpdateDraft={handleUpdateDraft} onNext={()=>{markDone('preview');goTo('send');}} onBack={()=>goTo('contacts')} />}
          {step==='send'          && <SendStep          drafts={drafts} formData={formData} onChange={handleChange} onSMTP={handleSMTP} loading={loading} onBack={()=>goTo('preview')} onDraftsUpdate={setDrafts} onOpenSettings={() => setShowSettings(true)} />}
          {step==='conversations' && <ConversationsStep onBack={()=>goTo('send')} />}
        </div>
      </div>
    </div>
  );
}
