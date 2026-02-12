/**
 * Centro de Controle - API Client
 * Comunicação com o backend FastAPI
 * Performance optimized with caching and parallel loading
 */

// Detectar se está rodando no GitHub Pages ou localmente
const isGitHubPages = window.location.hostname.includes('github.io');
const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';

// API Base: usa VPS quando no GitHub Pages, relativo quando local/VPS
const API_BASE = (isGitHubPages) 
    ? 'https://srv1315519.hstgr.cloud/api'  // VPS Backend HTTPS
    : '/api';  // Local ou servido pela própria VPS

// ============================================
// CACHE SYSTEM
// ============================================

const APICache = {
    data: new Map(),
    ttl: {
        '/today': 60000,           // 1 minuto
        '/tasks': 30000,           // 30 segundos
        '/projects': 60000,        // 1 minuto
        '/calendar/today': 120000, // 2 minutos
        '/reminders': 30000,       // 30 segundos
        '/notes': 60000,           // 1 minuto
        '/mba/stats': 300000,      // 5 minutos
        '/confluence/summary': 300000, // 5 minutos
        '/work-projects/report-cards': 300000, // 5 minutos
    },
    
    get(key) {
        const cached = this.data.get(key);
        if (!cached) return null;
        if (Date.now() > cached.expires) {
            this.data.delete(key);
            return null;
        }
        return cached.value;
    },
    
    set(key, value) {
        const ttl = this.ttl[key] || 30000;
        this.data.set(key, {
            value,
            expires: Date.now() + ttl
        });
    },
    
    invalidate(pattern) {
        for (const key of this.data.keys()) {
            if (key.includes(pattern)) {
                this.data.delete(key);
            }
        }
    },
    
    clear() {
        this.data.clear();
    }
};

/**
 * Helper para fazer requisições à API (com cache)
 */
async function apiRequest(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const isGET = !options.method || options.method === 'GET';
    
    // Check cache for GET requests
    if (isGET) {
        const cached = APICache.get(endpoint);
        if (cached) {
            console.log(`[Cache HIT] ${endpoint}`);
            return cached;
        }
    }
    
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
        
        const data = await response.json();
        
        // Cache GET responses
        if (isGET) {
            APICache.set(endpoint, data);
        } else {
            // Invalidate related cache on mutations
            if (endpoint.includes('/tasks')) APICache.invalidate('/tasks');
            if (endpoint.includes('/projects')) APICache.invalidate('/projects');
            if (endpoint.includes('/reminders')) APICache.invalidate('/reminders');
            if (endpoint.includes('/notes')) APICache.invalidate('/notes');
            APICache.invalidate('/today');
        }
        
        return data;
    } catch (error) {
        // Suppress expected 404s for endpoints with known fallbacks
        const SILENT_404_ENDPOINTS = ['/mba/data', '/mba/stats', '/work-projects/'];
        const isSilent = SILENT_404_ENDPOINTS.some(e => endpoint.startsWith(e)) 
            && error.message && error.message.includes('404');
        if (!isSilent) {
            console.error(`API Error [${endpoint}]:`, error);
        }
        throw error;
    }
}

/**
 * Load multiple endpoints in parallel
 */
async function loadParallel(endpoints) {
    const promises = endpoints.map(ep => 
        apiRequest(ep).catch(err => ({ error: err.message, endpoint: ep }))
    );
    return Promise.all(promises);
}

// Export cache control
window.APICache = APICache;
window.loadParallel = loadParallel;

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

// ============================================
// MBA / ADALOVE API
// ============================================

const MBAAPI = {
    /**
     * Obtem dados do Adalove
     */
    async getData() {
        return apiRequest('/mba/data');
    },
    
    /**
     * Solicita sincronizacao dos dados
     */
    async sync() {
        return apiRequest('/mba/sync', {
            method: 'POST',
        });
    },
    
    /**
     * Lista materiais disponiveis
     */
    async getMaterials() {
        return apiRequest('/mba/materials');
    },
    
    /**
     * Atualiza dados do Adalove
     * @param {object} data - Dados completos do Adalove
     */
    async updateData(data) {
        return apiRequest('/mba/data', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },
};

// ============================================
// OBSERVABILITY API
// ============================================

const ObservabilityAPI = {
    /**
     * Get tool metrics for last N days
     */
    async getToolMetrics(days = 7) {
        return apiRequest(`/metrics/tools?days=${days}`);
    },

    /**
     * Get routing evaluation metrics
     */
    async getRoutingMetrics(days = 7) {
        return apiRequest(`/metrics/routing?days=${days}`);
    },

    /**
     * Get quality score metrics
     */
    async getQualityMetrics(days = 30) {
        return apiRequest(`/metrics/quality?days=${days}`);
    },

    /**
     * Get recent daily reports
     */
    async getDailyReports(days = 7) {
        return apiRequest(`/reports/daily?days=${days}`);
    },

    /**
     * Get recent weekly reports
     */
    async getWeeklyReports(weeks = 4) {
        return apiRequest(`/reports/weekly?weeks=${weeks}`);
    },

    /**
     * Get cost metrics (balance, spend, by model, daily)
     * @param {number} days - Period in days (default 30)
     */
    async getCostMetrics(days = 30) {
        return apiRequest(`/metrics/costs?days=${days}`);
    },

    /**
     * Get live Moonshot balance
     */
    async getCostBalance() {
        return apiRequest(`/metrics/costs/balance`);
    },

    /**
     * Get Langfuse aggregated stats (cost, calls, cached tokens)
     * Data is cached on the backend for 5 minutes
     * @param {number} days - Period in days (default 30)
     */
    async getLangfuseStats(days = 30) {
        return apiRequest(`/metrics/langfuse-stats?days=${days}`);
    },
};

// ============================================
// WORK PROJECTS API (Report Cards)
// ============================================

const WorkProjectsAPI = {
    /**
     * Get report cards for all work projects (batch, cached 30min on backend)
     */
    async getReportCards() {
        return apiRequest('/work-projects/report-cards');
    },

    /**
     * Get report card for a single work project
     * @param {string} slug - Project slug (e.g. "3tpm", "cms-dam")
     */
    async getReportCard(slug) {
        return apiRequest(`/work-projects/${slug}/report-card`);
    },

    /**
     * Get work project details
     * @param {string} slug - Project slug
     */
    async getProject(slug) {
        return apiRequest(`/work-projects/${slug}`);
    },
};

// ============================================
// WEEKLY BRIEF API (CRUD on items)
// ============================================

const WeeklyBriefAPI = {
    /**
     * Add, complete, or remove an item from a weekly brief section
     * @param {string} section - "urgent", "important", "decisions"
     * @param {string} action - "add", "complete", "remove"
     * @param {number|null} index - Item index (for complete/remove)
     * @param {object|null} item - Item data (for add)
     */
    async patchItem(section, action, index = null, item = null) {
        return apiRequest('/weekly-brief/items', {
            method: 'PATCH',
            body: JSON.stringify({ section, action, index, item }),
        });
    },
};

// ============================================
// UI HELPERS - Error & Loading States
// ============================================

/**
 * Show a skeleton loading state inside a container
 * @param {string} containerId - DOM element ID
 * @param {number} count - Number of skeleton items
 */
function showLoadingState(containerId, count = 3) {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = Array.from({ length: count }, () => 
        `<div class="skeleton skeleton-card" style="margin-bottom: 12px;"></div>`
    ).join('');
}

/**
 * Show an error state inside a container with retry
 * @param {string} containerId - DOM element ID
 * @param {string} message - Error message
 * @param {Function} retryFn - Function to call on retry
 */
function showErrorState(containerId, message, retryFn) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const retryId = `retry-${containerId}-${Date.now()}`;
    el.innerHTML = `
        <div class="error-state">
            <div class="error-icon">⚠️</div>
            <div class="error-message">${message}</div>
            ${retryFn ? `<button class="error-retry" id="${retryId}">Tentar novamente</button>` : ''}
        </div>`;
    if (retryFn) {
        document.getElementById(retryId)?.addEventListener('click', retryFn);
    }
}

/**
 * Show an empty state inside a container
 * @param {string} containerId - DOM element ID
 * @param {string} icon - Emoji icon
 * @param {string} text - Message text
 */
function showEmptyState(containerId, icon = '📭', text = 'Nenhum item encontrado') {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = `
        <div class="empty-state">
            <div class="empty-icon">${icon}</div>
            <div class="empty-text">${text}</div>
        </div>`;
}

/**
 * Safely load data with error handling
 * @param {Function} fn - Async function to execute
 * @param {string} containerId - Container to show error in (optional)
 */
async function safeLoad(fn, containerId) {
    try {
        await fn();
    } catch (error) {
        console.error(`Load error${containerId ? ` [${containerId}]` : ''}:`, error);
        if (containerId) {
            showErrorState(containerId, error.message || 'Erro ao carregar dados', () => safeLoad(fn, containerId));
        }
    }
}

// Export para uso global
window.TasksAPI = TasksAPI;
window.RemindersAPI = RemindersAPI;
window.NotesAPI = NotesAPI;
window.TodayAPI = TodayAPI;
window.EventsAPI = EventsAPI;
window.ProjectsAPI = ProjectsAPI;
window.CalendarAPI = CalendarAPI;
window.MBAAPI = MBAAPI;
window.ObservabilityAPI = ObservabilityAPI;
window.WorkProjectsAPI = WorkProjectsAPI;
window.WeeklyBriefAPI = WeeklyBriefAPI;
window.showLoadingState = showLoadingState;
window.showErrorState = showErrorState;
window.showEmptyState = showEmptyState;
window.safeLoad = safeLoad;