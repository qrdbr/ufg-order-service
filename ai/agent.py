"""Agente GenAI do pipeline do OrderService.

Subcomandos:
  summarize  - resume o diff de um PR para documentação (CI com sucesso)
  diagnose   - correlaciona o log de falha com o diff e sugere correção (CI com falha)
  incident   - analisa a causa raiz de uma anomalia de produção (webhook)

Cada subcomando grava a resposta em Markdown no arquivo indicado por --output.
O workflow publica esse arquivo no PR ou numa Issue com o `gh`.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import anthropic

MODEL = os.environ.get("CLAUDE_MODEL") or "claude-opus-5-5"
# O diff, o log e o payload vão inteiros quando cabem. Acima desse tamanho, a
# entrada é cortada e o prompt avisa o modelo, que repassa o aviso na resposta.
MAX_INPUT_CHARS = 400_000

SYSTEM_PROMPT = """Você é um engenheiro de software sênior que atua como agente no pipeline \
de CI/CD do OrderService, uma API REST de pedidos em Python/FastAPI. Responda sempre em \
português do Brasil, em Markdown compatível com comentários do GitHub. Seja direto e \
baseie cada afirmação nos dados fornecidos: cite arquivos e linhas do diff ou trechos do \
log. Quando não houver evidência suficiente para uma conclusão, diga isso em vez de \
supor. Não repita o diff ou o log inteiro na resposta."""

SUMMARIZE_TASK = """O pipeline de CI deste Pull Request passou. Escreva um resumo das \
mudanças para a documentação do projeto, com as seções:

### Resumo
Duas ou três frases sobre o que mudou e por quê, do ponto de vista de quem usa a API.

### Mudanças
Lista por arquivo ou área, com o efeito de cada mudança.

### Impacto na API
Endpoints, contratos (campos, status HTTP) e comportamento que mudaram. Escreva \
"Nenhum" se não houver.

### Pontos de atenção
Riscos, trechos frágeis tocados pelo PR, testes que faltam. Escreva "Nenhum" se não houver."""

DIAGNOSE_TASK = """O pipeline de CI deste Pull Request falhou. Correlacione o log de \
erro com as mudanças do diff e escreva:

### Causa raiz
O que falhou e por quê, apontando a linha do diff responsável quando ela existir. \
Se a falha não vier do diff (ex.: problema de infraestrutura ou teste instável), diga isso.

### Correção sugerida
O trecho corrigido em bloco ```suggestion``` ou ```python```, indicando arquivo e linha.

### Como validar
Comando ou teste que confirma a correção."""

INCIDENT_TASK = """Uma anomalia foi detectada em produção pela ferramenta de \
observabilidade. Use o alerta, as métricas e os logs fornecidos, e os commits recentes \
implantados, para escrever:

### Diagnóstico
O que está acontecendo, com os números das métricas e as linhas de log que sustentam isso.

### Causa raiz provável
A hipótese mais provável e o nível de confiança (alto, médio, baixo). Se um commit \
recente for suspeito, cite o hash e o arquivo.

### Ações imediatas
Passos para mitigar agora (ex.: rollback, feature flag, escalar).

### Correção definitiva
Mudança de código ou configuração recomendada."""


def read_input(path: str, label: str) -> str:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        return f"<{label}>\n(vazio)\n</{label}>"
    if len(text) > MAX_INPUT_CHARS:
        note = (
            f"(ATENÇÃO: {label} tinha {len(text)} caracteres e foi cortado nos primeiros "
            f"{MAX_INPUT_CHARS}. Avise isso na resposta.)\n"
        )
        text = note + text[:MAX_INPUT_CHARS]
    return f"<{label}>\n{text}\n</{label}>"


def ask_claude(task: str, context: str) -> str:
    client = anthropic.Anthropic()
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=64000,
        system=SYSTEM_PROMPT,
        output_config={"effort": "high"},
        # Se o classificador de segurança recusar o pedido, a API refaz a chamada
        # no modelo de fallback recomendado, em vez de devolver a recusa.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": f"{context}\n\n{task}"}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "refusal":
        raise RuntimeError("O modelo recusou o pedido.")
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if response.stop_reason == "max_tokens":
        text += "\n\n_(resposta interrompida: limite de tokens atingido)_"
    return text


def footer() -> str:
    run_url = os.environ.get("RUN_URL")
    origin = f" · [execução do workflow]({run_url})" if run_url else ""
    return f"\n\n---\n<sub>🤖 Gerado por GenAI ({MODEL}){origin}. Revise antes de aplicar.</sub>"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_sum = sub.add_parser("summarize", help="Resumo do diff do PR")
    p_sum.add_argument("--diff", required=True)

    p_diag = sub.add_parser("diagnose", help="Diagnóstico de falha do CI")
    p_diag.add_argument("--diff", required=True)
    p_diag.add_argument("--log", required=True)

    p_inc = sub.add_parser("incident", help="Análise de causa raiz de anomalia")
    p_inc.add_argument("--payload", required=True, help="JSON do alerta (client_payload)")
    p_inc.add_argument("--commits", required=True, help="Saída de git log -p dos commits recentes")

    for p in (p_sum, p_diag, p_inc):
        p.add_argument("--output", required=True)

    args = parser.parse_args()

    if args.command == "summarize":
        title = "## 📝 Resumo das mudanças (CI ✅)"
        context = read_input(args.diff, "diff")
        task = SUMMARIZE_TASK
    elif args.command == "diagnose":
        title = "## 🔍 Diagnóstico da falha (CI ❌)"
        context = read_input(args.diff, "diff") + "\n\n" + read_input(args.log, "log_de_erro")
        task = DIAGNOSE_TASK
    else:
        title = "## 🚨 Análise de causa raiz"
        payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
        context = (
            f"<alerta>\n{json.dumps(payload, indent=2, ensure_ascii=False)}\n</alerta>\n\n"
            + read_input(args.commits, "commits_recentes")
        )
        task = INCIDENT_TASK

    try:
        body = ask_claude(task, context)
    except (anthropic.APIError, RuntimeError) as exc:
        # A falha do agente não deve derrubar o pipeline; o PR recebe um aviso.
        print(f"Falha ao consultar o modelo: {exc}", file=sys.stderr)
        body = f"Não foi possível gerar a análise automática: `{type(exc).__name__}`."

    Path(args.output).write_text(f"{title}\n\n{body}{footer()}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
