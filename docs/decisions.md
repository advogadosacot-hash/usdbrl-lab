# Decisões aprovadas

Fonte: especificação técnica da Etapa 2, seção 34, aprovada pelo usuário em 2026-09-30.
Estas decisões só mudam com aprovação explícita. Os testes em
`tests/unit/test_approved_decisions.py` falham se alguma delas for alterada na configuração.

## Decisões de origem (Etapa 2)

| ID | Decisão |
| --- | --- |
| D1 | Repositório público no GitHub |
| D2 | Yahoo como fonte operacional; dados brutos nunca publicados, nem redistribuídos, nem vendidos |
| D3 | Uso pessoal/experimental, arquitetura adaptável a uso comercial futuro |
| D4 | Horizontes: 5m (experimental), 15m, 1h, 4h, 24h |
| D5 | Nenhum horizonte é presumido previsível |

## Decisões aprovadas (P1–P9)

| ID | Decisão | Onde está travada |
| --- | --- | --- |
| P1 | Dados brutos do Yahoo no repositório privado `usdbrl-data`, com credencial de privilégio mínimo | `sources.toml` (`storage = "private"`), deploy key só no environment `production` |
| P2 | Painel V1: PTAX + cartões de variação %; sem AwesomeAPI; sem dados brutos do Yahoo | Fase 7 |
| P3 | Janelas de emissão da seção 5; 24h = mesmo horário do próximo pregão | `session.toml`, `targets.toml` |
| P4 | Binance fora da cadeia de fallback do preço-alvo | `sources.toml` |
| P5 | `target_v1`: k = 0,4307, σ̂ por EWMA (λ = 0,94); GARCH no target só como `target_v2` com nova aprovação | `targets.toml`, `models.toml` (`affects_target = false`) |
| P6 | Termos verificados antes de integrar; fonte sem permissão clara não entra | `sources.toml` (`policy`) |
| P7 | Números do Promotion Gate, rebaixamento, confiança e bloqueio por evento congelados (`gate_v1`) | `gate.toml` |
| P8 | Código e repositórios em inglês; documentação, mensagens e painel em português | Convenção |
| P9 | Sem licença própria | Ausência de `LICENSE` (testado) |

## Resultado da verificação P6 (2026-09-30)

- **Binance — fora da V1.** Os Binance Vision Dataset Terms v1.0 (CC BY-NC-SA 4.0) excluem uso
  comercial e restringem o uso não comercial; a aplicação a `data-api.binance.vision` não está clara.
- **AwesomeAPI — bloqueada.** Termos de uso não localizados; retomada na fase 1 somente após confirmação.
  Enquanto isso, a cadeia de fallback de preço é apenas `yahoo` → "Sem previsão confiável".

## Decisões técnicas da Fase 0

| Tema | Escolha | Motivo |
| --- | --- | --- |
| Gerenciador e lock | `uv` + `uv.lock` (com hashes) | A especificação deixou "pip-compile ou uv" para a fase 0; `uv` já instala o Python 3.12 e verifica hashes com `--locked` |
| Python | 3.12 | Decisão T1 |
| Dependências de runtime | Nenhuma na fase 0 | Cada fase adiciona só o que usa |
| Dependências de desenvolvimento | `pytest`, `ruff` | Testes e lint do CI |

## Decisões técnicas da Fase 1 (dentro da especificação)

| Tema | Escolha | Motivo |
| --- | --- | --- |
| Dependências de runtime | `pandas`, `pyarrow`, `requests` (stack T1) e `tzdata` | `tzdata` garante o fuso `America/Sao_Paulo` da PTAX em qualquer SO |
| Limites do Yahoo (medidos em 2026-09-30) | 1m: 30 dias (blocos de 7); 5m: 60 dias; 1h: 730 dias por período, ~2,8 anos com `range=730d` | Define o backfill e a coleta incremental |
| 1 dia | Não coletado do Yahoo | Seção 5: 1 dia é reamostrado do 5 min |
| Regras de mudança anormal e feed congelado | Só na grade de 5 min, só entre candles separados por exatamente 5 min | Seção 6 define essas regras para o retorno de 5 min; o salto entre fechamento e abertura não é retorno de 5 min |
| 1 min | Guardado como veio (só plausibilidade), sem imputação | Seção 5: 1 min é arquivo de auditoria, não grade de modelo |
| Lacunas | Imputação de até 2 candles só entre candles válidos do mesmo dia | Nunca herda o close do dia anterior na abertura |
| `available_time` numa revisão da fonte | Mantém o menor valor já registrado | Não atrasa artificialmente quando o dado ficou disponível |
| Arquivos Parquet | Regravados só quando o conteúdo muda | Evita crescimento do histórico do Git no `usdbrl-data` |
| Coletor provisório | `collect.yml`, de hora em hora, 12:07–22:07 UTC, dias úteis | Prioridade da fase 1: continuidade do histórico (o Yahoo guarda 30 dias de 1 min) |

## Pontos para decisão antes da Fase 6 (não alteram nada aprovado)

- **Componente de consistência de Q.** A seção 6 prevê comparar o Yahoo com uma segunda fonte intraday
  (AwesomeAPI), que está bloqueada (P6). Hoje o componente é registrado como indisponível (`None`) e
  não entra no mínimo de Q. Q ainda não é usado por nenhuma previsão; antes da fase 6 é preciso decidir
  se a ausência de segunda fonte deve deixar Q como "normal" ou "degradado".
- **Mudança anormal sem segunda fonte.** Pela regra literal da seção 6, um salto de 5 min acima do
  limite que não pode ser confirmado é rejeitado. Sem segunda fonte, um movimento real e brusco também
  será rejeitado (só o candle do salto; os seguintes não são afetados).
