/**
 * Centro de Controle - Main Application
 * Dashboard pessoal do Fábio
 */

// ============================================
// INITIALIZATION
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

async function initApp() {
    updateCurrentDate();
    await loadAllData();
    setInterval(loadAllData, 5 * 60 * 1000);
}

function updateCurrentDate() {
    const dateEl = document.getElementById('current-date');
    if (!dateEl) return;
    const options = { weekday: 'long', day: 'numeric', month: 'long' };
    const today = new Date().toLocaleDateString('pt-BR', options);
    dateEl.textContent = today.charAt(0).toUpperCase() + today.slice(1);
}

async function loadAllData() {
    try {
        await Promise.all([
            refreshToday(),
            loadTasks(),
            loadProjects(),
            loadReminders(),
            loadNotes(),
        ]);
    } catch (error) {
        console.error('Error loading data:', error);
    }
}

// ============================================
// TODAY SECTION
// ============================================

async function refreshToday() {
    try {
        const data = await TodayAPI.getSummary();
        document.getElementById('stat-todo').textContent = data.stats?.todo || 0;
        document.getElementById('stat-doing').textContent = data.stats?.doing || 0;
        document.getElementById('stat-done').textContent = data.stats?.done_today || 0;
        
        const eventsEl = document.getElementById('events-list');
        const allEvents = data.events || [];
        
        if (allEvents.length > 0) {
            eventsEl.innerHTML = allEvents.map(event => {
                const eventTime = event.time || event.event_time || '—';
                const location = event.location ? `<span class="event-location">📍 ${escapeHtml(event.location)}</span>` : '';
                const isGoogleCal = event.time !== undefined;
                
                return `
                    <div class="event-item ${isGoogleCal ? 'google-cal' : 'local'}">
                        <span class="event-time">${eventTime}</span>
                        <div class="event-details">
                            <span class="event-title">${escapeHtml(event.title)}</span>
                            ${location}
                        </div>
                    </div>
                `;
            }).join('');
        } else {
            eventsEl.innerHTML = '<p class="empty-state">Sem eventos hoje</p>';
        }
        
        const urgentEl = document.getElementById('urgent-list');
        if (data.urgent_tasks?.length > 0) {
            urgentEl.innerHTML = data.urgent_tasks.slice(0, 3).map(task => `
                <div class="urgent-item" onclick="editTask(${task.id})">
                    ${escapeHtml(task.title)}
                </div>
            `).join('');
        } else {
            urgentEl.innerHTML = '<p class="empty-state">Nenhuma tarefa urgente 🎉</p>';
        }
        
    } catch (error) {
        console.error('Error refreshing today:', error);
    }
}

// ============================================
// TASKS (KANBAN)
// ============================================

let allTasks = [];

async function loadTasks() {
    try {
        allTasks = await TasksAPI.getAll();
        renderTasks();
    } catch (error) {
        console.error('Error loading tasks:', error);
    }
}

function renderTasks() {
    const statuses = ['todo', 'doing', 'done'];
    
    statuses.forEach(status => {
        const tasks = allTasks.filter(t => t.status === status);
        const container = document.getElementById(`tasks-${status}`);
        const count = document.getElementById(`count-${status}`);
        
        if (!container) return;
        count.textContent = tasks.length;
        
        if (tasks.length > 0) {
            container.innerHTML = tasks.map(task => `
                <div class="task-card" data-priority="${task.priority}" onclick="editTask(${task.id})">
                    <div class="task-title">${escapeHtml(task.title)}</div>
                    <div class="task-meta">
                        ${task.due_date ? `<span>📅 ${formatDate(task.due_date)}</span>` : '<span></span>'}
                        ${task.priority === 'urgent' || task.priority === 'high' 
                            ? `<span class="task-priority ${task.priority}">${task.priority === 'urgent' ? '🔥 URGENTE' : '⚡ ALTA'}</span>` 
                            : ''}
                    </div>
                    <div class="task-actions" onclick="event.stopPropagation()">
                        ${status !== 'todo' ? `<button class="task-action-btn" onclick="moveTask(${task.id}, 'todo')">← A Fazer</button>` : ''}
                        ${status !== 'doing' ? `<button class="task-action-btn" onclick="moveTask(${task.id}, 'doing')">🔄 Fazendo</button>` : ''}
                        ${status !== 'done' ? `<button class="task-action-btn" onclick="moveTask(${task.id}, 'done')">✓ Feito</button>` : ''}
                        <button class="task-action-btn delete" onclick="deleteTask(${task.id})">🗑</button>
                    </div>
                </div>
            `).join('');
        } else {
            container.innerHTML = '<p class="empty-state">Vazio</p>';
        }
    });
}

async function moveTask(id, newStatus) {
    try {
        await TasksAPI.update(id, { status: newStatus });
        await loadTasks();
        await refreshToday();
    } catch (error) {
        alert('Erro ao mover tarefa: ' + error.message);
    }
}

async function deleteTask(id) {
    if (!confirm('Deletar esta tarefa?')) return;
    try {
        await TasksAPI.delete(id);
        await loadTasks();
        await refreshToday();
    } catch (error) {
        alert('Erro ao deletar: ' + error.message);
    }
}

function openTaskModal(taskId = null) {
    const modal = document.getElementById('task-modal');
    const form = document.getElementById('task-form');
    const title = document.getElementById('task-modal-title');
    
    form?.reset();
    document.getElementById('task-id').value = '';
    
    if (taskId) {
        const task = allTasks.find(t => t.id === taskId);
        if (task) {
            title.textContent = 'Editar Tarefa';
            document.getElementById('task-id').value = task.id;
            document.getElementById('task-title').value = task.title;
            document.getElementById('task-description').value = task.description || '';
            document.getElementById('task-priority').value = task.priority;
            document.getElementById('task-status').value = task.status;
            document.getElementById('task-due-date').value = task.due_date || '';
        }
    } else {
        title.textContent = 'Nova Tarefa';
    }
    
    modal?.classList.add('active');
}

function closeTaskModal() {
    document.getElementById('task-modal')?.classList.remove('active');
}

function editTask(id) {
    openTaskModal(id);
}

async function saveTask(event) {
    event.preventDefault();
    
    const id = document.getElementById('task-id').value;
    const task = {
        title: document.getElementById('task-title').value,
        description: document.getElementById('task-description').value || null,
        priority: document.getElementById('task-priority').value,
        status: document.getElementById('task-status').value,
        due_date: document.getElementById('task-due-date').value || null,
    };
    
    try {
        if (id) {
            await TasksAPI.update(parseInt(id), task);
        } else {
            await TasksAPI.create(task);
        }
        
        closeTaskModal();
        await loadTasks();
        await refreshToday();
    } catch (error) {
        alert('Erro ao salvar: ' + error.message);
    }
}

// ============================================
// REMINDERS
// ============================================

let allReminders = [];

async function loadReminders() {
    try {
        allReminders = await RemindersAPI.getAll();
        renderReminders();
    } catch (error) {
        console.error('Error loading reminders:', error);
    }
}

function renderReminders() {
    const container = document.getElementById('reminders-list');
    if (!container) return;
    
    if (allReminders.length > 0) {
        container.innerHTML = allReminders.slice(0, 7).map(reminder => `
            <div class="reminder-item" data-priority="${reminder.priority}">
                <div class="reminder-check" onclick="completeReminder(${reminder.id})"></div>
                <div class="reminder-content">
                    <div class="reminder-title">${escapeHtml(reminder.title)}</div>
                    <div class="reminder-time">${formatDateTime(reminder.due_datetime)}</div>
                </div>
                <button class="reminder-delete" onclick="deleteReminder(${reminder.id})">✕</button>
            </div>
        `).join('');
    } else {
        container.innerHTML = '<p class="empty-state">Sem lembretes pendentes 🎉</p>';
    }
}

async function completeReminder(id) {
    try {
        await RemindersAPI.complete(id);
        await loadReminders();
    } catch (error) {
        alert('Erro: ' + error.message);
    }
}

async function deleteReminder(id) {
    try {
        await RemindersAPI.delete(id);
        await loadReminders();
    } catch (error) {
        alert('Erro: ' + error.message);
    }
}

function openReminderModal() {
    const modal = document.getElementById('reminder-modal');
    const form = document.getElementById('reminder-form');
    form?.reset();
    
    const now = new Date();
    now.setHours(now.getHours() + 1);
    now.setMinutes(0);
    document.getElementById('reminder-datetime').value = now.toISOString().slice(0, 16);
    
    modal?.classList.add('active');
}

function closeReminderModal() {
    document.getElementById('reminder-modal')?.classList.remove('active');
}

async function saveReminder(event) {
    event.preventDefault();
    
    const reminder = {
        title: document.getElementById('reminder-title').value,
        due_datetime: document.getElementById('reminder-datetime').value,
        priority: document.getElementById('reminder-priority').value,
    };
    
    try {
        await RemindersAPI.create(reminder);
        closeReminderModal();
        await loadReminders();
        await refreshToday();
    } catch (error) {
        alert('Erro ao salvar: ' + error.message);
    }
}

// ============================================
// NOTES
// ============================================

let allNotes = [];

async function loadNotes() {
    try {
        allNotes = await NotesAPI.getAll(10);
        renderNotes();
    } catch (error) {
        console.error('Error loading notes:', error);
    }
}

function renderNotes() {
    const container = document.getElementById('notes-list');
    if (!container) return;
    
    if (allNotes.length > 0) {
        container.innerHTML = allNotes.slice(0, 5).map(note => `
            <div class="note-item" onclick="editNote(${note.id})">
                <div class="note-header">
                    <span class="note-title">${escapeHtml(note.title)}</span>
                    <span class="note-date">${note.meeting_date ? formatDate(note.meeting_date) : ''}</span>
                </div>
                ${note.content ? `<p class="note-preview">${escapeHtml(note.content.substring(0, 100))}...</p>` : ''}
            </div>
        `).join('');
    } else {
        container.innerHTML = '<p class="empty-state">Sem notas</p>';
    }
}

function openNoteModal(noteId = null) {
    const modal = document.getElementById('note-modal');
    const form = document.getElementById('note-form');
    const title = document.getElementById('note-modal-title');
    
    form?.reset();
    document.getElementById('note-id').value = '';
    
    if (noteId) {
        const note = allNotes.find(n => n.id === noteId);
        if (note) {
            title.textContent = 'Editar Nota';
            document.getElementById('note-id').value = note.id;
            document.getElementById('note-title').value = note.title;
            document.getElementById('note-date').value = note.meeting_date || '';
            document.getElementById('note-content').value = note.content || '';
            document.getElementById('note-tags').value = note.tags || '';
        }
    } else {
        title.textContent = 'Nova Nota';
        document.getElementById('note-date').value = new Date().toISOString().slice(0, 10);
    }
    
    modal?.classList.add('active');
}

function closeNoteModal() {
    document.getElementById('note-modal')?.classList.remove('active');
}

function editNote(id) {
    openNoteModal(id);
}

async function saveNote(event) {
    event.preventDefault();
    
    const id = document.getElementById('note-id').value;
    const note = {
        title: document.getElementById('note-title').value,
        meeting_date: document.getElementById('note-date').value || null,
        content: document.getElementById('note-content').value || null,
        tags: document.getElementById('note-tags').value || null,
    };
    
    try {
        if (id) {
            await NotesAPI.update(parseInt(id), note);
        } else {
            await NotesAPI.create(note);
        }
        
        closeNoteModal();
        await loadNotes();
    } catch (error) {
        alert('Erro ao salvar: ' + error.message);
    }
}

// ============================================
// PROJECTS
// ============================================

let allProjects = [];

async function loadProjects() {
    try {
        allProjects = await ProjectsAPI.getAll();
        renderProjects();
    } catch (error) {
        console.error('Error loading projects:', error);
    }
}

function renderProjects() {
    const bar = document.getElementById('projects-bar');
    if (!bar) return;
    
    const activeProjects = allProjects.filter(p => p.status !== 'archived');
    
    const categoryIcons = {
        'trabalho': '💼',
        'mba': '🎓',
        'pessoal': '👤',
        'familia': '👨‍👩‍👧'
    };
    
    let html = activeProjects.map(project => {
        const icon = categoryIcons[project.category] || '📁';
        const priorityClass = project.priority === 'high' ? 'priority-high' : '';
        const shortName = project.name.length > 15 ? project.name.substring(0, 15) + '…' : project.name;
        
        return `
            <div class="project-chip ${priorityClass}" onclick="openProject(${project.id})">
                <span class="chip-icon">${icon}</span>
                <span class="chip-name">${escapeHtml(shortName)}</span>
            </div>
        `;
    }).join('');
    
    html += `
        <div class="project-chip project-chip-add" onclick="openProjectModal()">
            <span class="chip-icon">+</span>
            <span class="chip-name">Novo</span>
        </div>
    `;
    
    bar.innerHTML = html;
}

function openProject(id) {
    window.location.href = `project.html?id=${id}`;
}

function openProjectModal(projectId = null) {
    const modal = document.getElementById('project-modal');
    const form = document.getElementById('project-form');
    const title = document.getElementById('project-modal-title');
    
    form?.reset();
    document.getElementById('project-id').value = '';
    document.getElementById('project-progress').value = 0;
    
    if (projectId) {
        const project = allProjects.find(p => p.id === projectId);
        if (project) {
            title.textContent = 'Editar Projeto';
            document.getElementById('project-id').value = project.id;
            document.getElementById('project-name').value = project.name;
            document.getElementById('project-description').value = project.description || '';
            document.getElementById('project-category').value = project.category || 'pessoal';
            document.getElementById('project-priority').value = project.priority || 'normal';
            document.getElementById('project-status').value = project.status || 'active';
            document.getElementById('project-progress').value = project.progress || 0;
            document.getElementById('project-due-date').value = project.due_date || '';
            document.getElementById('project-tags').value = project.tags || '';
        }
    } else {
        title.textContent = 'Novo Projeto';
    }
    
    modal?.classList.add('active');
}

function closeProjectModal() {
    document.getElementById('project-modal')?.classList.remove('active');
}

async function saveProject(event) {
    event.preventDefault();
    
    const id = document.getElementById('project-id').value;
    const project = {
        name: document.getElementById('project-name').value,
        description: document.getElementById('project-description').value || null,
        category: document.getElementById('project-category').value,
        priority: document.getElementById('project-priority').value,
        status: document.getElementById('project-status').value,
        progress: parseInt(document.getElementById('project-progress').value) || 0,
        due_date: document.getElementById('project-due-date').value || null,
        tags: document.getElementById('project-tags').value || null,
    };
    
    try {
        if (id) {
            await ProjectsAPI.update(parseInt(id), project);
        } else {
            await ProjectsAPI.create(project);
        }
        
        closeProjectModal();
        await loadProjects();
    } catch (error) {
        alert('Erro ao salvar: ' + error.message);
    }
}

// ============================================
// UTILITIES
// ============================================

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr + 'T00:00:00');
    return date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
}

function formatDateTime(dateTimeStr) {
    if (!dateTimeStr) return '';
    const date = new Date(dateTimeStr);
    return date.toLocaleString('pt-BR', { 
        day: '2-digit', 
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// ============================================
// KEYBOARD SHORTCUTS
// ============================================

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeTaskModal();
        closeReminderModal();
        closeNoteModal();
        closeProjectModal();
    }
    
    if (e.ctrlKey && e.key === 'n') {
        e.preventDefault();
        openTaskModal();
    }
});

// Close modals on backdrop click
document.querySelectorAll('.modal').forEach(modal => {
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.remove('active');
        }
    });
});
