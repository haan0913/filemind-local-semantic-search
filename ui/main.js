const API_BASE = "http://127.0.0.1:8000/api";

// Initialize Marked.js
marked.setOptions({
    breaks: true,
    gfm: true
});

// View Routing
document.querySelectorAll('.nav-links li').forEach(item => {
    item.addEventListener('click', (e) => {
        document.querySelectorAll('.nav-links li').forEach(i => i.classList.remove('active'));
        document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
        
        const targetId = e.currentTarget.getAttribute('data-target');
        e.currentTarget.classList.add('active');
        
        // Small delay to ensure CSS transition fires cleanly
        setTimeout(() => {
            document.getElementById(targetId).classList.add('active');
        }, 50);
        
        if (targetId === 'explorer') {
            loadExplorer();
        }
    });
});

// Chat Engine
const chatInput = document.getElementById('chat-input');
const chatMessages = document.getElementById('chat-messages');
const chatSend = document.getElementById('chat-send');

const renderMarkdown = (text) => {
    const rawMarkup = marked.parse(text);
    return DOMPurify.sanitize(rawMarkup);
};

const addMessage = (text, type) => {
    const msg = document.createElement('div');
    msg.className = `message ${type}`;
    
    let content = text;
    if (type === 'system') {
        content = renderMarkdown(text);
    }

    msg.innerHTML = `
        <div class="avatar ${type === 'system' ? 'system-avatar glow-pulse' : ''}"></div>
        <div class="bubble ${type === 'system' ? 'markdown-body' : ''}">${content}</div>
    `;
    
    chatMessages.appendChild(msg);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

const handleChat = async () => {
    const text = chatInput.value.trim();
    if (!text) return;
    
    addMessage(text, 'user');
    chatInput.value = '';
    
    const loadingId = 'loading-' + Date.now();
    const loadingMsg = document.createElement('div');
    loadingMsg.className = 'message system';
    loadingMsg.id = loadingId;
    loadingMsg.innerHTML = `<div class="avatar system-avatar glow-pulse"></div><div class="bubble outline"><div class="loading-spinner" style="width:20px;height:20px;border-width:2px;margin:0;"></div></div>`;
    chatMessages.appendChild(loadingMsg);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    try {
        const res = await fetch(`${API_BASE}/chat?prompt=${encodeURIComponent(text)}`, {
            method: 'POST'
        });
        const data = await res.json();
        document.getElementById(loadingId).remove();
        addMessage(data.response, 'system');
    } catch (err) {
        document.getElementById(loadingId).remove();
        addMessage(`Connection error: ${err.message}`, 'system');
    }
}

chatSend.addEventListener('click', handleChat);
chatInput.addEventListener('keypress', (e) => e.key === 'Enter' && handleChat());

// Search Engine
const searchInput = document.getElementById('search-input');
const searchBtn = document.getElementById('search-btn');
const resultsGrid = document.getElementById('search-results');

const highlightKeywords = (snippet, query) => {
    if (!query) return snippet;
    const words = query.split(' ').map(w => w.replace(/[^a-zA-Z0-9]/g, '')).filter(w => w.length > 2);
    if (!words.length) return snippet;
    
    const safeSnippet = snippet.replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const regex = new RegExp(`(${words.join('|')})`, 'gi');
    return safeSnippet.replace(regex, '<span style="color:var(--accent-main);font-weight:600;text-shadow:0 0 10px rgba(139,92,246,0.4)">$1</span>');
};

const handleSearch = async () => {
    const q = searchInput.value.trim();
    if (!q) return;

    resultsGrid.innerHTML = `<div class="loading-spinner" style="margin-top: 100px;"></div>`;
    
    let url = `${API_BASE}/search?q=${encodeURIComponent(q)}&k=15`;
    if (document.getElementById('use-hyde').checked) {
        url += '&hyde=true';
    }
    
    const exts = Array.from(document.querySelectorAll('.filters input[type="checkbox"]:checked'))
                 .map(box => box.value).join(',');
    if (exts) {
        url += `&ext=${encodeURIComponent(exts)}`;
    }

    try {
        const res = await fetch(url);
        const data = await res.json();
        
        if (!data.results || data.results.length === 0) {
            resultsGrid.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon-wrap">
                        <svg viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" stroke-width="1.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
                    </div>
                    <p>No results found for "${q}"</p>
                </div>`;
            return;
        }

        // Staggered Animation Delay
        resultsGrid.innerHTML = data.results.map((r, i) => `
            <div class="result-card" style="animation-delay: ${i * 0.05}s">
                <div class="result-meta">
                    <span class="tag">Score: ${(r.score).toFixed(2)}</span>
                    <span class="tag">${r.category || 'unknown'}</span>
                    <span class="tag">${r.type || 'unknown'}</span>
                </div>
                <div class="result-path">${r.path}</div>
                <div class="result-snippet">${highlightKeywords(r.snippet, q)}...</div>
            </div>
        `).join('');
    } catch (err) {
        resultsGrid.innerHTML = `<div class="empty-state"><p>Error: ${err.message}</p></div>`;
    }
}

searchBtn.addEventListener('click', handleSearch);
searchInput.addEventListener('keypress', (e) => e.key === 'Enter' && handleSearch());

// Explorer Engine
const treeContainer = document.getElementById('file-tree');
const previewContent = document.getElementById('preview-content');
const previewModal = document.getElementById('preview-modal');

const buildTreeHtml = (items, parentPath = "") => {
    return items.map(item => `
        <div class="tree-item-container">
            <div class="tree-item ${item.is_dir ? 'tree-folder' : 'tree-file'}" data-path="${item.path}" data-isdir="${item.is_dir}">
                <span class="tree-icon">
                    ${item.is_dir 
                        ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>' 
                        : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>'}
                </span>
                ${item.name}
                ${item.tier ? `<span class="tag" style="margin-left:auto; transform:scale(0.8)">${item.tier}</span>` : ''}
            </div>
            <div class="tree-children" id="children-${btoa(item.path).replace(/=/g, '')}"></div>
        </div>
    `).join('');
};

let rootLoaded = false;
const loadExplorer = async () => {
    if (rootLoaded) return;
    treeContainer.innerHTML = '<div class="loading-spinner"></div>';
    
    try {
        const res = await fetch(`${API_BASE}/explorer?path=`);
        const data = await res.json();
        treeContainer.innerHTML = buildTreeHtml(data);
        rootLoaded = true;
    } catch (err) {
        treeContainer.innerHTML = `<p>Error loading workspace: ${err.message}</p>`;
    }
}

// Event delegation for recursive folder fetching
treeContainer.addEventListener('click', async (e) => {
    const item = e.target.closest('.tree-item');
    if (!item) return;

    const path = item.getAttribute('data-path');
    const isDir = item.getAttribute('data-isdir') === 'true';

    if (isDir) {
        item.classList.toggle('open');
        const childrenContainer = document.getElementById(`children-${btoa(path).replace(/=/g, '')}`);
        
        if (childrenContainer.classList.contains('active')) {
            childrenContainer.classList.remove('active');
        } else {
            // Fetch if empty
            if (childrenContainer.innerHTML === '') {
                childrenContainer.innerHTML = '<div class="loading-spinner" style="width:20px;height:20px;border-width:2px;margin:10px;"></div>';
                childrenContainer.classList.add('active');
                
                try {
                    const res = await fetch(`${API_BASE}/explorer?path=${encodeURIComponent(path)}`);
                    const data = await res.json();
                    childrenContainer.innerHTML = buildTreeHtml(data, path);
                } catch (err) {
                    childrenContainer.innerHTML = `<div style="color:red;padding:10px;">Load failed</div>`;
                }
            } else {
                childrenContainer.classList.add('active');
            }
        }
    } else {
        // File Click Preview
        document.querySelectorAll('.tree-item').forEach(i => i.style.borderColor = 'transparent');
        item.style.borderColor = 'var(--accent-main)';
        item.style.background = 'var(--bg-glass-hover)';
        
        previewModal.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon-wrap" style="width:60px;height:60px;">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:30px;height:30px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
                </div>
                <h3 style="font-size:1.2rem;">${path.split('/').pop()}</h3>
                <p>File content preview requires fetching from source.</p>
                <div style="display:flex;gap:10px;margin-top:20px;">
                    <span class="tag">Ready to Sync</span>
                </div>
            </div>
        `;
    }
});
