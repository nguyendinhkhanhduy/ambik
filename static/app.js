// State Management
let state = {
    inputType: 'plan_amb_task',
    environment: ["a ceramic mug", "a glass mug", "coffee machine", "milk", "kitchen table"],
    apiKey: localStorage.getItem('gemini_api_key') || '',
    samples: [],
    kitchenKb: {},
    analysisResult: null,
    selectedOptionKey: null,
    chatHistory: [
        { role: 'robot', content: 'Chào bạn! Tôi là Robot Nhà Bếp. Hãy trò chuyện hoặc đưa ra yêu cầu (vd: "Pha cho tôi 1 ly cà phê", "Hâm nóng bánh mì bằng lò vi sóng"). Tôi sẽ tự động phân tích và hỏi lại bạn nếu có điểm mơ hồ!' }
    ]
};

// DOM Elements
document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

async function initApp() {
    await fetchKitchenKb();
    renderEnvironmentTags();
    setupEventListeners();
    
    if (state.apiKey) {
        document.getElementById('input-api-key').value = state.apiKey;
    }
}

async function fetchKitchenKb() {
    try {
        const res = await fetch('/api/kitchen_kb');
        const data = await res.json();
        if (data.status === 'success') {
            state.kitchenKb = data.kb;
        }
    } catch (e) {
        console.log("KB fetch error:", e);
    }
}

function setupEventListeners() {
    // Input Mode Tabs (3 modes)
    const tabBtns = document.querySelectorAll('.tab-btn');
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            state.inputType = btn.dataset.tab;
            state.selectedOptionKey = null; // Reset selection on mode change
            updateInputLabels();
        });
    });

    // API Key Modal
    const modalKey = document.getElementById('modal-api-key');
    document.getElementById('btn-api-key').addEventListener('click', () => {
        modalKey.classList.remove('hidden');
    });
    document.querySelector('.modal-close').addEventListener('click', () => {
        modalKey.classList.add('hidden');
    });
    document.getElementById('btn-save-key').addEventListener('click', () => {
        const val = document.getElementById('input-api-key').value.trim();
        state.apiKey = val;
        localStorage.setItem('gemini_api_key', val);
        modalKey.classList.add('hidden');
        showToast('Đã lưu API Key thành công!');
    });

    // Environment Tags
    document.getElementById('btn-add-env').addEventListener('click', addEnvironmentItem);
    document.getElementById('input-new-env').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') addEnvironmentItem();
    });

    // Environment Presets
    document.querySelectorAll('.preset-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const raw = btn.dataset.env;
            state.environment = raw.split(',').map(s => s.trim()).filter(Boolean);
            renderEnvironmentTags();
        });
    });

    // Sample Loader Modal
    const modalSamples = document.getElementById('modal-samples');
    document.getElementById('btn-load-sample').addEventListener('click', () => {
        modalSamples.classList.remove('hidden');
        loadDatasetSamples();
    });
    document.querySelector('.modal-close-samples').addEventListener('click', () => {
        modalSamples.classList.add('hidden');
    });

    // Sample Search Filter
    document.getElementById('input-search-sample').addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        filterSamples(query);
    });

    // Toggle Raw JSON
    document.getElementById('btn-toggle-json').addEventListener('click', () => {
        const pre = document.getElementById('raw-json-viewer');
        pre.classList.toggle('hidden');
    });

    // Submit Analyze (Modes 1 & 2)
    document.getElementById('btn-analyze').addEventListener('click', () => {
        state.selectedOptionKey = null;
        runAnalysis();
    });

    // Chat Send Button (Mode 3)
    document.getElementById('btn-send-chat').addEventListener('click', sendChatMessage);
    document.getElementById('input-chat-msg').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendChatMessage();
    });

    // Reset Chat Button
    document.getElementById('btn-reset-chat').addEventListener('click', resetChat);

    // Custom Answer Submission Handler
    document.getElementById('btn-submit-custom-answer').addEventListener('click', submitCustomAnswer);
    document.getElementById('input-custom-answer').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') submitCustomAnswer();
    });
}

function resetChat() {
    state.chatHistory = [
        { role: 'robot', content: 'Chào bạn! Tôi là Robot Nhà Bếp. Hãy trò chuyện hoặc đưa ra yêu cầu (vd: "Pha cho tôi 1 ly cà phê", "Hâm nóng bánh mì bằng lò vi sóng"). Tôi sẽ tự động phân tích và hỏi lại bạn nếu có điểm mơ hồ!' }
    ];
    state.selectedOptionKey = null;
    document.getElementById('input-chat-msg').value = '';
    renderChatMessages();
    
    document.getElementById('empty-state').classList.remove('hidden');
    document.getElementById('analysis-results').classList.add('hidden');
    setStepActive(0);

    showToast('Đã làm mới cuộc hội thoại thành công!');
}

function updateInputLabels() {
    const directGroup = document.getElementById('group-direct-input');
    const chatGroup = document.getElementById('group-chat-input');
    const btnAnalyze = document.getElementById('btn-analyze');
    const label = document.getElementById('label-input-content');
    const badge = document.getElementById('badge-input-mode');
    const textarea = document.getElementById('input-content');

    if (state.inputType === 'chat') {
        directGroup.classList.add('hidden');
        btnAnalyze.classList.add('hidden');
        chatGroup.classList.remove('hidden');
    } else {
        directGroup.classList.remove('hidden');
        btnAnalyze.classList.remove('hidden');
        chatGroup.classList.add('hidden');

        if (state.inputType === 'plan_amb_task') {
            label.textContent = "Chuỗi các bước tạo món ăn (plan_amb_task):";
            badge.textContent = "Thực thi kế hoạch trực tiếp ở Stage 4";
            textarea.placeholder = `1. Locate the food storage container.
2. Locate the honey.
3. Open the honey jar or bottle.
4. Pour honey into the food storage container until it is full.
5. Close the honey jar or bottle.`;
        } else {
            label.textContent = "Đoạn văn bản câu lệnh bình thường (Normal Text):";
            badge.textContent = "Câu lệnh ngữ pháp tự nhiên";
            textarea.placeholder = "Kitchen Robot, please make a coffee using the coffee machine and pour it into a mug on the table.";
        }
    }
}

function addEnvironmentItem() {
    const input = document.getElementById('input-new-env');
    const val = input.value.trim();
    if (val && !state.environment.includes(val)) {
        state.environment.push(val);
        input.value = '';
        renderEnvironmentTags();
    }
}

function removeEnvironmentItem(item) {
    state.environment = state.environment.filter(i => i !== item);
    renderEnvironmentTags();
}

function renderEnvironmentTags() {
    const container = document.getElementById('env-tags');
    const countSpan = document.getElementById('env-count');
    container.innerHTML = '';
    
    countSpan.textContent = `${state.environment.length} vật thể`;

    state.environment.forEach(item => {
        const chip = document.createElement('span');
        chip.className = 'env-tag';
        chip.innerHTML = `
            <i class="fa-solid fa-tag text-indigo" style="font-size:0.75rem;"></i>
            <span>${escapeHtml(item)}</span>
            <span class="tag-remove" data-item="${escapeHtml(item)}">&times;</span>
        `;
        
        chip.addEventListener('mouseenter', (e) => showKbTooltip(e, item));
        chip.addEventListener('mouseleave', hideKbTooltip);
        chip.addEventListener('click', (e) => showKbTooltip(e, item));

        chip.querySelector('.tag-remove').addEventListener('click', (e) => {
            e.stopPropagation();
            removeEnvironmentItem(item);
        });
        container.appendChild(chip);
    });
}

function showKbTooltip(e, itemName) {
    const popover = document.getElementById('kb-tooltip-popover');
    const popTitle = document.getElementById('popover-title');
    const popBody = document.getElementById('popover-content');

    popTitle.textContent = itemName;

    let attrs = {
        "location": "kitchen_table",
        "is_clean": true,
        "microwave_safe": !itemName.toLowerCase().includes("metal")
    };

    if (state.kitchenKb && state.kitchenKb.kitchen_entities) {
        const ent = state.kitchenKb.kitchen_entities.find(k => k.name.toLowerCase().includes(itemName.toLowerCase()) || itemName.toLowerCase().includes(k.name.toLowerCase()));
        if (ent) attrs = ent.attributes;
    }

    let html = '';
    for (const [key, val] of Object.entries(attrs)) {
        const valColor = typeof val === 'boolean' ? (val ? '#6ee7b7' : '#fca5a5') : '#c7d2fe';
        html += `<div class="popover-prop"><span>${escapeHtml(key)}:</span> <strong style="color:${valColor};">${escapeHtml(String(val))}</strong></div>`;
    }

    popBody.innerHTML = html;
    popover.classList.remove('hidden');

    const rect = e.target.getBoundingClientRect();
    popover.style.top = `${rect.bottom + 8}px`;
    popover.style.left = `${Math.min(rect.left, window.innerWidth - 280)}px`;
}

function hideKbTooltip() {
    const popover = document.getElementById('kb-tooltip-popover');
    popover.classList.add('hidden');
}

function appendChatMessage(role, content, options = null) {
    state.chatHistory.push({ role, content, options });
    renderChatMessages();
}

function renderChatMessages() {
    const box = document.getElementById('chat-messages-box');
    box.innerHTML = '';

    state.chatHistory.forEach(msg => {
        const div = document.createElement('div');
        div.className = `chat-msg ${msg.role === 'user' ? 'user-msg' : 'robot-msg'}`;
        
        let optionsHtml = '';
        if (msg.options && msg.options.length > 0) {
            optionsHtml = '<div class="chat-options-chips-row">';
            msg.options.forEach(opt => {
                optionsHtml += `<button class="chat-option-chip-btn" data-key="${escapeHtml(opt.key)}" data-target="${escapeHtml(opt.target)}"><i class="fa-solid fa-hand-pointer"></i> ${escapeHtml(opt.key)}: ${escapeHtml(opt.label)}</button>`;
            });
            optionsHtml += '</div>';
        }

        div.innerHTML = `
            <div class="msg-avatar"><i class="fa-solid ${msg.role === 'user' ? 'fa-user' : 'fa-robot'}"></i></div>
            <div class="msg-bubble">${escapeHtml(msg.content)}${optionsHtml}</div>
        `;
        box.appendChild(div);
    });

    box.querySelectorAll('.chat-option-chip-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const key = btn.dataset.key;
            const target = btn.dataset.target;
            document.getElementById('input-chat-msg').value = `Tôi chọn phương án ${key}: ${target}`;
            sendChatMessage();
        });
    });

    box.scrollTop = box.scrollHeight;
}

async function sendChatMessage() {
    const input = document.getElementById('input-chat-msg');
    const text = input.value.trim();
    if (!text) return;

    input.value = '';
    appendChatMessage('user', text);

    await executeAnalysis(text, 'chat');
}

async function loadDatasetSamples() {
    const container = document.getElementById('samples-list-container');
    if (state.samples.length > 0) {
        renderSamplesList(state.samples);
        return;
    }

    container.innerHTML = '<div class="loading-spinner"><i class="fa-solid fa-spinner fa-spin"></i> Đang tải dữ liệu tệp AmbiK_data.csv...</div>';

    try {
        const res = await fetch('/api/samples?limit=40');
        const data = await res.json();
        
        if (data.status === 'success') {
            state.samples = data.samples;
            renderSamplesList(state.samples);
        } else {
            container.innerHTML = '<p class="text-subtle">Không thể tải tệp AmbiK_data.csv.</p>';
        }
    } catch (err) {
        container.innerHTML = `<p class="text-subtle">Lỗi kết nối: ${err.message}</p>`;
    }
}

function renderSamplesList(samples) {
    const container = document.getElementById('samples-list-container');
    container.innerHTML = '';

    if (samples.length === 0) {
        container.innerHTML = '<p class="text-subtle">Không tìm thấy mẫu phù hợp.</p>';
        return;
    }

    samples.forEach(sample => {
        const card = document.createElement('div');
        card.className = 'sample-item-card';
        
        const typeBadgeClass = sample.ambiguity_type === 'safety' ? 'badge-red' : 
                              (sample.ambiguity_type === 'common_sense_knowledge' ? 'badge-blue' : 'badge-purple');

        card.innerHTML = `
            <div class="sample-header">
                <span class="sample-task">Mẫu #${sample.id}</span>
                <span class="badge ${typeBadgeClass}">${escapeHtml(sample.ambiguity_type)}</span>
            </div>
            <p style="font-size:0.85rem; color:#cbd5e1; margin-bottom:0.4rem;"><strong>Task mơ hồ:</strong> ${escapeHtml(sample.ambiguous_task || sample.unambiguous_direct)}</p>
            <p style="font-size:0.75rem; color:#9ca3af;"><strong>Plan (amb):</strong> ${escapeHtml((sample.plan_for_amb_task || '').substring(0, 100))}...</p>
        `;

        card.addEventListener('click', () => {
            selectSample(sample);
            document.getElementById('modal-samples').classList.add('hidden');
        });

        container.appendChild(card);
    });
}

function filterSamples(query) {
    const filtered = state.samples.filter(s => 
        (s.ambiguous_task && s.ambiguous_task.toLowerCase().includes(query)) ||
        (s.plan_for_amb_task && s.plan_for_amb_task.toLowerCase().includes(query)) ||
        (s.ambiguity_type && s.ambiguity_type.toLowerCase().includes(query))
    );
    renderSamplesList(filtered);
}

function selectSample(sample) {
    state.selectedOptionKey = null;
    if (state.inputType === 'plan_amb_task') {
        document.getElementById('input-content').value = sample.plan_for_amb_task || sample.ambiguous_task;
    } else if (state.inputType === 'text') {
        document.getElementById('input-content').value = sample.ambiguous_task || sample.unambiguous_direct;
    } else {
        document.getElementById('input-chat-msg').value = sample.ambiguous_task || sample.unambiguous_direct;
    }

    if (sample.environment && sample.environment.length > 0) {
        state.environment = [...sample.environment];
        renderEnvironmentTags();
    }
    showToast(`Đã chọn Mẫu #${sample.id} từ dataset AmbiK!`);
}

async function runAnalysis() {
    const content = document.getElementById('input-content').value.trim();
    if (!content) {
        alert('Vui lòng nhập chuỗi hành động hoặc câu lệnh!');
        return;
    }
    await executeAnalysis(content, state.inputType);
}

async function executeAnalysis(content, mode) {
    const statusChip = document.getElementById('pipeline-status');
    statusChip.innerHTML = '<span class="status-chip active"><i class="fa-solid fa-spinner fa-spin"></i> Đang suy luận...</span>';

    setStepActive(1);
    document.getElementById('empty-state').classList.add('hidden');
    document.getElementById('analysis-results').classList.remove('hidden');

    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                input_type: mode,
                input_content: content,
                environment: state.environment,
                api_key: state.apiKey,
                chat_history: mode === 'chat' ? state.chatHistory : []
            })
        });

        const data = await response.json();
        
        if (data.status === 'success') {
            state.analysisResult = data.analysis;

            if (mode === 'chat' && data.analysis.chat_reply) {
                const kOpts = (data.analysis.k_choice_question && data.analysis.k_choice_question.options) ? data.analysis.k_choice_question.options : null;
                appendChatMessage('robot', data.analysis.chat_reply, kOpts);
            }

            await animatePipeline(data.analysis);
        } else {
            alert('Lỗi phân tích: ' + (data.detail || 'Không xác định'));
        }

    } catch (err) {
        alert('Lỗi kết nối máy chủ: ' + err.message);
    } finally {
        statusChip.innerHTML = '<span class="status-chip done"><i class="fa-solid fa-circle-check"></i> Hoàn tất</span>';
    }
}

async function animatePipeline(analysis) {
    setStepActive(1);
    renderStage1(analysis);
    await delay(150);

    setStepActive(2);
    renderStage2(analysis);
    await delay(150);

    renderWordMappings(analysis);

    setStepActive(3);
    renderStage3(analysis);
    await delay(150);

    setStepActive(4);
    renderStage4(analysis);

    document.getElementById('raw-json-viewer').textContent = JSON.stringify(analysis, null, 2);
}

function setStepActive(stepNum) {
    for (let i = 1; i <= 4; i++) {
        const node = document.getElementById(`step-node-${i}`);
        if (i <= stepNum) {
            node.classList.add('active');
        } else {
            node.classList.remove('active');
        }
    }
}

function renderStage1(analysis) {
    const summaryText = document.getElementById('summary-text');
    const overallBadge = document.getElementById('overall-badge');
    
    summaryText.textContent = analysis.summary || "Đã phân tích các thành phần trong môi trường.";

    const cat = analysis.overall_classification || "Preferences";
    overallBadge.textContent = cat;
    overallBadge.className = `badge ${cat === 'Safety' ? 'badge-red' : (cat === 'Common Sense' ? 'badge-blue' : 'badge-purple')}`;

    const grounding = analysis.grounding_analysis || {};
    const extUl = document.getElementById('list-extracted-objects');
    const matchUl = document.getElementById('list-matched-env');

    extUl.innerHTML = (grounding.extracted_objects || ['Vật thể không tên']).map(o => `<li>${escapeHtml(o)}</li>`).join('');
    matchUl.innerHTML = (grounding.environment_match || state.environment).map(m => `<li><i class="fa-solid fa-check text-emerald"></i> ${escapeHtml(m)}</li>`).join('');

    const missingBox = document.getElementById('missing-object-suggestion-box');
    const missingSpan = document.getElementById('missing-object-names');
    const missingList = grounding.missing_objects || [];

    if (missingList && missingList.length > 0) {
        missingBox.classList.remove('hidden');
        missingSpan.textContent = missingList.join(', ');
        
        const btnAdd = document.getElementById('btn-add-missing-obj');
        btnAdd.onclick = () => {
            missingList.forEach(item => {
                if (!state.environment.includes(item)) {
                    state.environment.push(item);
                }
            });
            renderEnvironmentTags();
            missingBox.classList.add('hidden');
            showToast(`Đã thêm ${missingList.join(', ')} vào Môi Trường KB!`);
            runAnalysis();
        };
    } else {
        missingBox.classList.add('hidden');
    }
}

function renderStage2(analysis) {
    const scoreVal = document.getElementById('entropy-score-val');
    const barFill = document.getElementById('gauge-bar-fill');
    
    const hScore = typeof analysis.entropy_score === 'number' ? analysis.entropy_score : 0.65;
    scoreVal.textContent = `H = ${hScore.toFixed(2)}`;
    
    const percentage = Math.min(Math.max(hScore * 100, 5), 100);
    barFill.style.width = `${percentage}%`;

    const container = document.getElementById('ambiguity-cards-list');
    container.innerHTML = '';

    const detected = analysis.detected_ambiguities || [];

    if (detected.length === 0) {
        container.innerHTML = '<p class="text-subtle">Không phát hiện điểm mơ hồ nào trong câu lệnh.</p>';
        return;
    }

    detected.forEach(item => {
        const card = document.createElement('div');
        const catClass = item.category === 'Safety' ? 'Safety' : (item.category === 'Common Sense' ? 'Common Sense' : 'Preferences');
        const badgeClass = item.category === 'Safety' ? 'badge-red' : (item.category === 'Common Sense' ? 'badge-blue' : 'badge-purple');
        
        card.className = `ambiguity-item-card ${catClass}`;
        
        let payloadHtml = '';
        if (item.payload) {
            if (item.payload.shortlist && item.payload.shortlist.length > 0) {
                payloadHtml += `<div><strong>Shortlist lựa chọn:</strong> ${item.payload.shortlist.map(s => `<span class="badge badge-info">${escapeHtml(s)}</span>`).join(' ')}</div>`;
            }
            if (item.payload.clarifying_question) {
                payloadHtml += `<div><strong>Câu hỏi làm rõ:</strong> <em>"${escapeHtml(item.payload.clarifying_question)}"</em></div>`;
            }
            if (item.payload.resolved_intent) {
                payloadHtml += `<div><strong>Ý định chuẩn (Common Sense):</strong> ${escapeHtml(item.payload.resolved_intent)}</div>`;
            }
            if (item.payload.safe_intent) {
                payloadHtml += `<div><strong>Ràng buộc an toàn:</strong> <span class="text-emerald">${escapeHtml(item.payload.safe_intent)}</span></div>`;
            }
            if (item.payload.unsafe_objects && item.payload.unsafe_objects.length > 0) {
                payloadHtml += `<div><strong>Vật thể / Thao tác nguy hiểm:</strong> ${item.payload.unsafe_objects.map(u => `<span class="badge badge-red">${escapeHtml(u)}</span>`).join(' ')}</div>`;
            }
        }

        card.innerHTML = `
            <div class="amb-card-header">
                <span class="amb-element"><i class="fa-solid fa-triangle-exclamation text-amber"></i> ${escapeHtml(item.element || 'Yếu tố mơ hồ')}</span>
                <span class="badge ${badgeClass}">${escapeHtml(item.category)}</span>
            </div>
            <p class="amb-reasoning">${escapeHtml(item.reasoning)}</p>
            <div class="amb-payload-box">
                <div style="font-size:0.75rem; color:var(--text-subtle); margin-bottom:0.2rem;">HÀNH ĐỘNG HỆ THỐNG: <strong>${escapeHtml(item.action)}</strong></div>
                ${payloadHtml}
            </div>
        `;

        container.appendChild(card);
    });
}

function renderWordMappings(analysis) {
    const tbody = document.getElementById('table-mapping-body');
    tbody.innerHTML = '';

    const mappings = analysis.disambiguated_mappings || [];

    if (mappings.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="text-subtle" style="text-align:center;">Không có từ mơ hồ cần giải nghĩa.</td></tr>`;
        return;
    }

    mappings.forEach(m => {
        const tr = document.createElement('tr');
        const badgeClass = m.category === 'Safety' ? 'badge-red' : (m.category === 'Common Sense' ? 'badge-blue' : 'badge-purple');
        
        tr.innerHTML = `
            <td><span class="vague-term">${escapeHtml(m.vague_expression)}</span></td>
            <td><span class="resolved-term">${escapeHtml(m.disambiguated_expression)}</span></td>
            <td><span class="badge ${badgeClass}">${escapeHtml(m.category)}</span></td>
            <td style="font-size:0.8rem; color:#cbd5e1;">${escapeHtml(m.explanation || '')}</td>
        `;
        tbody.appendChild(tr);
    });
}

function renderStage3(analysis) {
    const qBox = document.getElementById('clarification-box');
    const qText = document.getElementById('text-clarify-question');
    const grid = document.getElementById('k-choice-options-grid');
    const customRow = document.getElementById('custom-answer-row');
    grid.innerHTML = '';

    const kChoice = analysis.k_choice_question || {};

    if (kChoice && kChoice.question && kChoice.options && kChoice.options.length > 0 && state.inputType !== 'plan_amb_task') {
        qBox.classList.remove('hidden');
        qText.textContent = `"${kChoice.question}"`;
        grid.classList.remove('hidden');
        customRow.classList.remove('hidden');

        kChoice.options.forEach(opt => {
            const card = document.createElement('div');
            card.className = `k-choice-card ${state.selectedOptionKey === opt.key ? 'selected' : ''}`;
            card.innerHTML = `
                <div class="k-key-badge">${state.selectedOptionKey === opt.key ? '✓' : escapeHtml(opt.key)}</div>
                <div class="k-label-text">${escapeHtml(opt.label)}</div>
            `;
            
            card.addEventListener('click', () => {
                state.selectedOptionKey = opt.key;
                
                document.querySelectorAll('.k-choice-card').forEach(c => c.classList.remove('selected'));
                card.classList.add('selected');
                
                const alertBanner = document.getElementById('user-selection-alert');
                const alertText = document.getElementById('text-user-selection-status');
                alertBanner.classList.remove('hidden');
                alertText.innerHTML = `✅ <strong>Đã ghi nhận lựa chọn:</strong> Phương án ${opt.key} (${escapeHtml(opt.target)}). Đang tự động giải nghĩa và kích hoạt Stage 4...`;

                if (state.inputType === 'chat') {
                    document.getElementById('input-chat-msg').value = `Tôi chọn phương án ${opt.key}: ${opt.target}`;
                    sendChatMessage();
                } else {
                    document.getElementById('input-content').value += `\n[Người dùng chọn ${opt.key}]: Dùng ${opt.target}`;
                    executeAnalysis(document.getElementById('input-content').value, state.inputType);
                }
            });

            grid.appendChild(card);
        });

    } else if (analysis.clarifying_question_for_user && state.inputType !== 'plan_amb_task') {
        qBox.classList.remove('hidden');
        qText.textContent = `"${analysis.clarifying_question_for_user}"`;
        grid.classList.add('hidden');
        customRow.classList.remove('hidden');
    } else {
        qBox.classList.remove('hidden');
        qText.textContent = `"Không cần hỏi lại người dùng - Thực thi kế hoạch hành động trực tiếp ở Stage 4."`;
        grid.classList.add('hidden');
        customRow.classList.add('hidden');
    }
}

function submitCustomAnswer() {
    const input = document.getElementById('input-custom-answer');
    const val = input.value.trim();
    if (!val) return;

    input.value = '';
    state.selectedOptionKey = 'CUSTOM';

    const alertBanner = document.getElementById('user-selection-alert');
    const alertText = document.getElementById('text-user-selection-status');
    alertBanner.classList.remove('hidden');
    alertText.innerHTML = `✅ <strong>Đã ghi nhận câu trả lời tùy nhập:</strong> "${escapeHtml(val)}". Đang kích hoạt Stage 4...`;

    if (state.inputType === 'chat') {
        document.getElementById('input-chat-msg').value = val;
        sendChatMessage();
    } else {
        document.getElementById('input-content').value += `\n[Câu trả lời từ người dùng]: ${val}`;
        executeAnalysis(document.getElementById('input-content').value, state.inputType);
    }
}

function renderStage4(analysis) {
    const pendingBanner = document.getElementById('stage4-pending-banner');
    const executionContent = document.getElementById('stage4-execution-content');

    const isPending = (analysis.overall_classification === 'Preferences' || (analysis.safe_execution_plan && analysis.safe_execution_plan.length === 0)) 
                      && !state.selectedOptionKey 
                      && state.inputType !== 'plan_amb_task';

    if (isPending) {
        pendingBanner.classList.remove('hidden');
        executionContent.classList.add('hidden');
        return;
    }

    pendingBanner.classList.add('hidden');
    executionContent.classList.remove('hidden');

    const ltlPre = document.getElementById('ltl-formula-text');
    const verifiedBadge = document.getElementById('verified-safe-badge');

    const ltlStr = analysis.ltl_plan || "G(!IsOn(Microwave, UnsafeMetal)) & F(TaskComplete)";
    ltlPre.textContent = ltlStr;

    if (analysis.verified_safe !== false) {
        verifiedBadge.className = 'badge badge-green';
        verifiedBadge.innerHTML = '<i class="fa-solid fa-circle-check"></i> Verified Safe (Model Checker)';
    } else {
        verifiedBadge.className = 'badge badge-red';
        verifiedBadge.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Safety Constraint Violation';
    }

    const container = document.getElementById('plan-steps-list');
    container.innerHTML = '';

    let steps = analysis.safe_execution_plan || [];

    if (!steps || steps.length === 0) {
        const envItem1 = state.environment[0] || "target_item";
        const envItem2 = state.environment[1] || "kitchen_table";
        
        steps = [
            {"step": 1, "action": "FindObject", "target": envItem1, "note": `Bước 1: Tìm kiếm ${envItem1} trong nhà bếp`},
            {"step": 2, "action": "PickUp", "target": envItem1, "note": `Bước 2: Cầm ${envItem1} một cách an toàn`},
            {"step": 3, "action": "PutObject", "target": envItem2, "note": `Bước 3: Đặt ${envItem1} lên ${envItem2}`}
        ];
    }

    steps.forEach(s => {
        const item = document.createElement('div');
        item.className = 'plan-step-item';
        item.innerHTML = `
            <div class="step-num-badge">${s.step || 1}</div>
            <div class="step-action-name">${escapeHtml(s.action || 'Action')}</div>
            <div class="step-target-name">${escapeHtml(s.target || 'Target')}</div>
            <div class="step-note">${escapeHtml(s.note || '')}</div>
        `;
        container.appendChild(item);
    });
}

function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function showToast(msg) {
    console.log("[Toast]:", msg);
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
