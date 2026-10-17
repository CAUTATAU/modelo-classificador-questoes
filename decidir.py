"""Etapas 4 e 5: regras publicar/revisar/fora → publicacao.csv, amostra-ouro e estimativa de precisão.

Uso:
  python decidir.py            # gera publicacao.csv; se amostra_ouro.csv estiver rotulada, mede a precisão
  python decidir.py amostra    # sorteia a amostra-ouro (amostra_ouro.csv + cache/amostra_para_rotular.md)
  python decidir.py preencher  # põe os rótulos do Opus na amostra e gera cache/conferir.md para revisão humana
"""
import csv
import json
import math
import random
import sys
from collections import Counter

from preparar import CACHE, RAIZ, carregar_questoes, carregar_temas, texto_questao

# disciplina_origem que não pertence ao recorte (pode estar errada: vira alerta, não decisão)
FORA_ESCOPO = {"Direito Constitucional", "Direito Civil - Legislação Especial", "Direito Tributário", "Direito Ambiental"}
# Confiança antes de existir amostra rotulada; substituída pelo acerto observado em cada grupo.
CONFIANCA_INICIAL = {"unanime": 0.97, "ramo": 0.92, "revisar_flag": 0.75, "revisar_juiz": 0.5,
                     "revisar_diverge": 0.4, "revisar_opus": 0.6, "fora": 0.7}
ARQ_PUBLICACAO = RAIZ / "publicacao.csv"
ARQ_AMOSTRA = RAIZ / "amostra_ouro.csv"


# ---------- árvore ----------

def pai(t, ativos):
    p = ativos[t]["parent_id"]
    return p if p in ativos else None


def ancestrais(t, ativos):
    cadeia = []
    while t:
        cadeia.append(t)
        t = pai(t, ativos)
    return cadeia


def mesmo_ramo(a, b, ativos):
    """A régua do case: certo se for o mesmo nó, o pai ou um filho do tema do gabarito."""
    return a == b or pai(a, ativos) == b or pai(b, ativos) == a


def valido(v, ativos):
    return bool(v) and not v["nenhum_serve"] and v["tema_central_id"] in ativos \
        and ativos[v["tema_central_id"]]["nivel"] >= 1


def no_candidato(va, vb, ativos):
    """Nó onde dá para publicar com os dois votos: o ancestral comum mais baixo, se não for disciplina raiz."""
    if not (valido(va, ativos) and valido(vb, ativos)):
        return None
    da_a = set(ancestrais(va["tema_central_id"], ativos))
    comum = next((t for t in ancestrais(vb["tema_central_id"], ativos) if t in da_a), None)
    return comum if comum and ativos[comum]["nivel"] >= 1 else None


# ---------- decisão ----------

def decidir(q, va, vb, vj, ativos):
    """Retorna (decisao, tema_central_id, extras, grupo, motivo)."""
    sugestao = next((v["tema_central_id"] for v in (va, vb) if valido(v, ativos)), "")
    if va and vb and va["nenhum_serve"] and vb["nenhum_serve"]:
        return "fora", "", [], "fora", "nenhum tema ativo serve (os dois modelos)"
    if not sugestao:  # um diz "nenhum serve" e o outro não respondeu: revisar exige tema sugerido
        return "fora", "", [], "fora", "nenhum tema sugerido (um modelo: nenhum serve; outro sem resposta)"
    no = no_candidato(va, vb, ativos)
    if no is None:
        a = va["tema_central_id"] if valido(va, ativos) else "nenhum"
        b = vb["tema_central_id"] if valido(vb, ativos) else "nenhum"
        return "revisar", sugestao, [], "revisar_diverge", f"modelos divergem: {a} x {b}"
    extras = [e for e in va.get("extras_ids", []) if e in ativos and e != no and ativos[e]["nivel"] >= 1]
    if not vj or vj["no"] != no or vj["veredito"] != "certo":
        return "revisar", no, extras, "revisar_juiz", f"juiz: {vj['veredito'] if vj else 'sem veredito'}"
    unanime = va["tema_central_id"] == vb["tema_central_id"]
    flags = ativos[no]["flags"]
    if not unanime and "lixeira" in flags:
        return "revisar", no, extras, "revisar_flag", "divergência entre subtemas caiu num tema genérico"
    if flags & {"duplicado", "parte"}:
        gemeos = set(ativos[no].get("gemeos", []))
        segundas = {va.get("segunda_opcao_id"), vb.get("segunda_opcao_id")}
        if not unanime or gemeos & segundas:
            return "revisar", no, extras, "revisar_flag", \
                f"tema duplicado/dividido: dúvida com {', '.join(sorted(gemeos)) or 'gêmeo'}"
    if q["disciplina_origem"] in FORA_ESCOPO:
        return "revisar", no, extras, "revisar_flag", f"disciplina de origem fora do recorte ({q['disciplina_origem']})"
    return "publicar", no, extras, "unanime" if unanime else "ramo", ""


def rotulo_opus(o):
    return "fora" if o["nenhum_serve"] or not o["tema_central_id"] else o["tema_central_id"]


def terceiro_voto(res, vo, ativos):
    """Filtro final: só publica se o Opus 4.6 (às cegas) também cair no mesmo ramo do nó publicado.
    Entrou depois da 1ª medição (92% < 95%): os 4 erros da amostra eram questões entre dois temas."""
    d, no, extras, grupo, motivo = res
    if d != "publicar":
        return res
    if not vo:
        return "revisar", no, extras, "revisar_opus", "falta o 3º voto (Opus)"
    t = rotulo_opus(vo)
    if t == "fora" or t not in ativos or not mesmo_ramo(no, t, ativos):
        return "revisar", no, extras, "revisar_opus", f"3º votante (Opus) discorda: {t}"
    return res


# ---------- cache e saída ----------

def ler_jsonl(nome):
    path = CACHE / f"{nome}.jsonl"
    if not path.exists():
        return {}
    return {r["id"]: r for r in map(json.loads, open(path, encoding="utf-8"))}


def validar(linhas, ativos, total):
    ids = [l["id"] for l in linhas]
    assert len(ids) == total and len(set(ids)) == total, "precisa de uma linha por questão"
    for l in linhas:
        assert l["decisao"] in ("publicar", "revisar", "fora"), l
        if l["decisao"] == "fora":
            assert l["tema_central_id"] == "" and l["motivo"], l
        else:
            assert l["tema_central_id"] in ativos and ativos[l["tema_central_id"]]["nivel"] >= 1, l
        if l["decisao"] != "publicar":
            assert l["motivo"], l
        assert 0 <= float(l["confianca"]) <= 1, l
        assert all(e in ativos for e in l["extras_ids"].split(";") if e), l


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 1.0
    p = k / n
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    meia = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centro - meia), min(1.0, centro + meia)


def ler_rotulos(ativos):
    """amostra_ouro.csv rotulada: tema_correto_id = id do tema ou 'fora'."""
    if not ARQ_AMOSTRA.exists():
        return {}
    rot = {}
    for r in csv.DictReader(open(ARQ_AMOSTRA, encoding="utf-8-sig")):
        g = r["tema_correto_id"].strip()
        if g:
            assert g == "fora" or g in ativos, f"{r['id']}: tema_correto_id inválido ({g})"
            rot[r["id"]] = g
    return rot


def acertou(linha, gold, ativos):
    if linha["decisao"] == "fora":
        return gold == "fora"
    return gold != "fora" and mesmo_ramo(linha["tema_central_id"], gold, ativos)


def avaliar(linhas, grupos, rotulos, ativos):
    print(f"\n=== Amostra-ouro: {len(rotulos)} rotuladas ===")
    pubs = [l for l in linhas if l["id"] in rotulos and l["decisao"] == "publicar"]
    k = sum(acertou(l, rotulos[l["id"]], ativos) for l in pubs)
    lo, hi = wilson(k, len(pubs))
    print(f"precisão nas publicadas: {k}/{len(pubs)} = {k / max(1, len(pubs)):.3f}  (Wilson 95%: {lo:.3f}-{hi:.3f})")
    taxa = {}
    for g in sorted(set(grupos.values())):
        ls = [l for l in linhas if l["id"] in rotulos and grupos[l["id"]] == g]
        kg = sum(acertou(l, rotulos[l["id"]], ativos) for l in ls)
        taxa[g] = (kg + 1) / (len(ls) + 2)  # suavização de Laplace: nunca 0 nem 1
        print(f"  {g:16s} {kg}/{len(ls)} certas")
    for l in pubs:
        if not acertou(l, rotulos[l["id"]], ativos):
            print(f"  ERRO {l['id']}: publicado {l['tema_central_id']} | gabarito {rotulos[l['id']]}")
    obs = {r["id"]: r["observacao"] for r in csv.DictReader(open(ARQ_AMOSTRA, encoding="utf-8-sig"))}
    # Com o Opus como 3º votante, só o rótulo conferido por humano mede sem circularidade
    humanas = [l for l in pubs if obs.get(l["id"], "").startswith("conferido")]
    kh = sum(acertou(l, rotulos[l["id"]], ativos) for l in humanas)
    lo, hi = wilson(kh, len(humanas))
    print(f"precisão nas publicadas CONFERIDAS por humano: {kh}/{len(humanas)}  (Wilson 95%: {lo:.3f}-{hi:.3f})")
    # O quanto o pré-rótulo do Opus bate com a conferência humana (risco: ele concordar demais com o Sonnet)
    opus = ler_jsonl("rotulos_opus")
    conf = [i for i in rotulos if obs.get(i, "").startswith("conferido") and i in opus]
    if conf:
        ok = sum(rotulo_opus(opus[i]) == rotulos[i] or (rotulos[i] != "fora" and rotulo_opus(opus[i]) != "fora"
                 and mesmo_ramo(rotulo_opus(opus[i]), rotulos[i], ativos)) for i in conf)
        print(f"rótulos conferidos por humano: {len(conf)} | Opus no mesmo ramo do humano em {ok}/{len(conf)}"
              f" | só Opus (não conferidos): {sum(1 for i in rotulos if obs.get(i) == 'opus')}")
    return taxa


def gerar():
    ativos, _ = carregar_temas()
    qs = carregar_questoes()
    va, vb, vj, vo = ler_jsonl("votos_A"), ler_jsonl("votos_B"), ler_jsonl("juiz"), ler_jsonl("rotulos_opus")
    faltando = [q["id"] for q in qs if q["id"] not in va or q["id"] not in vb]
    if faltando:
        print(f"ATENÇÃO: {len(faltando)} questões sem os dois votos (rode classificar.py votar de novo): {faltando[:10]}")
    linhas, grupos = [], {}
    for q in qs:
        d, tema, extras, grupo, motivo = terceiro_voto(
            decidir(q, va.get(q["id"]), vb.get(q["id"]), vj.get(q["id"]), ativos), vo.get(q["id"]), ativos)
        grupos[q["id"]] = grupo
        linhas.append({"id": q["id"], "decisao": d, "tema_central_id": tema, "extras_ids": ";".join(extras),
                       "confianca": "", "motivo": motivo})
    rotulos = ler_rotulos(ativos)
    taxa = avaliar(linhas, grupos, rotulos, ativos) if rotulos else {}
    for l in linhas:
        g = grupos[l["id"]]
        l["confianca"] = f"{taxa.get(g, CONFIANCA_INICIAL[g]):.2f}"
    validar(linhas, ativos, len(qs))
    with open(ARQ_PUBLICACAO, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)
    c = Counter(l["decisao"] for l in linhas)
    print(f"\n{ARQ_PUBLICACAO.name}: {dict(c)} | cobertura = {c['publicar'] / len(qs):.3f}")
    print("grupos:", dict(Counter(grupos.values())))
    print("motivos de revisar:", Counter(l["motivo"].split(":")[0] for l in linhas if l["decisao"] == "revisar").most_common())


def sortear_amostra(n_pub=50, n_rev=20, n_fora=10, semente=42):
    """Amostra estratificada para rotular à mão, sem mostrar qual opção os modelos escolheram."""
    ativos, _ = carregar_temas()
    qs = {q["id"]: q for q in carregar_questoes()}
    linhas = list(csv.DictReader(open(ARQ_PUBLICACAO, encoding="utf-8")))
    va, vb = ler_jsonl("votos_A"), ler_jsonl("votos_B")
    rnd = random.Random(semente)
    escolhidas = []
    for decisao, n in (("publicar", n_pub), ("revisar", n_rev), ("fora", n_fora)):
        ids = [l["id"] for l in linhas if l["decisao"] == decisao]
        escolhidas += rnd.sample(ids, min(n, len(ids)))
    rnd.shuffle(escolhidas)
    saida, md = [], ["# Amostra para rotular\n",
                     "Para cada questão, escreva em amostra_ouro.csv o id do tema correto (ou `fora`).",
                     "As opções são só um atalho, em ordem aleatória: o tema certo pode não estar entre elas.",
                     "A árvore completa está em cache/arvore.txt.\n"]
    for qid in escolhidas:
        opcoes = set()
        for v in (va.get(qid), vb.get(qid)):
            if v:
                for t in (v["tema_central_id"], v.get("segunda_opcao_id")):
                    if t in ativos and ativos[t]["nivel"] >= 1:
                        opcoes.add(t)
                        p = pai(t, ativos)
                        if p and ativos[p]["nivel"] >= 1:
                            opcoes.add(p)
                        irmaos = [f for f in ativos[p]["filhos"] if f != t] if p else []
                        if irmaos:
                            opcoes.add(rnd.choice(irmaos))
        opcoes = sorted(opcoes, key=lambda _: rnd.random())
        saida.append({"id": qid, "opcoes": ";".join(opcoes), "tema_correto_id": "", "observacao": ""})
        md.append(f"\n---\n\n## {qid}\n\n{texto_questao(qs[qid])}\n\n**Opções:**")
        md += [f"- `{t}` {ativos[t]['caminho']}" for t in opcoes]
    with open(ARQ_AMOSTRA, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(saida[0]))
        w.writeheader()
        w.writerows(saida)
    (CACHE / "amostra_para_rotular.md").write_text("\n".join(md), encoding="utf-8")
    print(f"{len(saida)} questões em {ARQ_AMOSTRA.name}; texto para leitura em cache/amostra_para_rotular.md")


def preencher():
    """Põe o rótulo do Opus nas linhas vazias de amostra_ouro.csv e lista em cache/conferir.md
    TODAS as publicadas da amostra ainda não conferidas por humano (com o Opus votando, só o humano mede)."""
    ativos, _ = carregar_temas()
    qs = {q["id"]: q for q in carregar_questoes()}
    pub = {l["id"]: l for l in csv.DictReader(open(ARQ_PUBLICACAO, encoding="utf-8"))}
    opus = ler_jsonl("rotulos_opus")
    linhas = list(csv.DictReader(open(ARQ_AMOSTRA, encoding="utf-8-sig")))
    for r in linhas:
        o = opus.get(r["id"])
        if o and not r["tema_correto_id"]:
            r["tema_correto_id"] = rotulo_opus(o)
            r["observacao"] = "opus"
    with open(ARQ_AMOSTRA, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)

    caminho = lambda t: "fora" if t == "fora" else f"`{t}` {ativos[t]['caminho']}"
    pendentes = [r for r in linhas if pub[r["id"]]["decisao"] == "publicar" and r["observacao"] == "opus"]
    discorda = [r for r in pendentes if not acertou(pub[r["id"]], r["tema_correto_id"], ativos)]
    concorda = [r for r in pendentes if r not in discorda]
    md = ["# Conferir rótulos do Opus\n",
          "Para cada questão: se o Opus errou, troque `tema_correto_id` em amostra_ouro.csv;",
          "em todas as que você olhar, troque `observacao` de `opus` para `conferido` (ou `conferido: motivo`).",
          "Ou mande no chat: `Q0001: ok` (Opus certo) / `Q0001: <id certo>`.\n",
          f"Publicadas na amostra ainda não conferidas: {len(pendentes)} (Opus discorda: {len(discorda)})\n"]
    for titulo, grupo in (("Opus DISCORDA da publicação", discorda), ("Opus concorda", concorda)):
        if not grupo:
            continue
        md.append(f"\n# {titulo}\n")
        for r in grupo:
            o, l = opus[r["id"]], pub[r["id"]]
            md += [f"\n---\n\n## {r['id']}\n\n{texto_questao(qs[r['id']])}\n",
                   f"- **Publicado:** {caminho(l['tema_central_id'])}",
                   f"- **Opus:** {caminho(r['tema_correto_id'])} — {o['justificativa']}"]
    (CACHE / "conferir.md").write_text("\n".join(md), encoding="utf-8")
    print(f"{len(pendentes)} publicadas da amostra sem conferência humana ({len(discorda)} com o Opus discordando)"
          f" → cache/conferir.md")


def _autoteste(ativos):
    tema = next(t for t, r in ativos.items() if r["nivel"] == 1 and len(r["filhos"]) >= 2)
    filho, irmao = ativos[tema]["filhos"][:2]
    outro = next(t for t in ativos[pai(tema, ativos)]["filhos"] if t != tema)
    voto = lambda t: {"tema_central_id": t, "nenhum_serve": False}
    assert mesmo_ramo(filho, tema, ativos) and mesmo_ramo(tema, filho, ativos) and mesmo_ramo(filho, filho, ativos)
    assert not mesmo_ramo(filho, irmao, ativos) and not mesmo_ramo(tema, outro, ativos)
    assert no_candidato(voto(filho), voto(filho), ativos) == filho
    assert no_candidato(voto(filho), voto(irmao), ativos) == tema
    assert no_candidato(voto(filho), voto(tema), ativos) == tema
    assert no_candidato(voto(filho), voto(outro), ativos) is None  # só a disciplina em comum
    pub = ("publicar", filho, [], "unanime", "")
    assert terceiro_voto(pub, voto(tema), ativos) == pub  # Opus no pai: mesmo ramo, publica
    assert terceiro_voto(pub, voto(irmao), ativos)[0] == "revisar"  # Opus no irmão: segura
    assert terceiro_voto(pub, None, ativos)[0] == "revisar"  # sem 3º voto não publica
    assert wilson(0, 0) == (0.0, 1.0) and wilson(50, 50)[0] > 0.9


if __name__ == "__main__":
    _autoteste(carregar_temas()[0])
    {"amostra": sortear_amostra, "preencher": preencher}.get(sys.argv[1] if sys.argv[1:] else "", gerar)()
