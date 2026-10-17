"""Etapa 1: carrega questões e árvore de temas, limpa o texto e marca flags de risco nos temas.

Usado como módulo pelos outros scripts. Rodando direto, imprime um resumo e grava
cache/arvore.txt (a árvore exatamente como vai no prompt).
"""
import csv
import html
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).parent
DADOS = RAIZ / "dados"
CACHE = RAIZ / "cache"

# Títulos genéricos que viraram "lixeira": atraem questões que não são deles.
RE_GENERICO = re.compile(
    r"introdu|teoria geral|no[cç][oõ]es|disposi[cç][oõ]es gerais|conceito|princ[ií]pios|parte geral",
    re.I,
)
RE_PARTE = re.compile(r"\(parte \w+\)", re.I)
DESCRICAO_AUTOMATICA = ("Subtema de", "Disciplina (root)")


def limpar(s):
    s = (s or "").replace("\\n", " ")
    s = re.sub(r"<br\s*/?>|</p>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s).replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\s*\n\s*", "\n", s).strip()


def texto_questao(q):
    alts = "\n".join(f"{k}) {limpar(v)}" for k, v in sorted(q["alternativas"].items()))
    return f"{limpar(q['enunciado_html'])}\n\nComando: {limpar(q['comando'])}\n\n{alts}"


def _chave_titulo(titulo):
    t = RE_PARTE.sub("", titulo).lower()
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def carregar_temas():
    """Retorna (ativos, inativos). ativos: id -> dict com pai, filhos, nivel, flags."""
    linhas = list(csv.DictReader(open(DADOS / "temas.csv", encoding="utf-8")))
    ativos = {r["tema_id"]: r for r in linhas if r["status"] == "active"}
    inativos = [r for r in linhas if r["status"] != "active"]
    for r in ativos.values():
        r["nivel"] = int(r["nivel"])
        r["filhos"] = []
        r["flags"] = set()
    for r in ativos.values():
        if r["parent_id"] in ativos:
            ativos[r["parent_id"]]["filhos"].append(r["tema_id"])

    grupos = defaultdict(list)
    for r in ativos.values():
        if r["nivel"] > 0:
            grupos[_chave_titulo(r["titulo"])].append(r)
    for grupo in grupos.values():
        if len(grupo) > 1:
            for r in grupo:
                r["flags"].add("parte" if any(RE_PARTE.search(g["titulo"]) for g in grupo) else "duplicado")
                r["gemeos"] = [g["tema_id"] for g in grupo if g is not r]
    for r in ativos.values():
        if RE_PARTE.search(r["titulo"]):
            r["flags"].add("parte")
        if r["nivel"] > 0 and RE_GENERICO.search(r["titulo"]):
            r["flags"].add("lixeira")
    return ativos, inativos


def carregar_questoes():
    return [json.loads(l) for l in open(DADOS / "questoes.jsonl", encoding="utf-8")]


def texto_arvore(ativos, inativos):
    """A árvore como vai no prompt: uma linha por tema, indentada por nível, ordem estável."""
    linhas = []

    def escrever(tid):
        r = ativos[tid]
        linha = f"{'  ' * r['nivel']}{tid} | {r['titulo']}"
        d = r["descricao"]
        if d and not d.startswith(DESCRICAO_AUTOMATICA):
            linha += f" — {d}"
        linhas.append(linha)
        for f in sorted(r["filhos"], key=lambda i: ativos[i]["titulo"]):
            escrever(f)

    for tid in sorted((t for t, r in ativos.items() if r["nivel"] == 0), key=lambda i: ativos[i]["titulo"]):
        escrever(tid)
    linhas.append("\nTEMAS INATIVOS (não podem ser usados; questão sobre eles → nenhum_serve):")
    linhas += [f"- {r['caminho']}" for r in inativos]
    return "\n".join(linhas)


if __name__ == "__main__":
    ativos, inativos = carregar_temas()
    qs = carregar_questoes()
    CACHE.mkdir(exist_ok=True)
    arvore = texto_arvore(ativos, inativos)
    (CACHE / "arvore.txt").write_text(arvore, encoding="utf-8")
    contagem = defaultdict(int)
    for r in ativos.values():
        for f in r["flags"]:
            contagem[f] += 1
    print(f"{len(qs)} questões, {len(ativos)} temas ativos, {len(inativos)} inativos")
    print("flags:", dict(contagem))
    print(f"árvore no prompt: {len(arvore)} caracteres (~{len(arvore) // 3.5:.0f} tokens)")
    print("\nexemplo de questão limpa:\n" + texto_questao(qs[0])[:600])
