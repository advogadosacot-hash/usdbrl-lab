# usdbrl-lab

Laboratório **experimental e pessoal** de previsão probabilística do USD/BRL, com custo zero.

Toda previsão é registrada antes do resultado e depois comparada com o que realmente aconteceu.
Quando os dados ou os testes não mostram vantagem real sobre os baselines, o sistema publica
**"Sem previsão confiável"** em vez de forçar um número.

> Isto não é recomendação de investimento. É um projeto de estudo.

## Situação

**Fase 1 — Coleta e qualidade.** O coletor provisório (`collect.yml`) arquiva de hora em hora, em dias
úteis, os candles de 1 min, 5 min e 1 h do Yahoo e os boletins PTAX do BCB no repositório privado,
com as regras de qualidade da seção 6. Ainda não existem features, modelos, previsões nem painel.

## Arquitetura em uma frase

Este repositório (público) guarda código, configuração e documentação. Dados de mercado com preços do
Yahoo vivem em um repositório **privado** separado (`usdbrl-data`) e nunca são publicados aqui.

## Uso local

```bash
uv sync --locked
uv run pytest
uv run usdbrl-lab config-check
uv run usdbrl-lab ingest --data-dir ../usdbrl-data            # coleta incremental
uv run usdbrl-lab ingest --data-dir ../usdbrl-data --backfill # todo o histórico disponível
```

No Windows, se o caminho da pasta for muito longo, use um ambiente virtual em caminho curto
(`UV_PROJECT_ENVIRONMENT`), porque o `pyarrow` não importa acima do limite de caminho.

## Documentação

- [`docs/decisions.md`](docs/decisions.md) — decisões aprovadas e congeladas.
- `config/*.toml` — parâmetros versionados (target, gate, qualidade, sessão, fontes, features, modelos).

## Licença

Sem licença própria (decisão P9): todos os direitos reservados. O código está visível, mas não é
licenciado para reutilização. As dependências seguem suas próprias licenças.
