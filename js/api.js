/**
 * Centro de Controle - API Client
 * Comunicação com o backend FastAPI
 */

// Detectar se está rodando no GitHub Pages ou localmente
const isGitHubPages = window.location.hostname.includes('github.io');
const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';

// API Base: usa VPS quando no GitHub Pages, relativo quando local/VPS
const API_BASE = (isGitHubPages) 
    ? 'http://76.13.226.10:8100/api'  // VPS Backend
    : '/api';  // Local ou servido pela própria VPS

/**
 * Helper para fazer requisições à API
 */
async function apiRequest(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
        },
    };
    
    const config = { ...defaultOptions, ...options };
    
    try {
        const response = await fetch(url, config);
        
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Erro desconhecido' }));
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error(`API Error [${endpoint}]:`, error);
        throw error;
    }
}

// ============================================
// TASKS API
// ============================================

const TasksAPI = {
    async getAll(status = null) {
        const query = status ? `?status=${status}` : '';
        return apiRequest(`/tasks${query}`);
    },
    
    async create(task) {
        return apiRequest('/tasks', {
            method: 'POST',
            body: JSON.stringify(task),
        });
    },
    
    async update(id, updates) {
        return apiRequest(`/tasks/${id}`, {
            method: 'PUT',
            body: JSON.stringify(updates),
        });
    },
    
    async delete(id) {
        return apiRequest(`/tasks/${id}`, {
            method: 'DELETE',
        });
    },
};

// ============================================
// REMINDERS API
// ============================================

const RemindersAPI = {
    async getAll(includeCompleted = false) {
        const query = includeCompleted ? '?include_completed=true' : '';
        return apiRequest(`/reminders${query}`);
    },
    
    async create(reminder) {
        return apiRequest('/reminders', {
            method: 'POST',
            body: JSON.stringify(reminder),
        });
    },
    
    async complete(id) {
        return apiRequest(`/reminders/${id}/complete`, {
            method: 'PUT',
        });
    },
    
    async delete(id) {
        return apiRequest(`/reminders/${id}`, {
            method: 'DELETE',
        });
    },
};

// ============================================
// NOTES API
// ============================================

const NotesAPI = {
    async getAll(limit = 10) {
        return apiRequest(`/notes?limit=${limit}`);
    },
    
    async create(note) {
        return apiRequest('/notes', {
            method: 'POST',
            body: JSON.stringify(note),
        });
    },
    
    async update(id, note) {
        return apiRequest(`/notes/${id}`, {
            method: 'PUT',
            body: JSON.stringify(note),
        });
    },
    
    async delete(id) {
        return apiRequest(`/notes/${id}`, {
            method: 'DELETE',
        });
    },
};

// ============================================
// TODAY API
// ============================================

const TodayAPI = {
    async getSummary() {
        return apiRequest('/today');
    },
};

// ============================================
// EVENTS API
// ============================================

const EventsAPI = {
    async getAll(date = null) {
        const query = date ? `?date=${date}` : '';
        return apiRequest(`/events${query}`);
    },
    
    async create(event) {
        return apiRequest('/events', {
            method: 'POST',
            body: JSON.stringify(event),
        });
    },
    
    async delete(id) {
        return apiRequest(`/events/${id}`, {
            method: 'DELETE',
        });
    },
};

// ============================================
// PROJECTS API
// ============================================

const ProjectsAPI = {
    async getAll(status = null, category = null) {
        let query = [];
        if (status) query.push(`status=${status}`);
        if (category) query.push(`category=${category}`);
        const queryStr = query.length > 0 ? '?' + query.join('&') : '';
        return apiRequest(`/projects${queryStr}`);
    },
    
    async create(project) {
        return apiRequest('/projects', {
            method: 'POST',
            body: JSON.stringify(project),
        });
    },
    
    async update(id, updates) {
        return apiRequest(`/projects/${id}`, {
            method: 'PUT',
            body: JSON.stringify(updates),
        });
    },
    
    async updateProgress(id, progress) {
        return apiRequest(`/projects/${id}/progress?progress=${progress}`, {
            method: 'PUT',
        });
    },
    
    async delete(id) {
        return apiRequest(`/projects/${id}`, {
            method: 'DELETE',
        });
    },
};

// ============================================
// CALENDAR API (Google Calendar)
// ============================================

const CalendarAPI = {
    async getToday() {
        return apiRequest('/calendar/today');
    },
    
    async getWeek() {
        return apiRequest('/calendar/week');
    },
    
    async getByDate(date) {
        return apiRequest(`/calendar/date/${date}`);
    },
    
    async getUpcoming(days = 7) {
        return apiRequest(`/calendar/upcoming?days=${days}`);
    },
};

// Export para uso global
window.TasksAPI = TasksAPI;
window.RemindersAPI = RemindersAPI;
window.NotesAPI = NotesAPI;
window.TodayAPI = TodayAPI;
window.EventsAPI = EventsAPI;
window.ProjectsAPI = ProjectsAPI;
window.CalendarAPI = CalendarAPI;
