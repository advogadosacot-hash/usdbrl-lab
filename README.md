# usdbrl-lab

Laboratório **experimental e pessoal** de previsão probabilística do USD/BRL, com custo zero.

Toda previsão é registrada antes do resultado e depois comparada com o que realmente aconteceu.
Quando os dados ou os testes não mostram vantagem real sobre os baselines, o sistema publica
**"Sem previsão confiável"** em vez de forçar um número.

> Isto não é recomendação de investimento. É um projeto de estudo.

## Situação

**Fase 0 — Fundação.** Existem apenas a estrutura do pacote, a configuração aprovada, os testes e o CI.
Nenhuma coleta, modelo ou painel foi implementado ainda.

## Arquitetura em uma frase

Este repositório (público) guarda código, configuração e documentação. Dados de mercado com preços do
Yahoo vivem em um repositório **privado** separado (`usdbrl-data`) e nunca são publicados aqui.

## Uso local

```bash
uv sync --locked
uv run pytest
uv run usdbrl-lab config-check
```

## Documentação

- [`docs/decisions.md`](docs/decisions.md) — decisões aprovadas e congeladas.
- `config/*.toml` — parâmetros versionados (target, gate, qualidade, sessão, fontes, features, modelos).

## Licença

Sem licença própria (decisão P9): todos os direitos reservados. O código está visível, mas não é
licenciado para reutilização. As dependências seguem suas próprias licenças.
