# 🎛️ Centro de Controle

> Dashboard pessoal do Fábio - Otimizado para TDAH

## 📁 Estrutura do Projeto

```
centro-de-controle/
├── frontend/          # Interface web (GitHub Pages)
│   ├── index.html     # Dashboard principal
│   ├── work.html      # Situation Wall (trabalho)
│   ├── mba.html       # Tracker MBA
│   ├── portfolio.html # Visão projetos
│   └── project.html   # Detalhes projeto
│
├── backend/           # API FastAPI
│   ├── main.py        # Servidor principal
│   ├── confluence_client.py
│   ├── jira_client.py
│   ├── situation_wall_parser.py
│   └── sync_confluence.py
│
├── PLANEJAMENTO.md    # Documento de planejamento
└── ROADMAP.md         # Roadmap de features
```

## 🚀 Como Usar

### Frontend (GitHub Pages)

O frontend está publicado em: **https://fabiosolivei.github.io/centro-de-controle/**

Para desenvolvimento local:
```bash
cd frontend
python -m http.server 8080
# Abra http://localhost:8080
```

### Backend (API)

```bash
cd backend

# Criar ambiente virtual
python -m venv .venv
source .venv/bin/activate

# Instalar dependências
pip install -r requirements.txt

# Configurar credenciais (criar arquivo .env)
cat > .env << EOF
CONFLUENCE_EMAIL=seu.email@empresa.com
CONFLUENCE_API_TOKEN=seu_token_aqui
CONFLUENCE_BASE_URL=https://empresa.atlassian.net
ATLASSIAN_EMAIL=seu.email@empresa.com
ATLASSIAN_API_TOKEN=seu_token_aqui
ATLASSIAN_BASE_URL=https://empresa.atlassian.net
EOF

# Rodar servidor
python -m uvicorn main:app --host 0.0.0.0 --port 8100 --reload
```

### Sync Confluence (Situation Wall)

```bash
cd backend
python sync_confluence.py
```

## 🔗 Integrações

| Serviço | Descrição |
|---------|-----------|
| **Confluence** | Situation Wall - Sprints, Initiatives, Risks |
| **Jira** | Detalhes de Issues (BEESIP, BEESCAD) |
| **Google Calendar** | Eventos do dia |
| **Notion** | Meeting Notes (via RAG) |

## 📊 Endpoints da API

| Endpoint | Descrição |
|----------|-----------|
| `GET /api/confluence/summary` | Resumo do Situation Wall |
| `GET /api/confluence/initiatives` | Lista initiatives |
| `GET /api/work-projects/{slug}` | Detalhes projeto trabalho |
| `GET /api/updates/recent` | Updates recentes |
| `POST /api/confluence/sync` | Trigger sync manual |

## 🎨 Features do Dashboard

- **GPM Dashboard** - Visão executiva para Group Product Manager
- **Keyboard Shortcuts** - Navegação rápida (Cmd+K, j/k)
- **Work Status** - Integração Confluence Situation Wall
- **MBA Tracker** - Acompanhamento acadêmico
- **Portfolio View** - Todos os projetos em uma tela

## 🔐 Segurança

- Autenticação por senha hash (SHA-256)
- API Tokens em `.env` (nunca commitar!)
- HTTPS em produção

---

*Criado por Atlas para Fábio*
