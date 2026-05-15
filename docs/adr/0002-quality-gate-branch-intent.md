# ADR 0002 — Quality Gate: intent declarado por branch (v2)

- **Status:** Accepted
- **Data:** 2026-05-12
- **Decisores:** Paulo Corcino
- **Contexto da decisão:** sessão `/grill-me` consolidada após adoção real em `channel2api`
- **Plano de implementação:** [`/home/corcino/.claude/plans/planeje-os-ajustes-serene-forest.md`](../../../../.claude/plans/planeje-os-ajustes-serene-forest.md)
- **Supersede:** ADR 0001 §3.1 (parcial), §3.6, §3.7, §3.10 (exit codes), §3.13 (inviolable rules)

---

## 1. Contexto

A v1 (ADR 0001) foi implementada e adotada em um repo real (`channel2api`). A primeira semana de uso revelou três fricções estruturais:

1. **Paradoxo do bootstrap.** A regra "baseline lido via `git show <main>:baseline.json`" assume que o bootstrap aconteceu em `main`. Quando o bootstrap real foi feito numa feature branch (cenário comum em projetos com refatoração ativa em curso), `run` retorna `NO_BASELINE` (exit 3) mesmo com `baseline.json` commitado — o arquivo só existe na branch, não em `main`.

2. **Decisão implícita sobre a natureza da branch.** A v1 assume tacitamente que toda branch é uma extensão de `main`. Branches que são refatorações arquiteturais onde `main` é legado não têm caminho de primeira classe — `update-baseline --force` é usado como hack para esses casos, mas é semanticamente ambíguo (capturar baseline ou contornar guard?).

3. **Mensagem de erro engana.** Stdout do `run` mostra `regressions: 0` (lê-se como sucesso); só o exit code revela que nada foi avaliado. Sem ler a doc, ninguém entende.

**Diagnóstico raiz:** a v1 trata `main` como ponto único de governança implícito. Branches são consumidoras passivas. Isso quebra quando o bootstrap precisa começar fora de `main` ou quando uma branch propõe ser o novo `main`.

## 2. Decisão central

Substituir a regra implícita **"baseline vem de main"** pela primitiva **intent declarado por branch**. Cada branch ≠ main deve declarar (e commitar) como se relaciona com main antes de rodar o gate, em um modo entre dois disponíveis:

- **`extend`** — branch estende main; ratchet contra a baseline existente em main, lida no **merge-base** entre HEAD e main.
- **`replace`** — branch substitui main; captura snapshot próprio que se torna o novo piso pós-merge.

A declaração vive em `.quality-gate/branch.json`, é versionada na branch, e é obrigatória — sem ela, `run` retorna `NO_INTENT` (exit 5) com mensagem orientadora.

## 3. Decisões detalhadas

### 3.1 Semântica do `replace` no merge — supersede ADR 0001 §3.1

Quando uma branch em modo `replace` é mergeada para main, seu `baseline.json` substitui o de main. Mesmo arquivo, mesma trilha git. **Razão:** força o reviewer a aprovar explicitamente a substituição (o diff aparece no PR). Alternativas (descartar no merge / coexistir em arquivos separados) criam ambiguidade silenciosa ou complexidade pós-merge.

### 3.2 Leitura em `extend` — supersede ADR 0001 §3.6

`extend` lê baseline via `git show <merge-base(HEAD, main)>:.quality-gate/baseline.json`, **não** via `git show <main>:`. **Razão:** comparação semanticamente correta é contra o estado em que a branch divergiu de main, não contra um main que andou enquanto a branch estava aberta. Long-lived branches não são punidas por melhorias paralelas em main. Sincronização (rebase/merge from main) avança o merge-base — ferramenta separada do ratchet.

### 3.3 Comando único `establish` — supersede ADR 0001 §3.10 (subcomandos)

`update-baseline` é removido. Substituído por `establish --mode {extend|replace} [--anchor-ref main] [--rationale "..."] [--force]`. **Razão:** "escrever baseline" e "declarar intent" são duas faces do mesmo ato (declaração de piso a partir deste commit). Comandos separados forçam o usuário a aprender uma distinção que não existe na operação real.

### 3.4 Hard error sem intent declarado

`run` em branch ≠ main sem `branch.json` retorna **`NO_INTENT` (exit 5)** com mensagem orientadora que lista os dois comandos válidos. **Razão:** toda a tese do redesign é tornar intent explícito; default implícito (para `extend`) reintroduz exatamente o problema que motiva esta ADR.

### 3.5 Strict one-shot com `--force`

`establish` recusa-se a sobrescrever `branch.json` existente, salvo com `--force`. A flag exige `--mode` explícito e age autoritativamente sobre os arquivos de estado conforme tabela:

| Transição | branch.json | baseline.json |
|---|---|---|
| `extend` (1ª vez) | cria | (não toca) |
| `replace` (1ª vez) | cria | cria (snapshot) |
| `--force` `replace → extend` | sobrescreve | **deleta** |
| `--force` `extend → replace` | sobrescreve | cria (snapshot) |
| `--force` `replace → replace` | sobrescreve | **re-snapshot** |
| `--force` `extend → extend` | sobrescreve | (n/a) |

**Razão:** `establish` é dono do estado QG da branch. Deixar artefatos órfãos (ex: `baseline.json` em modo `extend`) introduz divergência silenciosa.

### 3.6 Main special-cased — supersede ADR 0001 §3.7

Main não tem `branch.json`. `establish --mode replace` em main captura snapshot (equivalente ao antigo `update-baseline`). `establish --mode extend` em main é rejeitado (anchored a si mesmo não tem semântica). `run` em main lê `baseline.json` do working tree direto. Se `branch.json` vazar para main via merge, o gate emite warning. **Razão:** main É a referência canônica; inventar um modo `canonical` para uniformizar é cosmético e multiplica conceitos.

### 3.7 Nomes da primitiva

`extend` (branch estende main) e `replace` (branch substitui main). **Razão:** linguagem natural sobre o que a branch significa, não jargão sobre o que o comando faz. `anchored`/`rebaseline` (considerados) exigem que o leitor saiba o termo de antemão.

### 3.8 `init` permanece separado de `establish`

`init` continua sendo o scaffold de repo (cria `.quality-gate/`, `config.json`, `.gitignore`). `establish` opera por branch. **Razão:** escopos distintos — configurar a ferramenta no repo é uma operação única e compartilhada; declarar intent é por-branch e recorrente.

### 3.9 Hard cutover de migração

Repos que já usam v1 (com `baseline.json` em main mas sem `branch.json`): branches em voo retornam `NO_INTENT` no próximo `run` até que `establish` rode. **Razão:** abrir exceção pra "modo legado" reintroduz o problema do design. Skill é jovem o suficiente para absorver o custo de migração agora.

### 3.10 Conflito de dois `replace` simultâneos

Sem tooling especial. Conflito em `baseline.json` é tratado pelo fluxo de merge git padrão; a segunda branch normalmente roda `establish --mode replace --force` após sincronizar com main. Documentado em `references/branch-modes.md`. **Razão:** evento raro; criar primitiva para automatizar a "escolha óbvia" fecha portas para revisões manuais legítimas.

## 4. Inviolable rules atualizadas — supersede ADR 0001 §3.13

Lista canônica passa a ser:

- NUNCA edite `baseline.json` ou `branch.json` manualmente.
- NUNCA rode `run` em branch sem ter declarado intent via `establish`.
- NUNCA desinstale ferramenta para "passar" o gate.
- NUNCA relaxe tolerâncias no código da skill para um caso pontual.
- A intenção declarada via `branch.json` é commitada e versionada; ela é parte do PR.

## 5. Exit codes atualizados — supersede ADR 0001 §3.10

| Exit | Significado |
|---|---|
| 0 | PASSED |
| 1 | FAILED (regressão detectada) |
| 2 | PASSED_WITH_GAPS (ferramentas faltam, não estavam no baseline) |
| 3 | NO_BASELINE (modo declarado mas ref alvo sem baseline) |
| 4 | TOOL_MISSING_REGRESSION |
| **5** | **NO_INTENT — branch sem `branch.json` declarado** (novo) |
| 10 | CONFIG_ERROR |
| 20 | INTERNAL_ERROR |

## 6. Consequências

### Positivas

- **Bootstrap funciona em qualquer branch.** `establish --mode replace` em uma feature branch é cidadão de primeira classe; o paradoxo do bootstrap desaparece.
- **Intent declarado força conversa no PR.** O diff de `branch.json` aparece no review; revisores enxergam imediatamente se a branch promete estender ou substituir o piso atual.
- **Long-lived branches ficam sãs.** Merge-base como ref do `extend` significa que melhorias em main não punem retroativamente branches em voo.
- **Mensagens de erro acionáveis.** `NO_INTENT` lista o comando exato; `NO_BASELINE` lista as refs consultadas.
- **Refatorações arquiteturais têm caminho explícito.** Não mais `--force` semântico ambíguo.

### Negativas / trade-offs aceitos

- **Breaking change para usuários da v1.** Migração exige `establish` em cada branch em voo. Custo único, ~30s/branch.
- **Mais um arquivo na trilha (.quality-gate/branch.json) commitado por branch.** Custo aceitável pela explicitação que ele força.
- **`establish --force` é poderoso (pode deletar baseline.json).** Mitigação: log explícito + `--mode` obrigatório + tabela documentada do efeito.
- **Conflito em `replace` simultâneo não tem tooling.** Aceito; cenário raro, fluxo git resolve.

### Riscos a monitorar

- Vazamento de `branch.json` para main via merge. Mitigação: warning no `run` em main; documentação no fluxo de PR.
- Confusão entre `extend` e `replace` em equipes adotando agora. Mitigação: `references/branch-modes.md` com cenários reais.
- Pressão para reintroduzir "legacy mode" / default implícito. Resistir: a tese só vale com obrigatoriedade.

## 7. Escopo da implementação

PR principal atômico cobre:
- Schema `branch.json` + validação
- Comando `establish` (substitui `update-baseline`)
- Leitura via merge-base em `extend`
- `NO_INTENT` + mensagens acionáveis
- Tabela do `--force`
- Special-casing de main
- Docs: SKILL.md, bootstrap.md, branch-modes.md (nova), missing-tools.md

Follow-ups independentes (PRs separados, ordem livre):
1. Wrapper `bin/qg` (elimina `PYTHONPATH`)
2. `gate_status` explícito no Summary do report
3. Distinguir `— (not measured)` de `— (tool absent)` no report
4. `run --explain` (dry-run informativo)

Detalhamento operacional em [`/home/corcino/.claude/plans/planeje-os-ajustes-serene-forest.md`](../../../../.claude/plans/planeje-os-ajustes-serene-forest.md).

## 8. Referências

- ADR 0001 — Quality Gate skill: conceito e decisões de arquitetura (parcialmente superseded)
- Sessão `/grill-me` que consolidou as 12 decisões (12 questões: Q1–Q12)
