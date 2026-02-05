# 🎛️ Centro de Controle - Documento de Planejamento

> **Projeto:** Dashboard pessoal para Fábio
> **Criado por:** Atlas
> **Data:** 2026-02-03
> **Status:** 📝 Em Planejamento

---

## 📋 Sumário

1. [Visão Geral](#visão-geral)
2. [Arquitetura](#arquitetura)
3. [Stack Tecnológica](#stack-tecnológica)
4. [Design & UX](#design--ux)
5. [Wireframes](#wireframes)
6. [Tarefas/Tickets](#tarefastickets)
7. [Plano de Deploy](#plano-de-deploy)
8. [Cronograma](#cronograma)

---

## 🎯 Visão Geral

### Objetivo
Dashboard centralizado para Fábio gerenciar tarefas, comunicação com IAs (Nova/Atlas), agenda e lembretes.

### Perfil do Usuário (CRÍTICO pro design)
```
┌─────────────────────────────────────────────────┐
│ 🧠 PERFIL COGNITIVO - FÁBIO                     │
├─────────────────────────────────────────────────┤
│ ✅ Raciocínio Visual: 99º percentil (GÊNIO!)    │
│ ✅ QI: 126 (Superior)                           │
│ ⚠️  TDAH Combinado (moderado)                   │
│ ⚠️  Atenção Dividida: 50º (cuidado!)            │
│ ⚠️  Gerenciamento Tempo: 20º (precisa suporte!) │
├─────────────────────────────────────────────────┤
│ 💡 PREFERÊNCIAS:                                │
│ • Visual > Texto                                │
│ • Checkpoints curtos                            │
│ • Ação > Planejamento infinito                  │
│ • Urgência ativa foco                           │
│ • Odeia: textos longos, rotina rígida           │
└─────────────────────────────────────────────────┘
```

### Funcionalidades Principais
| # | Módulo | Descrição | Prioridade |
|---|--------|-----------|------------|
| 1 | 💬 Chat | Comunicação com Nova/Atlas | P0 |
| 2 | 📋 Kanban | Board de tarefas grandes | P0 |
| 3 | 📅 Hoje | Resumo do dia, reuniões | P0 |
| 4 | 🔔 Lembretes | Alertas visuais inteligentes | P1 |
| 5 | 🗒️ Notas | Últimas discussões/reuniões | P1 |

---

## 🏗️ Arquitetura

### Diagrama de Alto Nível
```
┌─────────────────────────────────────────────────────────┐
│                    📱 FRONTEND                          │
│         (HTML/CSS/JS - PWA Responsivo)                  │
│  ┌─────────┬─────────┬─────────┬─────────┬─────────┐   │
│  │  Chat   │ Kanban  │  Hoje   │Lembretes│  Notas  │   │
│  └────┬────┴────┬────┴────┬────┴────┬────┴────┬────┘   │
│       │         │         │         │         │         │
│       └─────────┴─────────┴────┬────┴─────────┘         │
│                                │                         │
│                         REST API                         │
└────────────────────────────────┼─────────────────────────┘
                                 │
┌────────────────────────────────┼─────────────────────────┐
│                    🖥️ BACKEND                            │
│              (Python/FastAPI)                            │
│  ┌─────────────────────────────────────────────────┐    │
│  │              API Gateway                         │    │
│  │   /chat  /tasks  /today  /reminders  /notes     │    │
│  └──────────────────────┬──────────────────────────┘    │
│                         │                                │
│  ┌──────────────────────┼──────────────────────────┐    │
│  │              Services Layer                      │    │
│  │  ┌────────┐  ┌────────┐  ┌────────┐            │    │
│  │  │  Nova  │  │ Tasks  │  │Calendar│            │    │
│  │  │Webhook │  │Manager │  │  Sync  │            │    │
│  │  └────────┘  └────────┘  └────────┘            │    │
│  └──────────────────────┬──────────────────────────┘    │
│                         │                                │
│  ┌──────────────────────┼──────────────────────────┐    │
│  │              Data Layer                          │    │
│  │         SQLite + JSON Files                      │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
                                 │
                                 │ Webhook
                                 ▼
┌──────────────────────────────────────────────────────────┐
│                    🤖 VPS (Nova)                         │
│              OpenClaw + Telegram Bot                     │
└──────────────────────────────────────────────────────────┘
```

### Comunicação
```
Fábio (Celular/PC)
       │
       ▼
   Dashboard ──────► Backend ──────► Nova (VPS)
       │                │                │
       │                │                ▼
       │                │           Telegram
       │                │                │
       ◄────────────────┴────────────────┘
              (Respostas via Webhook)
```

---

## 🛠️ Stack Tecnológica

### Frontend
| Tecnologia | Justificativa |
|------------|---------------|
| **HTML5/CSS3** | Simples, rápido, sem build |
| **Vanilla JS** | Leve, sem framework overhead |
| **CSS Grid/Flexbox** | Layout responsivo |
| **CSS Variables** | Tema dark mode fácil |
| **LocalStorage** | Cache offline |
| **Service Worker** | PWA (funciona offline) |

### Backend
| Tecnologia | Justificativa |
|------------|---------------|
| **Python 3.11** | Já usado no projeto |
| **FastAPI** | Rápido, async, docs automáticos |
| **SQLite** | Leve, sem setup, suficiente |
| **Pydantic** | Validação de dados |

### Infraestrutura
| Componente | Escolha |
|------------|---------|
| **Servidor** | VPS Hostinger (já existente) |
| **Reverse Proxy** | Nginx |
| **SSL** | Let's Encrypt (Certbot) |
| **Processo** | Systemd service |
| **Domínio** | Subdomínio ou IP direto |

---

## 🎨 Design & UX

### Princípios (baseado no perfil TDAH)
```
┌─────────────────────────────────────────────────┐
│ 🎨 REGRAS DE DESIGN                             │
├─────────────────────────────────────────────────┤
│ 1. VISUAL PRIMEIRO                              │
│    • Ícones > Texto                             │
│    • Cores significativas                       │
│    • Progress bars visuais                      │
│                                                 │
│ 2. INFORMAÇÃO MÍNIMA                            │
│    • Máximo 7 itens visíveis por seção          │
│    • Texto máximo 10 palavras por card          │
│    • Resumos, não detalhes                      │
│                                                 │
│ 3. URGÊNCIA VISUAL                              │
│    • Vermelho = AGORA                           │
│    • Amarelo = HOJE                             │
│    • Verde = OK/Feito                           │
│    • Cinza = Pode esperar                       │
│                                                 │
│ 4. INTERAÇÃO RÁPIDA                             │
│    • 1 clique pra ação principal                │
│    • Swipe pra completar (mobile)               │
│    • Atalhos de teclado (desktop)               │
│                                                 │
│ 5. FOCO FORÇADO                                 │
│    • Uma coisa de cada vez                      │
│    • Modal bloqueia background                  │
│    • Timer visível em tarefas ativas            │
└─────────────────────────────────────────────────┘
```

### Paleta de Cores (Dark Mode)
```css
:root {
  /* Background */
  --bg-primary: #0d1117;      /* Fundo principal */
  --bg-secondary: #161b22;    /* Cards */
  --bg-tertiary: #21262d;     /* Hover */
  
  /* Text */
  --text-primary: #e6edf3;    /* Texto principal */
  --text-secondary: #7d8590;  /* Texto secundário */
  
  /* Accent */
  --accent-blue: #58a6ff;     /* Links, ações */
  --accent-green: #3fb950;    /* Sucesso, feito */
  --accent-yellow: #d29922;   /* Alerta, hoje */
  --accent-red: #f85149;      /* Urgente, erro */
  --accent-purple: #a371f7;   /* Nova (IA) */
  --accent-orange: #db6d28;   /* Atlas (IA) */
}
```

### Tipografia
```
Títulos: Inter Bold, 18-24px
Corpo: Inter Regular, 14-16px
Números: JetBrains Mono, 14px (monospace pra dados)
```

---

## 📐 Wireframes

### Layout Principal (Mobile-First)
```
┌─────────────────────────────┐
│  🎛️ Centro de Controle     │ ← Header fixo
├─────────────────────────────┤
│                             │
│  ┌───────────────────────┐  │
│  │ 📅 HOJE               │  │ ← Card colapsável
│  │ • 14:00 Reunião MBA   │  │
│  │ • 3 tarefas pendentes │  │
│  │ [Ver mais]            │  │
│  └───────────────────────┘  │
│                             │
│  ┌───────────────────────┐  │
│  │ 📋 TAREFAS            │  │ ← Kanban simplificado
│  │ ┌─────┬─────┬─────┐   │  │
│  │ │ 🔴2 │ 🟡3 │ 🟢5 │   │  │ ← Contadores
│  │ │ To  │Doing│Done │   │  │
│  │ └─────┴─────┴─────┘   │  │
│  │ [Abrir board]         │  │
│  └───────────────────────┘  │
│                             │
│  ┌───────────────────────┐  │
│  │ 🔔 LEMBRETES          │  │
│  │ ⚠️ Entregar case 23h  │  │
│  │ [+2 mais]             │  │
│  └───────────────────────┘  │
│                             │
├─────────────────────────────┤
│ [💬 Chat] [📋] [📅] [⚙️]  │ ← Nav inferior
└─────────────────────────────┘
```

### Tela do Chat
```
┌─────────────────────────────┐
│ ← 💬 Chat                   │
├─────────────────────────────┤
│                             │
│  ┌───────────────────────┐  │
│  │ 🟣 Nova               │  │
│  │ Oi Fábio! Lembrete:   │  │
│  │ reunião em 30min      │  │
│  │              14:32 ✓✓ │  │
│  └───────────────────────┘  │
│                             │
│        ┌─────────────────┐  │
│        │ 🟠 Atlas        │  │
│        │ Deploy feito!   │  │
│        │ Site no ar.     │  │
│        │         14:35 ✓ │  │
│        └─────────────────┘  │
│                             │
│  ┌───────────────────────┐  │
│  │ 👤 Fábio              │  │
│  │ Valeu! Vou testar     │  │
│  │              14:36 ✓✓ │  │
│  └───────────────────────┘  │
│                             │
├─────────────────────────────┤
│ [📎] Digite mensagem... [➤]│
└─────────────────────────────┘
```

### Tela Kanban
```
┌─────────────────────────────┐
│ ← 📋 Board de Tarefas       │
├─────────────────────────────┤
│ [+ Nova Tarefa]             │
├─────────┬─────────┬─────────┤
│ 🔴 TODO │ 🟡 DOING│ 🟢 DONE │
├─────────┼─────────┼─────────┤
│┌───────┐│┌───────┐│┌───────┐│
││Centro ││││Plano  │││Secrets││
││Controle│││MBA    │││ ✓     ││
││[P0]   │││[P1]   │││       ││
│└───────┘│└───────┘│└───────┘│
│┌───────┐│         │┌───────┐│
││RAG    ││         ││Escala-││
││Notion ││         ││ção ✓  ││
││[P2]   ││         ││       ││
│└───────┘│         │└───────┘│
└─────────┴─────────┴─────────┘
```

---

## 📝 Tarefas/Tickets

### Fase 1: Setup (P0)
| # | Tarefa | Estimativa | Dependência |
|---|--------|------------|-------------|
| 1.1 | Criar estrutura de diretórios | 5min | - |
| 1.2 | Inicializar Git repo | 5min | 1.1 |
| 1.3 | Setup FastAPI básico | 15min | 1.2 |
| 1.4 | Criar schema do banco SQLite | 20min | 1.3 |
| 1.5 | Setup Nginx + SSL | 30min | 1.3 |

### Fase 2: Backend (P0)
| # | Tarefa | Estimativa | Dependência |
|---|--------|------------|-------------|
| 2.1 | API /tasks (CRUD) | 30min | 1.4 |
| 2.2 | API /chat (send/receive) | 30min | 1.4 |
| 2.3 | API /today (resumo dia) | 20min | 1.4 |
| 2.4 | API /reminders (CRUD) | 20min | 1.4 |
| 2.5 | Webhook Nova → Dashboard | 30min | 2.2 |

### Fase 3: Frontend (P0)
| # | Tarefa | Estimativa | Dependência |
|---|--------|------------|-------------|
| 3.1 | HTML base + CSS Variables | 30min | - |
| 3.2 | Componente: Header + Nav | 20min | 3.1 |
| 3.3 | Componente: Card Hoje | 30min | 3.1 |
| 3.4 | Componente: Kanban Board | 45min | 3.1 |
| 3.5 | Componente: Chat | 45min | 3.1 |
| 3.6 | Componente: Lembretes | 30min | 3.1 |
| 3.7 | Responsividade mobile | 30min | 3.2-3.6 |

### Fase 4: Integração (P0)
| # | Tarefa | Estimativa | Dependência |
|---|--------|------------|-------------|
| 4.1 | Conectar Frontend ↔ Backend | 30min | 2.*, 3.* |
| 4.2 | Integrar Nova webhook | 30min | 4.1 |
| 4.3 | Testes end-to-end | 30min | 4.2 |

### Fase 5: Deploy (P0)
| # | Tarefa | Estimativa | Dependência |
|---|--------|------------|-------------|
| 5.1 | Deploy backend no VPS | 20min | 4.3 |
| 5.2 | Deploy frontend (static) | 10min | 4.3 |
| 5.3 | Configurar domínio/SSL | 20min | 5.1, 5.2 |
| 5.4 | Teste em produção | 15min | 5.3 |

### Fase 6: Polish (P1)
| # | Tarefa | Estimativa | Dependência |
|---|--------|------------|-------------|
| 6.1 | PWA (Service Worker) | 30min | 5.4 |
| 6.2 | Notificações push | 30min | 6.1 |
| 6.3 | Sync calendário Google | 45min | 5.4 |
| 6.4 | Temas (dark/light toggle) | 20min | 5.4 |

---

## 🚀 Plano de Deploy

### Estrutura no VPS
```
/root/Nova/
├── openclaw-workspace/
│   └── projects/
│       └── centro-de-controle/
│           ├── backend/
│           │   ├── main.py
│           │   ├── models.py
│           │   ├── routes/
│           │   └── database.db
│           ├── frontend/
│           │   ├── index.html
│           │   ├── css/
│           │   ├── js/
│           │   └── assets/
│           ├── PLANEJAMENTO.md
│           └── README.md
```

### Configuração Nginx
```nginx
server {
    listen 443 ssl;
    server_name controle.fabio.dev;  # ou IP direto
    
    ssl_certificate /etc/letsencrypt/live/.../fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/.../privkey.pem;
    
    # Frontend (static)
    location / {
        root /root/Nova/.../frontend;
        try_files $uri $uri/ /index.html;
    }
    
    # Backend API
    location /api {
        proxy_pass http://127.0.0.1:8100;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }
}
```

### Systemd Service
```ini
[Unit]
Description=Centro de Controle API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/Nova/.../backend
ExecStart=/usr/bin/python3 -m uvicorn main:app --host 127.0.0.1 --port 8100
Restart=always

[Install]
WantedBy=multi-user.target
```

### Checklist de Deploy
- [ ] Backend rodando local
- [ ] Frontend conectando ao backend
- [ ] Upload arquivos pro VPS
- [ ] Configurar Nginx
- [ ] Gerar certificado SSL
- [ ] Criar systemd service
- [ ] Testar acesso externo
- [ ] Testar no celular

---

## ⏰ Cronograma Estimado

```
┌────────────────────────────────────────────────┐
│ FASE           │ TEMPO    │ STATUS             │
├────────────────┼──────────┼────────────────────┤
│ 1. Setup       │ ~1h      │ ⬜ Pendente        │
│ 2. Backend     │ ~2h      │ ⬜ Pendente        │
│ 3. Frontend    │ ~3h      │ ⬜ Pendente        │
│ 4. Integração  │ ~1.5h    │ ⬜ Pendente        │
│ 5. Deploy      │ ~1h      │ ⬜ Pendente        │
│ 6. Polish      │ ~2h      │ ⬜ Futuro          │
├────────────────┼──────────┼────────────────────┤
│ TOTAL MVP      │ ~8-9h    │                    │
└────────────────┴──────────┴────────────────────┘
```

---

## ✅ Próximos Passos

1. **Fábio revisa** este documento
2. **Ajustes** se necessário
3. **Atlas começa** implementação
4. **Commits** organizados por fase
5. **Deploy** quando MVP pronto

---

*Documento criado por: Atlas*
*Data: 2026-02-03*
*Versão: 1.0*
