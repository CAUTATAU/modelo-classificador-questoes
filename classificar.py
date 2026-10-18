"""Etapas 2, 3 e pré-rótulo: votos de dois modelos, juiz e rotulador da amostra-ouro, via Amazon Bedrock (boto3).

Uso (perfil AWS: o default do AWS CLI; para outro, defina AWS_PROFILE):
  python classificar.py teste      # passo 0: uma chamada mínima por modelo
  python classificar.py votar [N]  # votante A (Sonnet 4.6) e B (Haiku 4.5) nas N primeiras questões (padrão: todas)
  python classificar.py juiz       # juiz (Sonnet 4.6) nas questões com nó publicável
  python classificar.py rotular    # Opus 4.6 às cegas: pré-rótulo da amostra-ouro + 3º votante nas publicáveis
As respostas ficam em cache/*.jsonl: rodar de novo só chama o que falta.
"""
import csv
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from decidir import ARQ_AMOSTRA, decidir, ler_jsonl, no_candidato, pai
from preparar import CACHE, RAIZ, DESCRICAO_AUTOMATICA, carregar_questoes, carregar_temas, texto_arvore, texto_questao

# Na conta em que os votos rodaram, a família 5.x respondeu "not available for this account":
# ficaram os mais novos liberados.
SONNET = "us.anthropic.claude-sonnet-4-6"
HAIKU = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
OPUS = "us.anthropic.claude-opus-4-6-v1"
PARALELO = 4

bedrock = boto3.Session(profile_name=os.environ.get("AWS_PROFILE")).client(  # None → perfil default do AWS CLI
    "bedrock-runtime", region_name="us-east-1",
    # adaptive: o botocore espaça as chamadas sozinho quando a conta bate no limite (ThrottlingException)
    config=Config(retries={"max_attempts": 8, "mode": "adaptive"}, read_timeout=300),
)
_trava = threading.Lock()


def esquema_voto(ativos):
    """enum com os ids reais: sem ele o Haiku inventava ids vizinhos (5688 no lugar de 4688)."""
    ids = sorted(t for t, r in ativos.items() if r["nivel"] >= 1)
    return {
        "type": "object",
        "properties": {
            "tema_central_id": {"type": "string", "enum": ids + [""]},
            "extras_ids": {"type": "array", "items": {"type": "string", "enum": ids}},
            "nenhum_serve": {"type": "boolean"},
            "segunda_opcao_id": {"type": "string", "enum": ids + [""]},
            "justificativa": {"type": "string"},
        },
        "required": ["tema_central_id", "extras_ids", "nenhum_serve", "segunda_opcao_id", "justificativa"],
        "additionalProperties": False,
    }


ESQUEMA_JUIZ = {
    "type": "object",
    "properties": {
        "veredito": {"type": "string", "enum": ["certo", "errado", "ambiguo"]},
        "tema_melhor_id": {"type": "string"},
        "justificativa": {"type": "string"},
    },
    "required": ["veredito", "tema_melhor_id", "justificativa"],
    "additionalProperties": False,
}


def invocar(modelo, corpo):
    """InvokeModel com o corpo da Messages API da Anthropic (o mesmo JSON que o SDK enviaria)."""
    r = bedrock.invoke_model(modelId=modelo, body=json.dumps({"anthropic_version": "bedrock-2023-05-31", **corpo}))
    return json.loads(r["body"].read())


def chamar(modelo, system, user, esquema, effort, max_tokens=1500):
    """effort=None: sem thinking (Haiku 4.5 não aceita effort). Voto normal: ~100 tokens; o teto corta laços raros."""
    corpo = {
        "max_tokens": max_tokens, "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": {"format": {"type": "json_schema", "schema": esquema}, **({"effort": effort} if effort else {})},
    }
    if effort:
        corpo["thinking"] = {"type": "adaptive"}
    r = invocar(modelo, corpo)
    if r["stop_reason"] != "end_turn":
        raise RuntimeError(f"stop_reason={r['stop_reason']}")
    texto = next(b["text"] for b in r["content"] if b["type"] == "text")
    return json.loads(texto), r["usage"]


def gravar(nome, registro):
    with _trava, open(CACHE / f"{nome}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")


def rodar(nome, tarefas, fazer):
    """Primeira chamada sozinha (grava o cache de prompt); o resto em paralelo. Falhas ficam para a próxima rodada."""
    total = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    falhas = []

    def um(t):
        try:
            reg = fazer(t)
        except (ClientError, BotoCoreError, RuntimeError, json.JSONDecodeError) as e:
            falhas.append(t["id"])
            print(f"  falhou {t['id']}: {type(e).__name__}: {str(e)[:200]}")
            return
        gravar(nome, reg)
        with _trava:
            for k in total:
                total[k] += reg["uso"].get(k) or 0

    if tarefas:
        um(tarefas[0])
        with ThreadPoolExecutor(PARALELO) as pool:
            list(pool.map(um, tarefas[1:]))
    print(f"{nome}: {len(tarefas) - len(falhas)} feitas, {len(falhas)} falhas | tokens {total}")


def classificar_com(nome, modelo, qs, effort, pista=False, max_tokens=1500):
    """Uma passada do prompt de classificação (árvore inteira em cache) por um modelo."""
    ativos, inativos = carregar_temas()
    system = [{"type": "text", "cache_control": {"type": "ephemeral"},
               "text": (RAIZ / "prompts/classificar.md").read_text(encoding="utf-8")
               .replace("{arvore}", texto_arvore(ativos, inativos))}]
    esquema = esquema_voto(ativos)
    feitos = ler_jsonl(nome)

    def fazer(q):
        user = f"Questão:\n{texto_questao(q)}"
        if pista:
            user += (f"\n\nPista do site de origem (pode estar errada): disciplina = {q['disciplina_origem'] or '?'};"
                     f" assunto = {q['assunto_origem'] or '?'}")
        voto, uso = chamar(modelo, system, user, esquema, effort, max_tokens)
        return {"id": q["id"], **voto, "modelo": modelo, "uso": uso}

    rodar(nome, [q for q in qs if q["id"] not in feitos], fazer)


def votar(n=None):
    qs = carregar_questoes()[:n]
    # só o votante A vê a pista da origem: entradas diferentes → erros menos correlacionados
    classificar_com("votos_A", SONNET, qs, "low", pista=True)
    classificar_com("votos_B", HAIKU, qs, None)


def rotular():
    """Opus 4.6 (effort alto, sem pista, sem ver os votos) na amostra-ouro e nas publicáveis pelas regras de 2 votos.
    O mesmo procedimento serve de pré-rótulo da amostra e de 3º votante: só publica se ele cair no mesmo ramo."""
    ativos, _ = carregar_temas()
    ids = {r["id"] for r in csv.DictReader(open(ARQ_AMOSTRA, encoding="utf-8-sig"))}
    va, vb, vj = ler_jsonl("votos_A"), ler_jsonl("votos_B"), ler_jsonl("juiz")
    qs = [q for q in carregar_questoes() if q["id"] in ids
          or decidir(q, va.get(q["id"]), vb.get(q["id"]), vj.get(q["id"]), ativos)[0] == "publicar"]
    classificar_com("rotulos_opus", OPUS, qs, "high", max_tokens=8000)


def _linha(t, ativos):
    return f"{t} | {ativos[t]['caminho']}"


def juiz():
    ativos, _ = carregar_temas()
    system = (RAIZ / "prompts/juiz.md").read_text(encoding="utf-8")
    va, vb, feitos = ler_jsonl("votos_A"), ler_jsonl("votos_B"), ler_jsonl("juiz")
    tarefas = []
    for q in carregar_questoes():
        no = no_candidato(va.get(q["id"]), vb.get(q["id"]), ativos)
        if no and feitos.get(q["id"], {}).get("no") != no:
            tarefas.append({**q, "no": no})

    def fazer(q):
        no, r = q["no"], ativos[q["no"]]
        irmaos = [f for f in ativos[pai(no, ativos)]["filhos"] if f != no]
        desc = r["descricao"] if r["descricao"] and not r["descricao"].startswith(DESCRICAO_AUTOMATICA) else ""
        user = (f"Tema proposto: {_linha(no, ativos)}\n" + (f"Descrição: {desc}\n" if desc else "")
                + "Subtemas dele:\n" + ("\n".join(_linha(f, ativos) for f in r["filhos"]) or "(nenhum)")
                + "\nTemas irmãos:\n" + ("\n".join(_linha(f, ativos) for f in irmaos) or "(nenhum)")
                + f"\n\nQuestão:\n{texto_questao(q)}")
        v, uso = chamar(SONNET, system, user, ESQUEMA_JUIZ, "medium", max_tokens=4000)
        return {"id": q["id"], "no": no, **v, "modelo": SONNET, "uso": uso}

    rodar("juiz", tarefas, fazer)


def teste():
    for modelo in (SONNET, HAIKU, OPUS):
        try:
            r = invocar(modelo, {"max_tokens": 300, "messages": [{"role": "user", "content": "Responda apenas: ok"}]})
            texto = next((b["text"] for b in r["content"] if b["type"] == "text"), "")
            print(f"OK  {modelo}: {texto!r} stop={r['stop_reason']} uso={r['usage']}")
        except (ClientError, BotoCoreError) as e:
            print(f"ERRO {modelo}: {type(e).__name__}: {str(e)[:300]}")


if __name__ == "__main__":
    CACHE.mkdir(exist_ok=True)
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "teste":
        teste()
    elif cmd == "votar":
        votar(int(sys.argv[2]) if len(sys.argv) > 2 else None)
    elif cmd == "juiz":
        juiz()
    elif cmd == "rotular":
        rotular()
    else:
        print(__doc__)
