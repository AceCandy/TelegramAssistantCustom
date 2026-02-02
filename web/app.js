/**
 * TelegramAssistant Config Manager - Frontend Logic
 */

let currentConfig = {};

// Toast notification
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type} show`;
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

// Toggle collapsible sections
function toggleCollapse(element) {
    const card = element.closest('.collapsible');
    card.classList.toggle('collapsed');
}

// Load config from API
async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        const data = await response.json();

        if (data.success) {
            currentConfig = data.config;
            renderConfig(currentConfig);
            showToast('配置加载成功');
        } else {
            showToast(data.message || '加载失败', 'error');
        }
    } catch (error) {
        showToast('无法连接到服务器', 'error');
        console.error('Load config error:', error);
    }
}

// Render config to form
function renderConfig(config) {
    // API Credentials
    document.getElementById('api_id').value = config.api_id || '';
    document.getElementById('api_hash').value = config.api_hash || '';

    // Bot Account
    const bot = config.bot_account || {};
    document.getElementById('bot_token').value = bot.token || '';
    document.getElementById('bot_session_name').value = bot.session_name || 'bot_session';

    // User Account
    const user = config.user_account || {};
    document.getElementById('user_enabled').checked = user.enabled || false;
    document.getElementById('user_phone').value = user.phone || '';
    document.getElementById('user_session_name').value = user.session_name || 'user_session';

    // YouTube
    const youtube = config.youtube_download || {};
    document.getElementById('youtube_format').value = youtube.format || 'bv*+ba/best';
    document.getElementById('youtube_cookies').value = youtube.cookies || '';
    document.getElementById('youtube_download_list').checked = youtube.download_list || false;

    // Bilibili & Douyin
    document.getElementById('bilibili_cookie').value = (config.bilibili || {}).cookie || '';
    document.getElementById('douyin_cookie').value = (config.douyin || {}).cookie || '';

    // Permission Control
    const chatIds = config.allowed_chat_ids || [];
    document.getElementById('allowed_chat_ids').value = chatIds.join('\n');

    // Proxy
    const proxy = config.proxy || {};
    document.getElementById('proxy_enabled').checked = proxy.enabled || false;
    document.getElementById('proxy_host').value = proxy.host || '127.0.0.1';
    document.getElementById('proxy_port').value = proxy.port || 7890;

    // Log Level
    document.getElementById('log_level').value = config.log_level || 'INFO';

    // HDHive
    const hdhive = config.hdhive || {};
    document.getElementById('hdhive_username').value = hdhive.username || '';
    document.getElementById('hdhive_password').value = hdhive.password || '';
    document.getElementById('hdhive_unlock_threshold').value = hdhive.unlock_threshold || 20;

    // Scheduled Messages
    renderScheduledMessages(config.scheduled_messages || []);

    // Transfer Messages
    renderTransferMessages(config.transfer_message || []);
}

// Collect form data to config object
function collectConfig() {
    const config = { ...currentConfig };

    // API Credentials
    config.api_id = document.getElementById('api_id').value;
    config.api_hash = document.getElementById('api_hash').value;

    // Bot Account
    config.bot_account = {
        token: document.getElementById('bot_token').value,
        session_name: document.getElementById('bot_session_name').value,
    };

    // User Account
    config.user_account = {
        enabled: document.getElementById('user_enabled').checked,
        phone: document.getElementById('user_phone').value,
        session_name: document.getElementById('user_session_name').value,
    };

    // YouTube
    config.youtube_download = {
        format: document.getElementById('youtube_format').value,
        cookies: document.getElementById('youtube_cookies').value,
        download_list: document.getElementById('youtube_download_list').checked,
    };

    // Bilibili & Douyin
    config.bilibili = { cookie: document.getElementById('bilibili_cookie').value };
    config.douyin = { cookie: document.getElementById('douyin_cookie').value };

    // Permission Control
    const chatIdsText = document.getElementById('allowed_chat_ids').value.trim();
    config.allowed_chat_ids = chatIdsText ? chatIdsText.split('\n').map(id => id.trim()).filter(id => id) : [];

    // Proxy
    config.proxy = {
        enabled: document.getElementById('proxy_enabled').checked,
        host: document.getElementById('proxy_host').value,
        port: parseInt(document.getElementById('proxy_port').value) || 7890,
    };

    // Log Level
    config.log_level = document.getElementById('log_level').value;

    // HDHive
    config.hdhive = {
        ...config.hdhive,
        username: document.getElementById('hdhive_username').value,
        password: document.getElementById('hdhive_password').value,
        unlock_threshold: parseInt(document.getElementById('hdhive_unlock_threshold').value) || 20,
    };

    // Scheduled Messages
    config.scheduled_messages = collectScheduledMessages();

    // Transfer Messages
    config.transfer_message = collectTransferMessages();

    return config;
}

// Save config to API
async function saveConfig() {
    try {
        const config = collectConfig();

        const response = await fetch('/api/config', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ config }),
        });

        const data = await response.json();

        if (data.success) {
            currentConfig = data.config;
            showToast('配置保存成功！重启 Bot 后生效');
        } else {
            showToast(data.message || '保存失败', 'error');
        }
    } catch (error) {
        showToast('保存失败: ' + error.message, 'error');
        console.error('Save config error:', error);
    }
}

// Scheduled Messages
function renderScheduledMessages(messages) {
    const container = document.getElementById('scheduledMessages');
    container.innerHTML = messages.map((msg, idx) => `
        <div class="list-item" data-index="${idx}">
            <div class="list-item-header">
                <span class="list-item-title">定时消息 #${idx + 1}</span>
                <button class="btn btn-remove" onclick="removeScheduledMessage(${idx})">删除</button>
            </div>
            <div class="form-grid">
                <div class="form-group">
                    <label>Chat ID</label>
                    <input type="text" class="sm-chat-id" value="${msg.chat_id || ''}" placeholder="目标 Chat ID">
                </div>
                <div class="form-group">
                    <label>时间</label>
                    <input type="text" class="sm-time" value="${msg.time || ''}" placeholder="08:00">
                </div>
            </div>
            <div class="form-group">
                <label>消息内容</label>
                <textarea class="sm-message" rows="2" placeholder="要发送的消息">${msg.message || ''}</textarea>
            </div>
        </div>
    `).join('');
}

function collectScheduledMessages() {
    const items = document.querySelectorAll('#scheduledMessages .list-item');
    return Array.from(items).map(item => ({
        chat_id: item.querySelector('.sm-chat-id').value,
        time: item.querySelector('.sm-time').value,
        message: item.querySelector('.sm-message').value,
    }));
}

function addScheduledMessage() {
    const messages = collectScheduledMessages();
    messages.push({ chat_id: '', time: '08:00', message: '' });
    renderScheduledMessages(messages);
}

function removeScheduledMessage(index) {
    const messages = collectScheduledMessages();
    messages.splice(index, 1);
    renderScheduledMessages(messages);
}

// Transfer Messages
function renderTransferMessages(transfers) {
    const container = document.getElementById('transferMessages');
    container.innerHTML = transfers.map((t, idx) => `
        <div class="list-item" data-index="${idx}">
            <div class="list-item-header">
                <span class="list-item-title">转发规则 #${idx + 1}</span>
                <button class="btn btn-remove" onclick="removeTransferMessage(${idx})">删除</button>
            </div>
            <div class="form-grid">
                <div class="form-group">
                    <label>源频道/群组</label>
                    <input type="text" class="tm-source" value="${t.source_chat || ''}" placeholder="ID 或用户名">
                </div>
                <div class="form-group">
                    <label>目标接收者</label>
                    <input type="text" class="tm-target" value="${t.target_chat || ''}" placeholder="ID 或用户名">
                </div>
            </div>
            <div class="form-grid">
                <div class="form-group">
                    <label>包含关键词（每行一个）</label>
                    <textarea class="tm-include" rows="2" placeholder="关键词1&#10;关键词2">${(t.include_keywords || []).join('\n')}</textarea>
                </div>
                <div class="form-group">
                    <label>排除关键词（每行一个）</label>
                    <textarea class="tm-exclude" rows="2" placeholder="广告&#10;推广">${(t.exclude_words || []).join('\n')}</textarea>
                </div>
            </div>
            <div class="form-group">
                <label>忽略链接域名（每行一个）</label>
                <textarea class="tm-ignore-link" rows="2" placeholder="t.me">${(t.forwardIgnoreLink || []).join('\n')}</textarea>
            </div>
        </div>
    `).join('');
}

function collectTransferMessages() {
    const items = document.querySelectorAll('#transferMessages .list-item');
    return Array.from(items).map(item => ({
        source_chat: item.querySelector('.tm-source').value,
        target_chat: item.querySelector('.tm-target').value,
        include_keywords: textareaToArray(item.querySelector('.tm-include').value),
        exclude_words: textareaToArray(item.querySelector('.tm-exclude').value),
        forwardIgnoreLink: textareaToArray(item.querySelector('.tm-ignore-link').value),
    }));
}

function addTransferMessage() {
    const transfers = collectTransferMessages();
    transfers.push({ source_chat: '', target_chat: '', include_keywords: [], exclude_words: [], forwardIgnoreLink: [] });
    renderTransferMessages(transfers);
}

function removeTransferMessage(index) {
    const transfers = collectTransferMessages();
    transfers.splice(index, 1);
    renderTransferMessages(transfers);
}

// Utility
function textareaToArray(text) {
    return text.trim() ? text.split('\n').map(s => s.trim()).filter(s => s) : [];
}

// Initialize on load
document.addEventListener('DOMContentLoaded', loadConfig);
