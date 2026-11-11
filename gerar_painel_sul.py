"""Gera o painel HTML da região Sul: ações de reajuste da tabela do SUS no TRF-1.

Uso (na pasta CONSOLIDAÇÃO MUNICÍPIOS TABELA SUS):
    py -3 painel/gerar_painel_sul.py

Lê, da pasta REGIÃO SUL:
  - cnpj-municipios-<uf>.md   lista de municípios e CNPJs (PR, SC, RS)
  - captura/<uf>.jsonl        resultado bruto da busca no PJe do TRF-1, 1º grau, uma linha por município
                              (gravado por captura/registrar.py)

Um estado sem captura completa aparece como "pesquisa pendente". Quando a captura de um
novo estado terminar, basta rodar o script de novo.

Classificação (mesmo critério do Nordeste):
  - com ação:   algum processo com o próprio município ("MUNICIPIO DE <nome>") no polo ativo;
  - a verificar: só processos cujo polo ativo é "X e outros (n)", em que o município pode ser
                 coautor ou réu (conferir nos autos);
  - sem ação:   nenhum processo, ou só processos de terceiros em que o município é réu.

Usa, desta pasta (painel/): modelo-painel.html (layout do Nordeste, adaptado aqui para o Sul),
logo-monteiro.svg e malha-ibge-sul.json.

Grava: REGIÃO SUL/painel-tabela-sus-sul.html.
"""
import datetime as dt
import json
import os
import re
import sys
import unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from gerar_painel import fase, logo_inline, poligonos  # noqa: E402  (mesmas regras do painel Nordeste)
import math  # noqa: E402

PASTA = os.path.join(os.path.dirname(AQUI), "REGIÃO SUL")
SAIDA = os.path.join(PASTA, "painel-tabela-sus-sul.html")
ESTADOS = [("PR", "Paraná"), ("SC", "Santa Catarina"), ("RS", "Rio Grande do Sul")]  # norte para sul


def chave(txt):
    t = unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]", "", t)


def ler_lista_cnpj(uf):
    caminho = os.path.join(PASTA, f"cnpj-municipios-{uf.lower()}.md")
    linhas = []
    for ln in open(caminho, encoding="utf-8"):
        m = re.match(r"\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(\d{7})\s*\|\s*([\d./-]{18})\s*\|", ln)
        if m:
            linhas.append({"n": int(m.group(1)), "nome": m.group(2), "ibge": m.group(3), "cnpj": m.group(4)})
    return linhas


def ler_captura(uf, total):
    caminho = os.path.join(PASTA, "captura", f"{uf.lower()}.jsonl")
    if not os.path.exists(caminho):
        return None
    regs = {}
    for ln in open(caminho, encoding="utf-8"):
        if ln.strip():
            r = json.loads(ln)
            regs[r["ibge"]] = r
    if len(regs) < total:  # captura em andamento: o estado continua pendente
        return None
    datas = sorted({r["consulta"][:10] for r in regs.values()})
    return {"regs": regs, "data": "/".join(reversed(datas[-1].split("-")))}


def vara_curta(v):
    v = re.sub(r"Vara Federal Cível da (SJ\w\w)", r"VF Cível \1", v or "")
    return v.strip()


def mov_curto(m):
    m = (m or "").strip()
    if re.search(r"suspens|sobrest", m, re.I):
        if "2.176.896" in m:
            return "Processo suspenso (REsp 2.176.896/DF)"
        return "Processo suspenso (Tema 1.305 do STJ)"
    return m.rstrip(".")


def autor(p, nome):
    return chave(p["polo_ativo"]).startswith("MUNICIPIODE" + chave(nome))


def lista_terceiros(ps):
    return "; ".join(f"{p['processo']} ({p['polo_ativo']})" for p in ps)


def classificar(reg, nome):
    ps = reg["processos"]
    if not ps:
        return "sem", [], ""
    proprios = [p for p in ps if autor(p, nome)]
    outros = [p for p in ps if p not in proprios]
    duvida = [p for p in outros if "e outros" in p["polo_ativo"]]
    terceiros = [p for p in outros if p not in duvida]
    obs = []
    if proprios:
        sit = "com"
    elif duvida:
        sit = "verificar"
        obs.append("Polo ativo com outras partes; conferir nos autos se o município é coautor ou réu: " +
                   "; ".join(f"{p['processo']} (ativo: {p['polo_ativo']}; passivo: {p['polo_passivo']})" for p in duvida) + ".")
    else:
        sit = "sem"
    if sit == "com" and duvida:
        terceiros = terceiros + duvida
    if terceiros:
        obs.append(f"A busca pelo CNPJ trouxe {len(terceiros)} processo(s) de outras partes em que o município "
                   f"figura sem ser autor (desconsiderados): {lista_terceiros(terceiros)}.")
    return sit, proprios, " ".join(obs)


def metodologia(uf_nome, total, data):
    return [
        f"Lista de municípios: os {total} municípios de {uf_nome} e o CNPJ de cada prefeitura vêm do cadastro de entes "
        "do Tesouro Nacional (SICONFI), exercício 2026. Os CNPJs passaram na validação dos dígitos verificadores, "
        "nenhum se repete e todos são de matriz.",
        "Sistema pesquisado: consulta de processos do PJe do TRF-1, 1º grau (Seção Judiciária do DF e demais seções da "
        "1ª Região), com o login do advogado. Não abrange a Justiça Federal da 4ª Região (TRF-4), onde estão as "
        "seções judiciárias do Sul, nem o 2º grau do TRF-1.",
        "Busca pelo CNPJ: uma busca por município, combinando o assunto \"Reajuste da tabela do SUS\" e o CNPJ da "
        "prefeitura. O resultado é a lista que o PJe mostra na tela de pesquisa (número, vara, classe, autuação, "
        "polos e último movimento). Nenhum processo foi aberto.",
        "Critério: o município conta como \"com ação\" quando aparece no polo ativo como \"Município de ...\". "
        "Processos de hospitais, clínicas e entidades em que o município é réu foram desconsiderados e anotados em "
        "observação. Quando o polo ativo é \"X e outros (n)\", não dá para saber pela tela se o município é coautor "
        "ou réu; esses casos estão como \"a verificar\".",
        "Sem conferência pelo nome: como nos estados do Nordeste (exceto PE), os municípios sem resultado não foram "
        "pesquisados de novo pelo nome. Uma ação ajuizada com outro CNPJ (por exemplo, o do Fundo Municipal de Saúde) "
        "ou com outro assunto não aparece aqui.",
        f"Controle: a busca foi testada com um CNPJ que sabidamente tem ação (Abreu e Lima/PE) no meio e no fim da "
        f"captura, e o PJe devolveu o processo esperado. Situação do PJe em {data}.",
    ]


def projetar(malha, largura=1000):
    geoms = malha["municipios"]
    pts = [p for g in geoms.values() for poly in poligonos(g) for anel in poly for p in anel]
    lon0, lon1 = min(p[0] for p in pts), max(p[0] for p in pts)
    lat0, lat1 = min(p[1] for p in pts), max(p[1] for p in pts)
    k = math.cos(math.radians((lat0 + lat1) / 2))
    escala = largura / ((lon1 - lon0) * k)

    def caminho(g):
        out = []
        for poly in poligonos(g):
            for anel in poly:
                out.append("M" + "L".join(f"{(x - lon0) * k * escala:.1f},{(lat1 - y) * escala:.1f}" for x, y in anel) + "Z")
        return "".join(out)

    return {"w": largura, "h": round((lat1 - lat0) * escala, 1),
            "municipios": {c: caminho(g) for c, g in geoms.items()},
            "estados": {uf: caminho(malha["estados"][uf]) for uf, _ in ESTADOS}}


TROCAS = [  # textos do modelo do Nordeste que mudam no Sul
    ("<title>Tabela SUS no TRF-1 · Nordeste</title>", "<title>Tabela SUS no TRF-1 · Sul</title>"),
    ("Municípios do Nordeste que já ajuizaram", "Municípios da região Sul que já ajuizaram"),
    ("Todo o Nordeste", "Toda a região Sul"),
    ("const onde = e ? `Em ${e.nome}`",
     "const onde = e ? ({ PR: \"No Paraná\", SC: \"Em Santa Catarina\", RS: \"No Rio Grande do Sul\" }[e.uf] || `Em ${e.nome}`)"),
    ("frase.append(`${e.nome} ainda não foi pesquisado. A lista dos `",
     "frase.append(({ PR: \"O Paraná ainda não foi pesquisado\", SC: \"Santa Catarina ainda não foi pesquisada\", RS: \"O Rio Grande do Sul ainda não foi pesquisado\" }[e.uf] || `${e.nome} ainda não foi pesquisado`) + `. A lista dos `"),
    ('"no Nordeste"', '"na região Sul"'),
    ("Mapa dos municípios do Nordeste", "Mapa dos municípios da região Sul"),
    ("`Nos ${pesquisados.length} estados pesquisados até agora",
     "(pesquisados.length === 1 ? `No estado pesquisado até agora` : `Nos ${pesquisados.length} estados pesquisados até agora`) + `"),
    ("só apareceram homônimos", "polo ativo com outras partes"),
    ('"nordeste"}', '"sul"}'),
    ("Ex.: Caruaru, 10.091.536 ou 1004128", "Ex.: Viamão, 88.000.914 ou 1133094"),
    ("os números entram quando a planilha do estado for gerada.", "os números entram quando a captura do estado terminar."),
    ("a partir das planilhas da pasta.", "a partir da captura do PJe gravada na pasta REGIÃO SUL."),
    ("const ajuste = { MA: [0, 0.1], PI: [0, 0.15], BA: [0, 0], PE: [-0.15, 0], PB: [0, 0], RN: [0, -0.05], CE: [0, 0], AL: [0.1, 0.1], SE: [0.2, 0.2] }[uf] || [0, 0];",
     "const ajuste = { PR: [0, 0], SC: [0.1, 0], RS: [0, -0.05] }[uf] || [0, 0];"),
]
PASSOS_NE = re.compile(r"<summary>Como atualizar este painel</summary>\s*<ol>.*?</ol>", re.S)
PASSOS_SUL = """<summary>Como atualizar este painel</summary>
    <ol>
      <li>Termine a captura do estado no PJe do TRF-1 (arquivo <code>REGIÃO SUL/captura/&lt;uf&gt;.jsonl</code>, gravado por <code>captura/registrar.py</code>, com todos os municípios da lista).</li>
      <li>Rode <code>py -3 painel/gerar_painel_sul.py</code> na pasta CONSOLIDAÇÃO MUNICÍPIOS TABELA SUS.</li>
      <li>O estado sai de "pesquisa pendente" e entra nos números, no mapa e na tabela.</li>
    </ol>"""


def modelo_sul():
    html = open(os.path.join(AQUI, "modelo-painel.html"), encoding="utf-8").read()
    for a, b in TROCAS:
        if a not in html:
            sys.exit(f"Trecho do modelo não encontrado (o modelo do Nordeste mudou?): {a[:60]}")
        html = html.replace(a, b)
    html, n = PASSOS_NE.subn(PASSOS_SUL, html)
    if n != 1:
        sys.exit("Bloco 'Como atualizar este painel' não encontrado no modelo.")
    return html


def main():
    estados, municipios, processos, avisos = [], [], [], []
    for uf, nome in ESTADOS:
        lista = ler_lista_cnpj(uf)
        cap = ler_captura(uf, len(lista))
        for m in lista:
            reg = cap["regs"].get(m["ibge"]) if cap else None
            if cap and reg is None:
                avisos.append(f"{uf}: {m['nome']} sem registro na captura.")
            if reg and reg["cnpj"] != m["cnpj"]:
                avisos.append(f"{uf}: CNPJ divergente em {m['nome']} ({reg['cnpj']} x {m['cnpj']}).")
            sit, proprios, obs = classificar(reg, m["nome"]) if reg else ("pendente", [], "")
            municipios.append({"ibge": m["ibge"], "nome": m["nome"], "uf": uf, "cnpj": m["cnpj"],
                               "sit": sit, "obs": obs, "n": len(proprios)})
            for p in proprios:
                mov = mov_curto(p["ultimo_movimento"])
                processos.append({"ibge": m["ibge"], "uf": uf, "num": p["processo"], "vara": vara_curta(p["orgao"]),
                                  "aut": p["autuacao"], "mov": mov, "fase": fase(mov)})
        estados.append({"uf": uf, "nome": nome, "total": len(lista), "pesquisado": bool(cap),
                        "data": cap["data"] if cap else None,
                        "metodologia": metodologia(nome, len(lista), cap["data"]) if cap else [],
                        "arquivo": f"captura/{uf.lower()}.jsonl" if cap else None})

    malha = json.load(open(os.path.join(AQUI, "malha-ibge-sul.json"), encoding="utf-8"))
    sem_mapa = [m["nome"] for m in municipios if m["ibge"] not in malha["municipios"]]
    if sem_mapa:
        avisos.append(f"{len(sem_mapa)} município(s) sem polígono na malha: {', '.join(sem_mapa[:10])}")
    dados = {"gerado": dt.datetime.now().strftime("%d/%m/%Y %H:%M"), "estados": estados,
             "municipios": municipios, "processos": processos, "mapa": projetar(malha)}
    js = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = modelo_sul().replace("/*__DADOS__*/null", js).replace("<!--__LOGO__-->", logo_inline())
    open(SAIDA, "w", encoding="utf-8").write(html)

    cont = {s: sum(1 for m in municipios if m["sit"] == s) for s in ("com", "sem", "verificar", "pendente")}
    print(f"Painel gravado em {SAIDA} ({len(html) / 1024:.0f} KB)")
    print("Estados pesquisados:", ", ".join(e["uf"] for e in estados if e["pesquisado"]) or "nenhum",
          "| pendentes:", ", ".join(e["uf"] for e in estados if not e["pesquisado"]) or "nenhum")
    print(f"Municípios: {len(municipios)} | com ação {cont['com']} | sem ação {cont['sem']} | "
          f"verificar {cont['verificar']} | pendentes {cont['pendente']} | processos {len(processos)}")
    for a in avisos:
        print("Aviso:", a)


if __name__ == "__main__":
    main()
