# OrderService

O OrderService é uma API REST de e-commerce simplificada, em Python com FastAPI, que processa pedidos. A aplicação funciona, mas tem trechos de código frágeis de propósito e não tem documentação atualizada, um cenário comum em manutenção evolutiva. Os trechos frágeis estão marcados com `FRÁGIL` em [app/services.py](app/services.py) e [app/repository.py](app/repository.py).

## O fluxo de trabalho inteligente

O projeto tem os seguintes estágios de integração, todos na plataforma **GitHub** com **GitHub Actions**:

1. **Gatilho de evento:** o desenvolvedor faz um commit e um push para uma branch no GitHub, depois abre um **Pull Request (PR)**. Os eventos `push` e `pull_request` iniciam a integração contínua.
2. **Validação e testes:** o GitHub Actions executa o workflow [.github/workflows/ci.yml](.github/workflows/ci.yml), que roda o lint, os testes unitários e o build da imagem Docker.
3. **Intervenção da GenAI (o diferencial):**
   - **Em caso de sucesso:** o agente de IA analisa o diff do PR e gera um resumo das mudanças para a documentação. O resumo é publicado como comentário no Pull Request.
   - **Em caso de falha:** o agente lê o log do job que falhou, cruza esse log com o diff do PR e então sugere uma correção ou explica a causa raiz. A resposta vai direto para a discussão do Pull Request.
4. **Implantação (CD):** depois que o Pull Request é aprovado e entra na `main`, o workflow [.github/workflows/deploy.yml](.github/workflows/deploy.yml) publica a imagem no **GitHub Container Registry (GHCR)** e implanta o serviço no ambiente `staging`. Em seguida, depois de uma aprovação manual, implanta no ambiente `production`.
5. **Monitoramento assistido:** em produção, as métricas vão para o Prometheus e os logs vão para o Loki. Quando o Prometheus detecta uma anomalia, o Alertmanager chama um relay. O relay junta métricas e logs e dispara o evento `repository_dispatch` no GitHub. Esse evento inicia o workflow [.github/workflows/incident-analysis.yml](.github/workflows/incident-analysis.yml), em que a GenAI analisa a causa raiz e abre uma **Issue**.

```
push / PR ──► CI (lint, testes, build) ──┬─ sucesso ─► GenAI resume o diff ─► comentário no PR
                                         └─ falha ───► GenAI diagnostica  ─► comentário no PR
PR aprovado + merge na main ──► Deploy: GHCR ─► staging ─► (aprovação) ─► production
produção ──► Prometheus/Loki ─► Alertmanager ─► relay ─► repository_dispatch ─► GenAI ─► Issue
```

## Estrutura

| Caminho | Conteúdo |
|---|---|
| [app/](app/) | API FastAPI: modelos, regras de negócio, logs JSON e métricas em `/metrics` |
| [tests/](tests/) | Testes unitários (pytest) |
| [ai/agent.py](ai/agent.py) | Agente GenAI (Claude) com os subcomandos `summarize`, `diagnose` e `incident` |
| [.github/workflows/](.github/workflows/) | Workflows de CI, deploy e análise de incidente |
| [scripts/deploy.sh](scripts/deploy.sh) | Deploy do contêiner via SSH, com smoke test |
| [observability/](observability/) | Prometheus, Alertmanager, Loki, Alloy, Grafana e o relay de alertas |
| [scripts/generate_traffic.py](scripts/generate_traffic.py) | Gera tráfego e erros 500 para disparar o alerta |

## Executar localmente

```bash
python -m venv .venv && source .venv/bin/activate   # no Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest
uvicorn app.main:app --reload
```

A documentação interativa fica em http://localhost:8000/docs.

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET | `/health` | Verificação de saúde |
| GET | `/products` | Lista produtos e estoque |
| POST | `/orders` | Cria pedido (`customer_email`, `items`, `coupon` opcional no formato `PROMO<NN>`) |
| GET | `/orders` | Lista pedidos |
| GET | `/orders/{id}` | Consulta pedido |
| POST | `/orders/{id}/pay` | Marca o pedido como pago |
| POST | `/orders/{id}/ship` | Marca o pedido como enviado |
| POST | `/orders/{id}/cancel` | Cancela o pedido e devolve o estoque |
| GET | `/metrics` | Métricas Prometheus |

## Configuração no GitHub

1. **Secret do agente:** em *Settings → Secrets and variables → Actions*, crie `ANTHROPIC_API_KEY`. Opcionalmente, crie a variável `CLAUDE_MODEL` para trocar o modelo (o padrão é `claude-opus-5-5`).
2. **Aprovação do PR:** em *Settings → Rules → Rulesets* (ou *Branches*), proteja a `main` exigindo Pull Request com pelo menos uma aprovação e o check **Build e testes** passando.
3. **Ambientes:** em *Settings → Environments*, crie `staging` e `production`. Em `production`, ative **Required reviewers**. Esta é a aprovação manual do deploy.
4. **Servidor de deploy (opcional):** em cada environment, crie os secrets `DEPLOY_HOST`, `DEPLOY_USER` e `DEPLOY_SSH_KEY`. Sem eles, o `deploy.sh` sobe o contêiner no próprio runner e faz o smoke test lá, para demonstrar o fluxo completo.
5. **Monitoramento:** no servidor de produção, rode a stack de observabilidade com um token que possa disparar `repository_dispatch` (um fine-grained token com permissão **Contents: Read and write** no repositório):

   ```bash
   cd observability
   GITHUB_REPOSITORY=dono/ufg-order-service GITHUB_TOKEN=github_pat_... docker compose up -d --build
   python ../scripts/generate_traffic.py http://localhost:8000 300
   ```

   Os cupons inválidos gerados pelo script fazem a API devolver erro 500. Em cerca de 2 minutos, o alerta `OrderServiceHighErrorRate` dispara e uma Issue com a análise aparece no repositório. Também é possível testar o workflow sem a stack, em *Actions → Análise de incidente → Run workflow*.

## Observações

- Os comentários da GenAI são sugestões. Revise o conteúdo antes de aplicar uma correção.
- PRs abertos a partir de forks não recebem secrets, por isso os jobs da GenAI só rodam em PRs de branches do próprio repositório.
- Para mudar o `ai/agent.py` ou os workflows com segurança, teste primeiro numa branch: os jobs da GenAI rodam no próprio PR.
