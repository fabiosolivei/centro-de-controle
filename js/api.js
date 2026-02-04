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
    /**
     * Lista todas as tarefas
     * @param {string} status - Filtrar por status (todo, doing, done)
     */
    async getAll(status = null) {
        const query = status ? `?status=${status}` : '';
        return apiRequest(`/tasks${query}`);
    },
    
    /**
     * Cria uma nova tarefa
     * @param {object} task - Dados da tarefa
     */
    async create(task) {
        return apiRequest('/tasks', {
            method: 'POST',
            body: JSON.stringify(task),
        });
    },
    
    /**
     * Atualiza uma tarefa
     * @param {number} id - ID da tarefa
     * @param {object} updates - Campos a atualizar
     */
    async update(id, updates) {
        return apiRequest(`/tasks/${id}`, {
            method: 'PUT',
            body: JSON.stringify(updates),
        });
    },
    
    /**
     * Deleta uma tarefa
     * @param {number} id - ID da tarefa
     */
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
    /**
     * Lista lembretes
     * @param {boolean} includeCompleted - Incluir completos
     */
    async getAll(includeCompleted = false) {
        const query = includeCompleted ? '?include_completed=true' : '';
        return apiRequest(`/reminders${query}`);
    },
    
    /**
     * Cria um novo lembrete
     * @param {object} reminder - Dados do lembrete
     */
    async create(reminder) {
        return apiRequest('/reminders', {
            method: 'POST',
            body: JSON.stringify(reminder),
        });
    },
    
    /**
     * Marca lembrete como completo
     * @param {number} id - ID do lembrete
     */
    async complete(id) {
        return apiRequest(`/reminders/${id}/complete`, {
            method: 'PUT',
        });
    },
    
    /**
     * Deleta um lembrete
     * @param {number} id - ID do lembrete
     */
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
    /**
     * Lista notas recentes
     * @param {number} limit - Limite de resultados
     */
    async getAll(limit = 10) {
        return apiRequest(`/notes?limit=${limit}`);
    },
    
    /**
     * Cria uma nova nota
     * @param {object} note - Dados da nota
     */
    async create(note) {
        return apiRequest('/notes', {
            method: 'POST',
            body: JSON.stringify(note),
        });
    },
    
    /**
     * Atualiza uma nota
     * @param {number} id - ID da nota
     * @param {object} note - Dados atualizados
     */
    async update(id, note) {
        return apiRequest(`/notes/${id}`, {
            method: 'PUT',
            body: JSON.stringify(note),
        });
    },
    
    /**
     * Deleta uma nota
     * @param {number} id - ID da nota
     */
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
    /**
     * Obtém resumo do dia
     */
    async getSummary() {
        return apiRequest('/today');
    },
};

// ============================================
// EVENTS API
// ============================================

const EventsAPI = {
    /**
     * Lista eventos
     * @param {string} date - Filtrar por data (YYYY-MM-DD)
     */
    async getAll(date = null) {
        const query = date ? `?date=${date}` : '';
        return apiRequest(`/events${query}`);
    },
    
    /**
     * Cria um novo evento
     * @param {object} event - Dados do evento
     */
    async create(event) {
        return apiRequest('/events', {
            method: 'POST',
            body: JSON.stringify(event),
        });
    },
    
    /**
     * Deleta um evento
     * @param {number} id - ID do evento
     */
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
    /**
     * Lista projetos
     * @param {string} status - Filtrar por status
     * @param {string} category - Filtrar por categoria
     */
    async getAll(status = null, category = null) {
        let query = [];
        if (status) query.push(`status=${status}`);
        if (category) query.push(`category=${category}`);
        const queryStr = query.length > 0 ? '?' + query.join('&') : '';
        return apiRequest(`/projects${queryStr}`);
    },
    
    /**
     * Cria um novo projeto
     * @param {object} project - Dados do projeto
     */
    async create(project) {
        return apiRequest('/projects', {
            method: 'POST',
            body: JSON.stringify(project),
        });
    },
    
    /**
     * Atualiza um projeto
     * @param {number} id - ID do projeto
     * @param {object} updates - Campos a atualizar
     */
    async update(id, updates) {
        return apiRequest(`/projects/${id}`, {
            method: 'PUT',
            body: JSON.stringify(updates),
        });
    },
    
    /**
     * Atualiza progresso do projeto
     * @param {number} id - ID do projeto
     * @param {number} progress - Progresso (0-100)
     */
    async updateProgress(id, progress) {
        return apiRequest(`/projects/${id}/progress?progress=${progress}`, {
            method: 'PUT',
        });
    },
    
    /**
     * Deleta um projeto
     * @param {number} id - ID do projeto
     */
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
    /**
     * Obtém eventos de hoje do Google Calendar
     */
    async getToday() {
        return apiRequest('/calendar/today');
    },
    
    /**
     * Obtém eventos da semana agrupados por dia
     */
    async getWeek() {
        return apiRequest('/calendar/week');
    },
    
    /**
     * Obtém eventos de uma data específica
     * @param {string} date - Data no formato YYYY-MM-DD
     */
    async getByDate(date) {
        return apiRequest(`/calendar/date/${date}`);
    },
    
    /**
     * Obtém próximos eventos
     * @param {number} days - Número de dias à frente (máx 30)
     */
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
