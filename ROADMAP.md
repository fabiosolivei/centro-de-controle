# 🗺️ Centro de Controle - Roadmap

> **Objetivo:** Dashboard pessoal do Fábio controlado pela Nova
> **Princípio:** Nova é a controladora principal - ela gerencia tarefas, lembretes, projetos

---

## ✅ Fase 1: Base (CONCLUÍDO)

- [x] Backend FastAPI com SQLite
- [x] Frontend responsivo (design V2)
- [x] Kanban de tarefas
- [x] Lembretes
- [x] Notas de reunião
- [x] Integração Google Calendar (iCal)
- [x] Deploy na VPS (porta 8100)

---

## 🚧 Fase 2: Integração Nova (PRÓXIMO)

### 2.1 API para Nova
A Nova precisa conseguir:

| Ação | Endpoint | Método | Exemplo de uso |
|------|----------|--------|----------------|
| Criar tarefa | `/api/tasks` | POST | "Fábio, criei uma tarefa pra você revisar o DAM" |
| Atualizar tarefa | `/api/tasks/{id}` | PUT | Mover tarefa para "Fazendo" |
| Listar tarefas | `/api/tasks` | GET | "Você tem 3 tarefas pendentes" |
| Criar lembrete | `/api/reminders` | POST | "Vou te lembrar às 15h" |
| Criar nota | `/api/notes` | POST | Salvar resumo de reunião |
| Ver resumo do dia | `/api/today` | GET | "Hoje você tem 5 reuniões" |

### 2.2 Skill da Nova para o Dashboard
Criar skill em `/openclaw-workspace/skills/centro-de-controle/`

```
skills/centro-de-controle/
├── SKILL.md          # Instruções para Nova
├── scripts/
│   └── dashboard.py  # Funções helper
└── templates/
    └── resumo-diario.md
```

### 2.3 Webhook Nova → Dashboard
- Nova pode enviar atualizações em tempo real
- Endpoint: `/api/nova/webhook`
- Autenticação via token

---

## 📊 Fase 3: Seção de Projetos

### 3.1 Modelo de Dados
```python
class Project:
    id: int
    name: str           # "DAM", "MBA", "Catalog"
    status: str         # "active", "paused", "completed"
    priority: str       # "high", "normal", "low"
    description: str
    progress: int       # 0-100%
    due_date: str
    tags: str           # "trabalho,produto,documentação"
    nova_notes: str     # Notas que a Nova adiciona
    created_at: str
    updated_at: str
```

### 3.2 Funcionalidades
- [ ] CRUD de projetos
- [ ] Progress bar visual
- [ ] Tags coloridas por categoria
- [ ] Nova pode atualizar progresso
- [ ] Link para documentos relacionados

### 3.3 Projetos Iniciais
| Projeto | Categoria | Status |
|---------|-----------|--------|
| DAM - Documentação | Trabalho | Pendente |
| MBA Inteli | Estudo | Ativo |
| Centro de Controle | Pessoal | Em progresso |
| Catalog/Content | Trabalho | Ativo |

---

## 📁 Fase 4: Upload de Arquivos

### 4.1 Estrutura
```
/api/files/
├── upload          # POST - Upload de arquivo
├── list            # GET - Listar arquivos
├── download/{id}   # GET - Baixar arquivo
└── delete/{id}     # DELETE - Remover arquivo
```

### 4.2 Storage
- **Opção A:** Armazenar na VPS (`/root/Nova/uploads/`)
- **Opção B:** Integrar com OneDrive API
- **Opção C:** Usar S3-compatible (MinIO local)

### 4.3 Integração Nova
- Nova pode receber arquivos via Telegram
- Salvar automaticamente no dashboard
- Indexar no RAG para busca

### 4.4 Limites
- Tamanho máximo: 50MB por arquivo
- Tipos permitidos: PDF, DOC, TXT, MD, imagens
- Cota total: 1GB

---

## 🔒 Fase 5: Segurança (HTTPS)

### 5.1 Opções
| Opção | Prós | Contras |
|-------|------|---------|
| Nginx + Let's Encrypt | Gratuito, padrão | Precisa domínio |
| Cloudflare Tunnel | Sem expor porta | Depende de Cloudflare |
| Tailscale | Rede privada | Só acesso autenticado |

### 5.2 Plano Recomendado
1. Registrar subdomínio: `controle.fabio.dev` ou similar
2. Instalar Nginx na VPS
3. Configurar Let's Encrypt (certbot)
4. Proxy reverso para porta 8100
5. Fechar porta 8100 no firewall

### 5.3 Autenticação
- [ ] Login simples (usuário/senha)
- [ ] Ou: Token de API para acesso
- [ ] Nova tem token permanente

---

## 🤖 Fase 6: Automações da Nova

### 6.1 Rotinas Diárias
```
07:00 - Nova envia resumo do dia via Telegram
        - Eventos do calendário
        - Tarefas pendentes
        - Lembretes do dia

19:00 - Nova pergunta sobre o dia
        - O que foi feito?
        - Mover tarefas concluídas
        - Criar tarefas para amanhã
```

### 6.2 Triggers Automáticos
- Quando Fábio menciona tarefa no Telegram → Nova cria no dashboard
- Quando reunião termina → Nova pergunta se quer criar nota
- Quando deadline se aproxima → Nova envia lembrete

### 6.3 Comandos da Nova
```
"Nova, adiciona tarefa: Revisar documentação DAM"
"Nova, o que tenho pra hoje?"
"Nova, marca a tarefa X como feita"
"Nova, qual o status do projeto MBA?"
```

---

## 📅 Ordem de Execução

| Fase | Prioridade | Esforço | Dependência |
|------|------------|---------|-------------|
| 2. Integração Nova | 🔴 Alta | Médio | - |
| 3. Projetos | 🟡 Média | Médio | - |
| 5. HTTPS | 🟡 Média | Baixo | Domínio |
| 4. Upload | 🟢 Baixa | Alto | HTTPS |
| 6. Automações | 🟢 Baixa | Alto | Fase 2 |

---

## 🎯 Próximo Passo Imediato

**Criar skill da Nova para o Centro de Controle:**

1. Criar `/skills/centro-de-controle/SKILL.md`
2. Documentar todos os endpoints disponíveis
3. Criar script helper `dashboard.py`
4. Testar Nova criando uma tarefa

---

*Documento criado por Atlas em 2026-02-04*
*Última atualização: 2026-02-04*
