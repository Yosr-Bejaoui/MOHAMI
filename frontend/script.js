document.addEventListener('DOMContentLoaded', () => {
    const askForm = document.getElementById('askForm');
    const questionInput = document.getElementById('questionInput');
    const chatContainer = document.getElementById('chatContainer');
    const sendBtn = document.getElementById('sendBtn');
    
    // Templates
    const userMessageTemplate = document.getElementById('userMessageTemplate');
    const aiMessageTemplate = document.getElementById('aiMessageTemplate');
    const sourceCardTemplate = document.getElementById('sourceCardTemplate');

    // Auto-resize textarea
    questionInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
        if (this.value.trim() !== '') {
            sendBtn.removeAttribute('disabled');
        } else {
            sendBtn.setAttribute('disabled', 'true');
        }
    });

    // Handle Enter key (Shift+Enter for newline)
    questionInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (this.value.trim() !== '') {
                askForm.dispatchEvent(new Event('submit'));
            }
        }
    });

    window.highlightSource = function(article, law) {
        const sourceCards = document.querySelectorAll('.source-card');
        let found = false;
        
        sourceCards.forEach(card => {
            const articleText = card.querySelector('.source-article').textContent;
            const artNum = articleText.replace(/Art\.?\s*/i, '').trim();
            const searchedNum = article.replace(/Article\s*/i, '').trim();
            
            if (artNum.toLowerCase() === searchedNum.toLowerCase()) {
                card.scrollIntoView({ behavior: 'smooth', block: 'center' });
                card.classList.remove('highlighted');
                void card.offsetWidth; // Trigger reflow
                card.classList.add('highlighted');
                found = true;
            }
        });
    };

    // Simple markdown to HTML parser for the answer text
    function parseMarkdown(text) {
        let html = text
            .replace(/\[(Article\s+[^,\]]+),\s*([^\]]+)\]/gi, `<span class="citation-badge" onclick="highlightSource('$1', '$2')">📜 $1</span>`)
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>');
        return `<p>${html}</p>`;
    }

    function scrollToBottom() {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function addMessage(type, content = null) {
        const template = type === 'user' ? userMessageTemplate : aiMessageTemplate;
        const clone = template.content.cloneNode(true);
        const messageEl = clone.querySelector('.message');
        
        if (type === 'user') {
            clone.querySelector('.message-bubble').textContent = content;
        } else {
            // Add typing indicator initially for AI messages
            const textContent = clone.querySelector('.text-content');
            textContent.innerHTML = `
                <div class="typing-indicator">
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                </div>
            `;
        }
        
        chatContainer.appendChild(clone);
        scrollToBottom();
        return messageEl;
    }

    function updateAIMessage(messageEl, data) {
        // Update Domain Badge
        const domainBadge = messageEl.querySelector('.domain-badge');
        const domainText = messageEl.querySelector('.domain-text');
        
        if (data.detected_domain && data.detected_domain !== 'default') {
            domainText.textContent = `Domaine juridique : ${data.detected_domain}`;
            domainBadge.classList.remove('hidden');
        } else {
            domainBadge.classList.add('hidden');
        }

        // Update Answer Text
        const textContent = messageEl.querySelector('.text-content');
        textContent.innerHTML = parseMarkdown(data.answer);

        // Update Sources
        if (data.sources && data.sources.length > 0) {
            const sourcesContainer = messageEl.querySelector('.sources-container');
            const sourcesGrid = messageEl.querySelector('.sources-grid');
            
            data.sources.forEach(source => {
                const sourceClone = sourceCardTemplate.content.cloneNode(true);
                
                // Format law name (e.g. code_penal -> Code Pénal)
                let lawName = source.law.replace(/_/g, ' ');
                lawName = lawName.charAt(0).toUpperCase() + lawName.slice(1);
                
                sourceClone.querySelector('.source-law').textContent = lawName;
                sourceClone.querySelector('.source-article').textContent = `Art. ${source.article}`;
                sourceClone.querySelector('.source-excerpt').textContent = source.excerpt;
                
                sourcesGrid.appendChild(sourceClone);
            });
            
            sourcesContainer.classList.remove('hidden');
        }
        
        scrollToBottom();
    }

    askForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const question = questionInput.value.trim();
        if (!question) return;

        // Reset input
        questionInput.value = '';
        questionInput.style.height = 'auto';
        sendBtn.setAttribute('disabled', 'true');

        // Add user message
        addMessage('user', question);

        // Add AI loading message
        const aiMessageEl = addMessage('ai');

        try {
            const response = await fetch('/api/ask', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ question })
            });

            if (!response.ok) {
                throw new Error('API Error');
            }

            const data = await response.json();
            updateAIMessage(aiMessageEl, data);

        } catch (error) {
            console.error('Error fetching answer:', error);
            const textContent = aiMessageEl.querySelector('.text-content');
            textContent.innerHTML = `<p style="color: var(--warning);">Désolé, une erreur de connexion est survenue. Veuillez réessayer.</p>`;
            aiMessageEl.querySelector('.domain-text').textContent = 'Erreur';
        }
    });
});
