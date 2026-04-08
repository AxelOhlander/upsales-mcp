// ─── DOM elements ───
const loginScreen = document.getElementById('login-screen');
const appEl = document.getElementById('app');
const loginForm = document.getElementById('login-form');
const loginError = document.getElementById('login-error');
const loginBtn = document.getElementById('login-btn');
const messagesEl = document.getElementById('messages');
const welcomeEl = document.getElementById('welcome');
const textarea = document.getElementById('input');
const sendBtn = document.getElementById('send-btn');
const resetBtn = document.getElementById('reset-btn');
const logoutBtn = document.getElementById('logout-btn');
const userNameEl = document.getElementById('user-name');

let isStreaming = false;

// ─── Login ───

loginForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const email = document.getElementById('email').value.trim();
  const password = document.getElementById('password').value;
  if (!email || !password) return;

  loginError.textContent = '';
  loginBtn.disabled = true;
  loginBtn.querySelector('.login-btn-text').style.display = 'none';
  loginBtn.querySelector('.login-btn-loading').style.display = 'inline';

  try {
    const resp = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const data = await resp.json();

    if (!resp.ok) {
      loginError.textContent = data.error || 'Login failed';
      return;
    }

    showApp(data.user);
  } catch (err) {
    loginError.textContent = 'Connection error — is the server running?';
  } finally {
    loginBtn.disabled = false;
    loginBtn.querySelector('.login-btn-text').style.display = 'inline';
    loginBtn.querySelector('.login-btn-loading').style.display = 'none';
  }
});

logoutBtn.addEventListener('click', async () => {
  await fetch('/api/logout', { method: 'POST' });
  appEl.style.display = 'none';
  loginScreen.style.display = 'flex';
  loginScreen.style.opacity = '1';
  document.getElementById('password').value = '';
  loginError.textContent = '';
  messagesEl.innerHTML = '';
  welcomeEl.style.display = 'flex';
  welcomeEl.style.opacity = '1';
  welcomeEl.style.transform = 'translateY(0)';
  accumulatedText = '';
  renderTarget = null;
});

function showApp(user) {
  loginScreen.style.display = 'none';
  appEl.style.display = 'flex';
  appEl.style.animation = 'welcomeFade 300ms cubic-bezier(0.16, 1, 0.3, 1) both';
  if (user && user.name) {
    userNameEl.textContent = user.name;
  }
  textarea.focus();
}

// Check if already logged in on page load
(async () => {
  try {
    const resp = await fetch('/api/status');
    const data = await resp.json();
    if (data.loggedIn) {
      showApp(data.user);
    }
  } catch {
    // Not logged in, show login screen
  }
})();

// ─── Chat ───

textarea.addEventListener('input', () => {
  textarea.style.height = 'auto';
  textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
});

textarea.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

sendBtn.addEventListener('click', sendMessage);
resetBtn.addEventListener('click', resetChat);

document.querySelectorAll('.suggestion').forEach(btn => {
  btn.addEventListener('click', () => {
    textarea.value = btn.textContent.trim();
    sendMessage();
  });
});

async function sendMessage() {
  const text = textarea.value.trim();
  if (!text || isStreaming) return;

  if (welcomeEl) {
    welcomeEl.style.opacity = '0';
    welcomeEl.style.transform = 'translateY(-8px)';
    welcomeEl.style.transition = 'all 200ms cubic-bezier(0.16, 1, 0.3, 1)';
    setTimeout(() => { welcomeEl.style.display = 'none'; }, 200);
  }

  addMessage('user', text);
  textarea.value = '';
  textarea.style.height = 'auto';

  isStreaming = true;
  sendBtn.disabled = true;

  const msgEl = addMessage('assistant', '');
  const bodyEl = msgEl.querySelector('.message-body');

  const typingEl = document.createElement('div');
  typingEl.className = 'typing';
  typingEl.innerHTML = '<span></span><span></span><span></span>';
  bodyEl.appendChild(typingEl);

  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });

    if (response.status === 401) {
      if (typingEl.parentNode) typingEl.remove();
      bodyEl.innerHTML = '<span style="color: var(--danger)">Session expired. Please sign out and log in again.</span>';
      isStreaming = false;
      sendBtn.disabled = false;
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      let eventType = '';
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7);
        } else if (line.startsWith('data: ')) {
          const data = JSON.parse(line.slice(6));
          handleEvent(eventType, data, bodyEl, typingEl);
        }
      }
    }
  } catch (err) {
    if (typingEl.parentNode) typingEl.remove();
    bodyEl.innerHTML = `<span style="color: var(--danger)">Connection error: ${err.message}</span>`;
  }

  isStreaming = false;
  sendBtn.disabled = false;
  textarea.focus();
  scrollToBottom();
}

function handleEvent(type, data, bodyEl, typingEl) {
  switch (type) {
    case 'text':
      if (typingEl.parentNode) typingEl.remove();
      renderMarkdown(bodyEl, data.text);
      break;

    case 'tool_start': {
      if (typingEl.parentNode) typingEl.remove();
      const indicator = document.createElement('div');
      indicator.className = 'tool-indicator';
      indicator.dataset.tool = data.name;
      indicator.innerHTML = `<span class="spinner"></span> Searching ${formatToolName(data.name)}`;
      bodyEl.appendChild(indicator);
      break;
    }

    case 'tool_result': {
      const el = bodyEl.querySelector(`.tool-indicator[data-tool="${data.name}"]`);
      if (el) {
        el.classList.add('done');
        el.innerHTML = `<span class="spinner done"></span> Found ${formatToolName(data.name)}`;
      }
      if (!bodyEl.querySelector('.typing')) {
        const newTyping = document.createElement('div');
        newTyping.className = 'typing';
        newTyping.innerHTML = '<span></span><span></span><span></span>';
        bodyEl.appendChild(newTyping);
      }
      break;
    }

    case 'done': {
      const typing = bodyEl.querySelector('.typing');
      if (typing) typing.remove();
      break;
    }
  }
  scrollToBottom();
}

// ─── Markdown ───

let accumulatedText = '';
let renderTarget = null;

function renderMarkdown(bodyEl, newText) {
  if (renderTarget !== bodyEl) {
    accumulatedText = '';
    renderTarget = bodyEl;
  }
  accumulatedText += newText;

  bodyEl.querySelectorAll('.tool-indicator').forEach(el => el.remove());
  bodyEl.querySelectorAll('.typing').forEach(el => el.remove());

  bodyEl.innerHTML = markdownToHtml(accumulatedText);
}

function markdownToHtml(md) {
  let html = md
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/^\|(.+)\|$/gm, (match) => {
      const cells = match.split('|').filter(c => c.trim());
      if (cells.every(c => /^[\s-:]+$/.test(c))) return '<!--sep-->';
      return cells.map(c => `<td>${c.trim()}</td>`).join('');
    })
    .replace(/^---$/gm, '<hr>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>');

  html = html.replace(/((?:<td>.*?<\/td>)+)/g, '<tr>$1</tr>');
  html = html.replace(/((?:<tr>.*?<\/tr>(?:<br>)?<!--sep-->(?:<br>)?)+(?:<tr>.*?<\/tr>(?:<br>)?)*)/g,
    (match) => {
      const rows = match.replace(/<!--sep-->(<br>)?/g, '').replace(/<br>/g, '');
      const firstRow = rows.match(/<tr>(.*?)<\/tr>/);
      if (firstRow) {
        const headerRow = firstRow[1].replace(/<td>/g, '<th>').replace(/<\/td>/g, '</th>');
        const bodyRows = rows.replace(firstRow[0], '');
        return `<table><thead><tr>${headerRow}</tr></thead><tbody>${bodyRows}</tbody></table>`;
      }
      return `<table>${rows}</table>`;
    }
  );

  html = html.replace(/((?:<li>.*?<\/li>(?:<br>)?)+)/g, '<ul>$1</ul>');
  html = html.replace(/<ul>(.*?)<\/ul>/g, (m, inner) => `<ul>${inner.replace(/<br>/g, '')}</ul>`);

  html = html.replace(/<br><(h[1-3]|hr|table|ul|pre)/g, '<$1');
  html = html.replace(/<\/(h[1-3]|hr|table|ul|pre)><br>/g, '</$1>');

  return `<p>${html}</p>`.replace(/<p><\/p>/g, '');
}

function formatToolName(name) {
  return name.replace(/^(get|find)_/, '').replace(/_/g, ' ');
}

function addMessage(role, text) {
  const el = document.createElement('div');
  el.className = `message ${role}`;

  const avatarContent = role === 'user'
    ? 'Y'
    : '<svg width="16" height="16" viewBox="0 0 200 200" fill="none"><rect width="200" height="200" rx="40" fill="#1D3D48"/><path d="M57.5 124.5C54.1 123.2 51.2 121.4 48.8 118.9C46.2 116.6 44.4 113.7 43 110.2C41.7 106.7 41 102.8 41 98.5V71.7H51.9V99C51.9 101.5 52.3 103.7 53.1 105.8C54 108 55.1 109.8 56.6 111.4C58 113 59.9 114.2 61.9 115.1C63.9 116 66.3 116.5 68.7 116.5C71.2 116.5 73.4 116 75.6 115.1C77.6 114.3 79.3 113 80.9 111.4C82.3 109.8 83.5 108 84.3 105.8C85.2 103.7 85.6 101.4 85.6 99V71.7H96.4V98.4C96.4 102.7 95.8 106.6 94.4 110.1C93.1 113.6 91.1 116.5 88.7 118.9C86.3 121.3 83.3 123.2 79.9 124.5C76.6 125.9 72.8 126.5 68.7 126.5C64.6 126.5 60.9 125.9 57.5 124.5Z" fill="#C3E8E8"/><path d="M124.6 124.5C121.4 123.2 118.8 121.1 116.8 118.4V144H106.6V72.1H116.8V80C118.9 77.2 121.5 75.1 124.8 73.5C128 71.8 131.4 71 135.1 71C138.7 71 142 71.7 145.2 73C148.4 74.3 151.1 76.2 153.6 78.6C156 81 158 83.9 159.4 87.3C160.8 90.7 161.6 94.5 161.6 98.7C161.6 102.9 160.8 106.7 159.4 110.1C158 113.5 155.9 116.5 153.5 118.9C151.1 121.4 148.2 123.3 145 124.5C141.8 125.9 138.5 126.5 135 126.5C131.3 126.7 127.9 125.9 124.6 124.5Z" fill="#C3E8E8"/></svg>';

  const label = role === 'user' ? 'You' : 'Assistant';

  el.innerHTML = `
    <div class="message-header">
      <div class="message-avatar">${avatarContent}</div>
      <div class="message-label">${label}</div>
    </div>
    <div class="message-body">${role === 'user' ? escapeHtml(text) : text}</div>
  `;
  messagesEl.appendChild(el);
  scrollToBottom();
  return el;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML.replace(/\n/g, '<br>');
}

function scrollToBottom() {
  requestAnimationFrame(() => {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  });
}

async function resetChat() {
  await fetch('/api/reset', { method: 'POST' });
  messagesEl.innerHTML = '';
  messagesEl.appendChild(welcomeEl);
  welcomeEl.style.display = 'flex';
  welcomeEl.style.opacity = '1';
  welcomeEl.style.transform = 'translateY(0)';
  welcomeEl.style.transition = '';
  accumulatedText = '';
  renderTarget = null;
  textarea.focus();
}
