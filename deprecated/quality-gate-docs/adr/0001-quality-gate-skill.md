# ADR 0001 — Quality Gate skill: conceito e decisões de arquitetura

- **Status:** Accepted — **parcialmente superseded por ADR 0002** (§3.1, §3.6, §3.7, §3.10 exit codes, §3.13 inviolable rules)
- **Data:** 2026-05-12
- **Decisores:** Paulo Corcino
- **Contexto da decisão:** sessão `/grill-me` consolidada nesta branch
- **Plano de implementação:** [`docs/plans/quality-gate-skill.md`](../plans/quality-gate-skill.md)
- **Evolução:** ver [ADR 0002](0002-quality-gate-branch-intent.md) para o redesign de governança baseado em intent declarado por branch (v2)

---

## 1. Contexto

Modelos de IA hoje produzem grandes volumes de código em múltiplos arquivos por iteração. Revisar tudo manualmente é lento e o programador vira gargalo. Sem um portão automatizado, a qualidade do projeto degrada silenciosamente: arquivos crescem sem refatoração, cobertura cai, duplicação aumenta, vulnerabilidades entram via dependências.

Soluções de mercado (SonarQube, GitHub Code Quality) existem mas exigem infra dedicada, configuração pesada, ou vínculo a um SaaS específico. Para o uso pré-PR local — onde o agente de IA (ou desenvolvedor) precisa validar o próprio trabalho antes de abrir um Pull Request — precisamos de uma alternativa **leve, open-source, agnóstica de linguagem, determinística e diagnóstica**.

## 2. Conceito do Quality Gate (QG)

### 2.1 Princípio da catraca (ratchet)

A qualidade do código só pode andar em uma direção: **melhorar ou empatar, nunca piorar**. Um baseline congela o estado atual e o QG bloqueia qualquer regressão sobre ele. Isso permite adotar o gate mesmo em código legado com débito técnico — não exigimos perfeição imediata, apenas que nada piore.

### 2.2 Regra de ouro

A IA (ou humano) tem total liberdade para adicionar lógica nova, mas não pode aumentar nenhuma métrica negativa nem reduzir nenhuma métrica positiva acima das tolerâncias mínimas declaradas.

### 2.3 Skill diagnóstica, não corretiva

O QG **mede** e **relata**; não corrige, não entra em loop de babá, não atualiza baseline automaticamente. A correção é decisão do operador (humano ou agente). Determinismo é garantido para que execuções repetidas sem alteração de código produzam o mesmo relatório.

### 2.4 Pré-PR local

O QG roda localmente antes da abertura do PR. Não é uma etapa de CI nesta versão; é precursor do próprio code review.

---

## 3. Decisões

### 3.1 Armazenamento do baseline

**Decisão:** Baseline vive em `.quality-gate/baseline.json` **dentro do repo alvo**, versionado no git.

**Razão:** baseline é propriedade do projeto, não da máquina do desenvolvedor. Governança ratchet ("main atualiza, feature branch só lê") só funciona com baseline versionado. Compartilhamento natural entre clones/máquinas/agentes.

### 3.2 Formato

**Decisão:** JSON para baseline (fonte da verdade); Markdown para relatório (artefato derivado, gitignored).

**Razão:** JSON é estruturado, parseável por script, diff legível em PR. CSV não suporta aninhamento (coverage com sub-métricas, lista de arquivos com métricas individuais). Markdown como dado é frágil para parsing. Separação dado vs apresentação evita acoplamento.

**Estrutura do baseline:**
```json
{
  "schema_version": 1,
  "generated_at": "...",
  "commit": "...",
  "main_branch": "main",
  "tools_versions": {"ruff": "0.x", "...": "..."},
  "projects": {
    "_root" | "<dir>": {
      "language": "python",
      "root": "./",
      "tools_used": ["ruff", "pytest-cov", "..."],
      "coverage": {"lines": ..., "statements": ..., "functions": ..., "branches": ...},
      "duplication": {"percentage": ..., "fragments": ...},
      "violations": {"errors": ..., "warnings": ...},
      "vulnerabilities": {"critical": ..., "high": ..., "medium": ..., "low": ...},
      "files": {"path/to/file": {"lines": ..., "bytes": ..., "max_depth": ...}}
    }
  }
}
```

### 3.3 Granularidade do baseline de arquivos

**Decisão:** apenas arquivos que cruzam um `soft_limit` (por linguagem) entram no baseline. `hard_limit` causa falha imediata para arquivo novo.

**Razão:** baseline com todos os arquivos do repo é gigante e ruidoso. Limitar ao "que importa" mantém o arquivo enxuto. Limites configuráveis por linguagem reconhecem que Go aceita arquivos maiores que Python.

Limites iniciais: Python 300/800, Go 500/1000, Rust 400/900, BunJS 300/800.

### 3.4 Layout da skill — pastas por linguagem

**Decisão:** uma pasta por linguagem em `languages/<lang>/` contendo `run.py`, `tools.json`, `metadata.json`. Lógica comum em `lib/`. Schemas em `schema/`.

**Razão:** adicionar nova linguagem = preencher um template. O core não muda. Cada `run.py` é independente, normaliza para o schema canônico.

**Tudo em Python**, inclusive para Go/Rust/BunJS — sem shell scripts. Parsing de output, tratamento de erro e geração de JSON ficam no mesmo lugar; sem quoting bash; sem incompatibilidade entre macOS/Linux/WSL.

### 3.5 Multi-linguagem em monorepo

**Decisão:** baseline único namespaced por projeto. Autodetecção via manifests; `.quality-gate/config.json` opcional sobrescreve a detecção.

**Razão:** monorepo backend+frontend é comum. Métricas precisam ser comparáveis por projeto. Um arquivo único = um commit, um diff, fácil de versionar.

### 3.6 Governança rodando local

**Decisão:**
- **Leitura:** sempre `git show <main-branch>:.quality-gate/baseline.json`.
- **Escrita:** bloqueada por padrão. Só com `--update-baseline` E branch == main (ou `--force` como escape hatch documentado).

**Razão:** sem essa restrição, dev/agente honesto poderia "relaxar" o baseline numa feature branch por acidente e o ratchet vira teatro. Garantia equivalente a CI sem precisar de CI.

### 3.7 Bootstrap

**Decisão:** subcomando explícito `quality-gate init`. Recusa rodar `run` sem baseline. `init` só na branch principal.

**Razão:** evita o problema clássico do "ratchet introduzido em legado bloqueia tudo": o init congela o débito atual como teto. Modo explícito impede que o agente confunda bootstrap com "passou no gate".

### 3.8 Ferramenta ausente

**Decisão:** três regras combinadas:
1. Ferramenta ausente no bootstrap: `SKIPPED`, métrica não entra no baseline.
2. Ferramenta presente no baseline mas ausente agora: **FAIL** (anti-cheat — fecha o furo de "desinstalar pra passar").
3. Ferramenta nova disponível agora: roda, vira informativa, só vira ratchet no próximo update de baseline.

Cada `languages/<lang>/tools.json` declara `detect_command`, `install_command` (preferindo gerenciador OSS padrão), `purpose`, `docs_url`. Quando ferramenta falta, o relatório inclui o comando de instalação — o agente pode executar direto ou pedir confirmação.

Estados de saída: `PASSED`, `FAILED`, `PASSED_WITH_GAPS` (ferramentas faltam mas não estavam no baseline).

### 3.9 Definição de "regressão" — tabela de regras

| Métrica | Tipo | Regra de falha |
|---|---|---|
| Coverage (lines/stmt/func/branch) | % | `current < baseline - 0.05` |
| Duplication percentage | % | `current > baseline + 0.05` |
| Duplication fragments | int | `current > baseline` |
| Lint errors | int | `current > 0` (zero tolerância sempre) |
| Lint warnings | int | `current > baseline` |
| File length/size (por arquivo no baseline) | int | `current > baseline` |
| Max depth (por arquivo) | int | `current > baseline` |
| Oversized files count | int | `current > baseline` |
| Vulnerabilities critical | int | `current > 0` (zero tolerância sempre) |
| Vulnerabilities high/medium/low | int | `current > baseline` |
| Tool availability | bool | tool no baseline ausente agora = FAIL |

Tolerância de 0.05% existe **apenas para absorver ruído de medição**, não como espaço para degradação. Como o baseline só atualiza na main após melhoria, não há drift acumulado.

### 3.10 Interface CLI

**Decisão:** entrypoint primário `python -m quality_gate <subcomando>`. Subcomandos: `init`, `run`, `status`, `update-baseline`, `to-backlog`. Flags: `--language`, `--only`, `--update-baseline`, `--force`, `--main-branch`. Scripts internos em `lib/` também executáveis para debug (`python -m quality_gate.lib.ratchet`).

**Exit codes:**

| Exit | Significado |
|---|---|
| 0 | PASSED |
| 1 | FAILED (regressão detectada) |
| 2 | PASSED_WITH_GAPS (ferramentas faltam, não estavam no baseline) |
| 3 | NO_BASELINE |
| 4 | TOOL_MISSING_REGRESSION |
| 10 | CONFIG_ERROR |
| 20 | INTERNAL_ERROR |

### 3.11 Comportamento em FAIL — diagnóstico, não corretivo

**Decisão:** o QG **não** entra em loop de babysitting. Em FAIL: produz `report.md` com tabela de regressões e encerra. Sem auto-fix, sem auto-retry, sem auto-backlog.

**Escalação opt-in:** subcomando separado `quality-gate to-backlog` lê o último relatório e gera issues em `/docs/backlogs/` no formato da skill `to-issues` (tracer-bullet vertical slices). Só roda quando explicitamente invocado.

**Razão:** consistência. Mesma entrada → mesma saída. 10 execuções sem alteração de código produzem o mesmo relatório (módulo o bloco Metadata). Separa medição de intervenção: o QG mede, o operador decide.

### 3.12 Determinismo

Medidas obrigatórias:
1. Bloco Metadata isolado no topo do `report.md` (timestamps, versões); resto é dado comparável.
2. Todas as listas (arquivos, ferramentas, projetos) ordenadas alfabeticamente.
3. Percentuais com 2 casas decimais.
4. `tools_versions` registradas no baseline; divergência local emite `TOOL_VERSION_DRIFT`.
5. Seeds fixos onde aplicável: `pytest -p no:randomly`, jest com ordem estável.
6. `report_hash` no final do relatório, calculado sobre os dados (excluindo Metadata). Permite teste objetivo de idempotência.

### 3.13 SKILL.md — diagnóstico, não babá

O `SKILL.md` instrui o agente: "rode, leia o relatório, decida". Inviolable rules:
- NUNCA edite `baseline.json` manualmente.
- NUNCA atualize baseline em feature branch.
- NUNCA desinstale ferramenta para "passar" o gate.
- NUNCA relaxe tolerâncias no código da skill para um caso pontual.

Casos especiais ficam em `references/`: `bootstrap.md`, `missing-tools.md`, `monorepo.md`, `adding-language.md`.

### 3.14 Adicionar nova linguagem — contrato formal

**Decisão:** contrato formal via `schema/language_metrics.schema.json` + template em `languages/_template/`. Cada linguagem expõe:
- `tools.json` (manifesto)
- `run.py` (aceita `--root`, `--output`, produz JSON conforme schema)
- `metadata.json` (linguagem, manifests detectáveis, extensões, soft/hard limits)
- `sample-output.json` (fixture validada)

`lib/validate_language.py` valida o output contra o schema. Adicionar Java/Ruby/etc. = preencher o template, não mexer no core.

### 3.15 Persistência

Em `.quality-gate/`:
```
baseline.json       # COMMITADO — fonte da verdade
config.json         # COMMITADO se existir — opcional
.gitignore          # COMMITADO — ignora os efêmeros abaixo
report.md           # efêmero
current.json        # efêmero
tmp/                # efêmero (outputs crus das ferramentas)
```

Sem histórico de relatórios — git já tem histórico do baseline. Comparação histórica = `git checkout` num commit antigo e re-rodar.

### 3.16 Segurança — escopo v1

**Decisão:** incluir auditoria de dependências e SAST básico com duas ferramentas OSS estabelecidas:

- **[OSV-Scanner](https://github.com/google/osv-scanner)** (Google, v2.x): vulnerabilidades em dependências cross-language (Python/Go/Rust/Node e mais). Single binary, JSON output, sem servidor, sem SaaS.
- **[Semgrep CE](https://semgrep.dev/products/community-edition/)** (LGPL-2.1): patterns SAST multi-linguagem. Single binary, 3000+ regras comunitárias.

Regra ratchet de vulnerabilidades:

| Severidade | Regra |
|---|---|
| Critical | Zero tolerância sempre (desvio da regra ratchet pura) |
| High | Não pode aumentar; presença no baseline ≠ permissão para mais |
| Medium / Low | Conta no baseline, não pode aumentar |

Justificativa para o desvio em criticals: CVE crítico não pode ficar dormindo no baseline. Vale o desvio para preservar a segurança como linha-vermelha.

### 3.17 Excluído na v1

- SonarQube (exige servidor; foge do "rodar local pré-PR")
- Hooks git (pre-push) — documentado em `references/` como sugestão
- CI / GitHub Actions — extensão futura, fora do escopo
- Histórico/gráficos de evolução — git log resolve
- Auto-instalação de ferramentas sem confirmação — manifestos sugerem, agente decide

---

## 4. Pilares e ferramentas — visão consolidada

| Pilar | Python | Go | Rust | BunJS | Cross-language |
|---|---|---|---|---|---|
| Lint / complexidade | ruff, radon | golangci-lint, gocyclo | clippy | biome / oxlint | — |
| Testes | pytest | go test | cargo test | bun test | — |
| Coverage | pytest-cov / coverage.py | go cover | cargo llvm-cov | bun test --coverage | — |
| Duplicação | jscpd | jscpd | jscpd | jscpd | jscpd |
| Vuln deps | — | — | — | — | OSV-Scanner |
| SAST patterns | bandit | (via Semgrep) | (via Semgrep) | (via Semgrep) | Semgrep CE |

Bandit cobre patterns Python específicos; Semgrep CE adiciona análise cross-language.

---

## 5. Fluxo operacional

```
Dev/agente termina trabalho
        ↓
quality-gate run
        ↓
detect → run (por projeto) → security → ratchet → report
        ↓
Lê report.md
        ↓
PASSED → abre PR
FAILED → corrige regressões → re-roda
   OU
FAILED → quality-gate to-backlog → cria issues para débito pré-existente
        ↓
Após merge na main:
   quality-gate update-baseline → commit do novo baseline
```

---

## 6. Consequências

### Positivas
- **Adoção viável em legado.** Bootstrap congela o estado atual; não exige perfeição imediata.
- **Anti-cheat embutido.** Desinstalar ferramenta = FAIL. Editar baseline em feature = bloqueado.
- **Determinístico.** Re-execuções consistentes; idempotência testável via `report_hash`.
- **Agnóstico de linguagem.** Contrato formal permite adicionar Java/Ruby/etc. sem mexer no core.
- **Sem infra.** Tudo local; sem servidor, sem SaaS, sem CI obrigatório.
- **Open-source de ponta a ponta.** OSV-Scanner, Semgrep CE, ferramentas nativas de cada linguagem.

### Negativas / trade-offs aceitos
- **Não rodar em CI na v1.** Confiamos no operador honesto e no anti-cheat. Risco residual: agente desinstala ferramenta para "passar" só passa uma vez (próxima run com baseline atualizado falha).
- **Tolerância de 0.05% em percentuais.** Aceita ruído de medição; não acumula drift porque o baseline só atualiza na main após melhoria.
- **Desvio do ratchet puro em vuln criticals.** Filosofia "ratchet" cede à filosofia "segurança"; documentado.
- **Sem auto-correção.** Operador (humano ou agente) precisa decidir o que fazer com regressões. Aceitamos a fricção em troca de consistência e previsibilidade.
- **Determinismo é "mínimo", não absoluto.** Versões de ferramentas, ordem de arquivos em FS, ambiente — todos podem variar; medidas mitigam mas não eliminam. Aceitável para o objetivo (pré-PR, não certificação).

### Riscos a monitorar
- Crescimento do `baseline.json` em monorepos muito grandes (>10k arquivos cruzando soft_limit). Mitigação: reavaliar soft_limits.
- Tempo total de execução em repos grandes (cobertura + SAST + duplicação). Mitigação: `--language` e `--only` para iteração.
- Manutenção de manifests `tools.json` à medida que ferramentas mudam comandos de instalação.

---

## 7. Implementação

Plano staged em 7 estágios, com gate reviewer (light): [`docs/plans/quality-gate-skill.md`](../plans/quality-gate-skill.md).

1. Core skeleton — SKILL.md, schemas, lib, cli, _template, stubs (`judgment / extended`)
2. Python language pack (`standard / standard`)
3. Go language pack (`standard / standard`)
4. Rust language pack (`standard / standard`)
5. BunJS language pack (`standard / standard`)
6. Security pack — OSV-Scanner + Semgrep CE (`standard / standard`)
7. references/ docs + SKILL.md polish (`mechanical / minimal`)

---

## 8. Referências

- [OSV-Scanner](https://github.com/google/osv-scanner)
- [Semgrep Community Edition](https://semgrep.dev/products/community-edition/)
- [JSCPD — Code Duplication Detector](https://github.com/kucherenko/jscpd)
- Skill `to-issues` (formato dos issues gerados por `to-backlog`)
- Skill `staged-plan` (estrutura do plano de implementação)
